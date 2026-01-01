import asyncio
import os
import shlex
import shutil
import tempfile
import traceback
import logging
from textwrap import dedent, indent

SUBPROCESS_TIMEOUT = 120

logger = logging.getLogger("CodexAgent")


class CodexAgent:
    """
    Codex agent for evoeval evaluation.
    Uses the same prompt format as other models in evoeval.
    """
    
    def __init__(self, model_name: str = "gpt-5.1-codex-mini", verbose: bool = False, **kwargs):
        self.model_name = model_name
        self.verbose = verbose
        
        # Set up environment
        self.env = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        }
        print("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY"))
        
        if shutil.which("codex") is None:
            raise RuntimeError(
                "Codex CLI not found. Please ensure it's installed and available in PATH."
            )
    
    async def _run_codex_command(self, prompt: str, work_dir: str) -> str:
        """Run codex command with the prompt in a working directory."""
        escaped_prompt = shlex.quote(prompt)
        cmd = [
            "codex",
            "exec",
            escaped_prompt,
            "--full-auto",
            "--model", self.model_name,
            "--skip-git-repo-check"
        ]
        
        # Run the command in the working directory
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env={**os.environ, **self.env},
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=SUBPROCESS_TIMEOUT
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("Codex command timed out")

        if process.returncode != 0:
            raise RuntimeError(f"Codex command failed: {stderr.decode(errors='replace')}")

        return stdout.decode(errors="replace")
    
    async def _extract_generated_files(self, work_dir: str) -> str:
        """Extract the generated Python files from the working directory."""
        file_path = os.path.join(work_dir, "answer.txt")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                out = f.read()
            if self.verbose:
                logger.info(f"Output from Codex: {out}")
            return out
        except Exception as e:
            logger.error(f"Error extracting generated files from Codex: {e}")
            process = await asyncio.create_subprocess_shell(
                f"ls -la {work_dir}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            logger.info("Content of working directory:\n" + stdout.decode(errors='replace'))
            # Return empty strings for all samples on error
            raise e

    async def answer(self, question: str) -> str:
        """Generate code using Codex CLI."""    
        # Create temporary working directory
        work_dir = tempfile.mkdtemp()
        if self.verbose:
            logger.info(f"Running Codex instance in Working directory: {work_dir}")
        
        try:
            # Write question to file
            file_path = os.path.join(work_dir, "question.txt")        
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(question)
            if self.verbose:
                logger.info(f"Content of question.txt:\n{question}")
        except Exception as e:
            logger.error(f"Error writing question to file: {e}")
            raise e

        instruction = f"""\
Given a problem in `question.txt` in the current working directory "{work_dir}", your task is to answer the question by thinking step-by-step in a clear and specific manner.
Once you have thought about the reasoning process, provide the answer in the file "answer.txt" (which should also be put in in the current working directory).
Do not explain your reasoning inside the answer tags, provide only the final answer. When an example is provided, you should strictly follow the format of the output/answer in that example.
"""
        if self.verbose:
            logger.info(f"Instruction: {instruction}")
        
        try:
            # Run codex command in working directory
            await self._run_codex_command(instruction.strip(), work_dir)
            
            # Extract all generated files
            return await self._extract_generated_files(work_dir)
                        
        finally:
            # Clean up temporary files and directories
            if 0:
                try:
                    import shutil
                    shutil.rmtree(work_dir)
                except OSError:
                    pass
