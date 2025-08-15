#!/usr/bin/env python3
"""
Evaluation Orchestrator Script

This script orchestrates the complete evaluation pipeline by running:
1. run_conversations.py - Executes conversation flows with the agent
2. generator.py - Generates additional test conversations
3. deep_eval.py - Evaluates all conversations using deepeval metrics

The script runs each component in sequence and provides detailed logging
of the execution process, including timing information and error handling.

Usage:
    python evaluate.py                    # Use default (20 conversations)
    python evaluate.py -n 5              # Generate 5 conversations
    python evaluate.py --num-conversations 10  # Generate 10 conversations

Environment Variables:
    All environment variables required by the individual scripts:
    - LLM_API_TOKEN: API key for LLM endpoints
    - LLM_URL: Base URL for LLM API
    - LLM_ID: Model identifier (optional)

Dependencies:
    - All dependencies from run_conversations.py, generator.py, and deep_eval.py
    - OpenShift CLI (oc) must be available and configured
    - Agent deployment must be running in OpenShift
"""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_script(
    script_name: str, args: Optional[List[str]] = None, timeout: int = 600
) -> bool:
    """
    Run a Python script with optional arguments and timeout, showing real-time output.

    Args:
        script_name: Name of the Python script to run (e.g., 'generator.py')
        args: Optional list of command line arguments to pass to the script
        timeout: Maximum time to wait for script completion in seconds

    Returns:
        True if the script completed successfully, False otherwise

    Raises:
        subprocess.TimeoutExpired: If the script exceeds the timeout
        subprocess.CalledProcessError: If the script returns a non-zero exit code
    """
    cmd = [sys.executable, script_name]
    if args:
        cmd.extend(args)

    logger.info(f"🚀 Starting: {' '.join(cmd)}")
    logger.info("=" * 50)
    start_time = time.time()

    try:
        # Run with real-time output by piping stdout/stderr to parent process
        subprocess.run(
            cmd,
            check=True,
            timeout=timeout,
            cwd=Path(__file__).parent,  # Run in the evaluations directory
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

        duration = time.time() - start_time
        logger.info("=" * 50)
        logger.info(f"✅ Completed: {script_name} (Duration: {duration:.2f}s)")

        return True

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        logger.info("=" * 50)
        logger.error(
            f"⏰ Timeout: {script_name} exceeded {timeout}s limit (ran for {duration:.2f}s)"
        )
        return False

    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        logger.info("=" * 50)
        logger.error(
            f"❌ Failed: {script_name} (Duration: {duration:.2f}s, Exit code: {e.returncode})"
        )
        return False

    except Exception as e:
        duration = time.time() - start_time
        logger.info("=" * 50)
        logger.error(f"💥 Error: {script_name} (Duration: {duration:.2f}s, Error: {e})")
        return False


def _cleanup_generated_files() -> None:
    """
    Remove all files starting with 'generated_flow' from results/conversation_results/.

    This ensures a clean slate for each evaluation run by removing files from
    previous generator.py executions.
    """
    results_dir = Path("results/conversation_results")

    if not results_dir.exists():
        return

    # Find all files starting with 'generated_flow'
    generated_files = list(results_dir.glob("generated_flow*"))

    if not generated_files:
        return

    for file_path in generated_files:
        try:
            file_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove {file_path.name}: {e}")


def _parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments for the evaluation orchestrator.

    Returns:
        Parsed arguments containing evaluation configuration parameters
    """
    parser = argparse.ArgumentParser(
        description="Orchestrate the complete evaluation pipeline"
    )
    parser.add_argument(
        "-n",
        "--num-conversations",
        type=int,
        default=20,
        help="Number of conversations to generate with generator.py (default: 20)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout in seconds for each script execution (default: 600)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=20,
        help="Maximum number of turns per conversation in generator.py (default: 20)",
    )
    return parser.parse_args()


def run_evaluation_pipeline(
    num_conversations: int = 20, timeout: int = 600, max_turns: int = 20
) -> int:
    """
    Run the complete evaluation pipeline.

    Executes the evaluation steps in sequence:
    0. Clean up generated files from previous runs
    1. run_conversations.py - Run predefined conversation flows
    2. generator.py - Generate additional test conversations
    3. deep_eval.py - Evaluate all conversations with deepeval metrics

    Args:
        num_conversations: Number of conversations to generate with generator.py
        timeout: Timeout in seconds for each script execution
        max_turns: Maximum number of turns per conversation in generator.py

    Returns:
        Exit code (0 for success, 1 for any failures)
    """
    logger.info("🎯 Starting Evaluation Pipeline")
    logger.info("=" * 80)

    # Clean up generated files from previous runs
    _cleanup_generated_files()
    logger.info("-" * 60)

    pipeline_start_time = time.time()
    failed_steps = []

    # Step 1: Run conversation flows
    logger.info("📋 Step 1/3: Running predefined conversation flows...")
    if not run_script("run_conversations.py", timeout=timeout):
        failed_steps.append("run_conversations.py")
        logger.error("❌ Step 1 failed - continuing with remaining steps")
    else:
        logger.info("✅ Step 1 completed successfully")

    logger.info("-" * 60)

    # Step 2: Generate additional conversations
    logger.info(
        f"🤖 Step 2/3: Generating {num_conversations} additional test conversations..."
    )
    generator_args = [str(num_conversations), "--max-turns", str(max_turns)]
    if not run_script("generator.py", args=generator_args, timeout=timeout):
        failed_steps.append("generator.py")
        logger.error("❌ Step 2 failed - continuing with remaining steps")
    else:
        logger.info("✅ Step 2 completed successfully")

    logger.info("-" * 60)

    # Step 3: Run deepeval evaluation
    logger.info("📊 Step 3/3: Running deepeval evaluation...")
    if not run_script("deep_eval.py", timeout=timeout):
        failed_steps.append("deep_eval.py")
        logger.error("❌ Step 3 failed")
    else:
        logger.info("✅ Step 3 completed successfully")

    # Pipeline summary
    pipeline_duration = time.time() - pipeline_start_time
    logger.info("=" * 80)
    logger.info(
        f"🏁 Evaluation Pipeline Complete (Total Duration: {pipeline_duration:.2f}s)"
    )

    if failed_steps:
        logger.error(f"❌ Pipeline completed with {len(failed_steps)} failed step(s):")
        for step in failed_steps:
            logger.error(f"   • {step}")
        logger.error("🔍 Check the logs above for detailed error information")
        return 1
    else:
        logger.info("🎉 All pipeline steps completed successfully!")
        logger.info("📁 Check the results/ directory for evaluation outputs")
        return 0


def main() -> int:
    """
    Main entry point for the evaluation orchestrator.

    Returns:
        Exit code (0 for success, 1 for failures)
    """
    try:
        args = _parse_arguments()
        return run_evaluation_pipeline(
            num_conversations=args.num_conversations,
            timeout=args.timeout,
            max_turns=args.max_turns,
        )
    except KeyboardInterrupt:
        logger.warning("⚠️  Pipeline interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"💥 Unexpected error in evaluation pipeline: {e}")
        logger.exception("Full traceback:")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
