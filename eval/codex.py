import os
import shlex
import subprocess
import tempfile
import traceback
from textwrap import dedent, indent
from typing import List


class CodexAgent:
    """
    Codex agent for evoeval evaluation.
    Uses the same prompt format as other models in evoeval.
    """
    
    def __init__(self, model_name: str = "gpt-5.1-codex-mini", **kwargs):
        self.model_name = model_name
        
        # Set up environment
        self.env = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        }
        
        # Check if codex command is available
        try:
            subprocess.run(["codex", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "Codex CLI not found. Please ensure it's installed and available in PATH."
            )
    
    def _run_codex_command(self, prompt: str, work_dir: str) -> str:
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
        # print(" ".join(cmd))
        
        # Run the command in the working directory
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=work_dir,
            env={**os.environ, **self.env}
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Codex command failed: {result.stderr}")
        
        return result.stdout
    
    def _extract_generated_files(self, work_dir: str) -> str:
        """Extract the generated Python files from the working directory."""
        file_path = os.path.join(work_dir, "answer.txt")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                out = f.read()
                # print(out)
                return out
        except:
            print(f"Error generating code with Codex: {e}")
            traceback.print_exc()
            # Return empty strings for all samples on error
            return ""            

    def answer(self, prompt: str) -> List[str]:
        """Generate code using Codex CLI."""
        work_dir = None
        
        try:
            # Create temporary working directory
            work_dir = tempfile.mkdtemp()
            
            # Create instruction with prompt
            instruction = dedent("""\
            Given a problem, your task is to answer the question by thinking step-by-step in a clear and specific manner.
            Once you have thought about the reasoning process, provide the answer in the file "answer.txt" in the following format:
<answer>answer here</answer>
            Do not explain your reasoning inside the answer tags, provide only the final answer. When an example is provided, you should strictly follow the format of the output/answer in that example.

            {prompt}
            """)
                        
            full_instruction = instruction.format(prompt=prompt.strip())
            
            # Run codex command in working directory
            self._run_codex_command(full_instruction, work_dir)
            
            # Extract all generated files
            return self._extract_generated_files(work_dir)
            
        except Exception as e:
            print(f"Error generating code with Codex: {e}")
            traceback.print_exc()
            # Return empty strings for all samples on error
            return ""
            
        finally:
            # Clean up temporary files and directories
            if work_dir:
                try:
                    import shutil
                    shutil.rmtree(work_dir)
                except OSError:
                    pass