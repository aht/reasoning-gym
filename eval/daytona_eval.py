#!/usr/bin/env python
"""
Daytona declarative image builder for reasoning-gym evaluation.

This script creates a Daytona declarative image that:
1. Sets up a Python environment
2. Clones the reasoning-gym repository
3. Installs all dependencies
4. Runs the evaluation script

Usage:
    uv run eval/daytona_eval.py --config eval/test.yaml

Example:
    uv run eval/daytona_eval.py --config eval/test.yaml
"""

import sys
import os
import argparse
from pathlib import Path

try:
    from daytona_sdk import Daytona, Image
    from daytona_sdk.common.daytona import CreateSandboxFromImageParams
except ImportError:
    print("Error: daytona_sdk is not installed.")
    print("Please install it with: pip install daytona-sdk")
    sys.exit(1)


def create_reasoning_gym_image() -> Image:
    """
    Create a Daytona declarative image for reasoning-gym evaluation.

    Returns:
        Image: Configured Daytona image ready for evaluation
    """
    # Build the image with all necessary components
    image = (
        Image.debian_slim("3.12")
        # Install system dependencies that might be needed
        .run_commands("apt-get update && apt-get install -y git curl")
        # Install Node.js and npm for Codex installation
        .run_commands("curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs")
        # Set working directory
        .workdir("/workspace")
        # Clone the reasoning-gym repository
        .run_commands("git clone -b harbor-adapter https://github.com/aht/reasoning-gym.git")
        # Change to the repo directory for subsequent commands
        .workdir("/workspace/reasoning-gym")
        # Install the package and its dependencies
        .run_commands("pip install --upgrade pip && pip install -e . && pip install -r eval/requirements-eval.txt")
        # Install OpenAI Codex CLI
        .run_commands("npm install -g @openai/codex")
    )

    return image


def main():
    """
    Main function to create Daytona sandbox and run evaluation.
    """
    parser = argparse.ArgumentParser(
        description="Run reasoning-gym evaluation on Daytona",
        epilog="All additional arguments are passed to eval/eval.py"
    )
    parser.add_argument(
        "--sandbox-name",
        default="reasoning-gym-eval",
        help="Name for the Daytona sandbox (default: reasoning-gym-eval)"
    )
    parser.add_argument(
        "--keep-sandbox",
        action="store_true",
        help="Keep the sandbox running after evaluation completes"
    )

    # Parse known args to separate Daytona args from eval.py args
    args, eval_args = parser.parse_known_args()

    # Get API keys from environment
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        print("Error: OPENROUTER_API_KEY environment variable is not set.", file=sys.stderr)
        print("Please set it with: export OPENROUTER_API_KEY=your_key_here", file=sys.stderr)
        return 1

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Error: OPENAI_API_KEY environment variable is not set.", file=sys.stderr)
        print("Please set it with: export OPENAI_API_KEY=your_key_here", file=sys.stderr)
        return 1

    print("Creating Daytona declarative image for reasoning-gym evaluation...")
    image = create_reasoning_gym_image()

    try:
        # Create Daytona client
        daytona = Daytona()

        # Try to get existing sandbox first
        print(f"Checking for existing sandbox: {args.sandbox_name}")
        try:
            sandbox = daytona.get(args.sandbox_name)
            print(f"Found existing sandbox: {sandbox.id}")
            print("Reusing existing sandbox...")
        except Exception:
            # Sandbox doesn't exist, create a new one
            print(f"Creating new sandbox: {args.sandbox_name}")
            params = CreateSandboxFromImageParams(
                name=args.sandbox_name,
                image=image,
                env_vars={
                    "OPENROUTER_API_KEY": openrouter_api_key,
                    "OPENAI_API_KEY": openai_api_key
                }
            )
            sandbox = daytona.create(params=params)
            print(f"Sandbox created successfully: {sandbox.id}")

            # setup codex auth.json
            sandbox.process.exec(
                f"echo '{{\"OPENAI_API_KEY\": \"{openai_api_key}\"}}' > /root/.codex/auth.json"
            )

            # setup harbor adapter git repo which contains the eval config file for parity
            print("Setting up harbor adapter-reasoning-gym git repo...")
            result = sandbox.process.exec(f"""git clone -b adapter-reasoning-gym https://github.com/aht/harbor.git /workspace/harbor""")
            print(result.result)

        print("Running evaluation...")

        # Build the eval command with any additional arguments
        eval_command = ["python", "eval/eval.py"] + eval_args
        eval_cmd_str = " ".join(eval_command)

        print(f"Executing: {eval_cmd_str}")

        # Execute the evaluation script
        result = sandbox.process.exec(eval_cmd_str, timeout=3000)

        # Print output
        print("\n" + "="*80)
        print("EVALUATION OUTPUT:")
        print("="*80)
        print(result.result)

        print("\n" + "="*80)
        print(f"Evaluation completed with exit code: {result.exit_code}")
        print("="*80)

        # Download results if they exist
        results_dir = Path("results")
        if not results_dir.exists():
            results_dir.mkdir(parents=True, exist_ok=True)

        print("\nDownloading evaluation results...")

        try:
            # Try to download the results directory from the sandbox
            files = sandbox.fs.find_files(path="/workspace/reasoning-gym/results", pattern="**/*")
            if files:
                for file in files:
                    file_path = file.path if hasattr(file, 'path') else str(file)
                    sandbox.fs.download_file(file_path, str(results_dir / Path(file_path).name))
                print(f"Results downloaded to: {results_dir.absolute()}")
            else:
                print("No result files found to download.")
        except Exception as e:
            print(f"Note: Could not download results: {e}")
            print("Results may still be available in the sandbox.")

        # Cleanup unless --keep-sandbox is specified
        if not args.keep_sandbox:
            print(f"\nCleaning up sandbox: {args.sandbox_name}")
            sandbox.delete()
            print("Sandbox deleted.")
        else:
            print(f"\nSandbox {args.sandbox_name} is still running.")
            print(f"Sandbox ID: {sandbox.id}")
            print("Use `daytona delete <sandbox-id>` to remove it later.")

        return result.exit_code

    except Exception as e:
        print(f"\nError during evaluation: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
