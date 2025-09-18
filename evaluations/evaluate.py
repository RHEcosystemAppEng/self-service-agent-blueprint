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
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    Remove all files starting with 'generated_flow' from results/conversation_results/
    and all token usage files from results/token_usage/.

    This ensures a clean slate for each evaluation run by removing files from
    previous executions.
    """
    # Clean up generated conversation files
    conversation_results_dir = Path("results/conversation_results")
    if conversation_results_dir.exists():
        # Find all files starting with 'generated_flow'
        generated_files = list(conversation_results_dir.glob("generated_flow*"))

        if generated_files:
            logger.info(
                f"Removing {len(generated_files)} generated conversation files from previous runs"
            )
            for file_path in generated_files:
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove {file_path.name}: {e}")

    # Clean up token usage files
    token_usage_dir = Path("results/token_usage")
    if token_usage_dir.exists():
        # Find all token usage files (all patterns)
        token_patterns = [
            "token_usage_*.json",
            "run_conversations_*.json",
            "generator_*.json",
            "deep_eval_*.json",
            "pipeline_aggregated_*.json",
        ]

        all_token_files = []
        for pattern in token_patterns:
            token_files = list(token_usage_dir.glob(pattern))
            all_token_files.extend(token_files)

        if all_token_files:
            logger.info(
                f"Removing {len(all_token_files)} token usage files from previous runs"
            )
            for file_path in all_token_files:
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove {file_path.name}: {e}")


def _aggregate_token_usage() -> Dict[str, Any]:
    """
    Aggregate token usage statistics from all token usage files generated during the pipeline.

    Searches for token_usage_*.json files in various results directories and combines
    their statistics into a comprehensive summary. Now handles separate app and evaluation tokens.

    Returns:
        Dictionary containing aggregated token statistics
    """
    aggregated_stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "total_calls": 0,
        "max_input_tokens": 0,
        "max_output_tokens": 0,
        "max_total_tokens": 0,
        "app_tokens": {
            "input": 0,
            "output": 0,
            "total": 0,
            "calls": 0,
            "max_input": 0,
            "max_output": 0,
            "max_total": 0,
        },
        "evaluation_tokens": {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "call_count": 0,
            "max_input_tokens": 0,
            "max_output_tokens": 0,
            "max_total_tokens": 0,
        },
        "scripts": {},
        "detailed_calls": [],
    }

    # Search for token usage files in various directories
    search_dirs = [
        Path("results/token_usage"),
        Path("results/deep_eval_results"),
        Path("results"),
        Path("."),
    ]

    found_files = []
    for search_dir in search_dirs:
        if search_dir.exists():
            # Look for all token usage files with various naming patterns
            patterns = [
                "token_usage_*.json",  # Old naming pattern
                "run_conversations_*.json",  # New naming pattern
                "generator_*.json",  # New naming pattern
                "deep_eval_*.json",  # New naming pattern
                "pipeline_aggregated_*.json",  # Skip aggregated files to avoid double counting
            ]
            for pattern in patterns:
                if pattern != "pipeline_aggregated_*.json":  # Skip aggregated files
                    token_files = list(search_dir.glob(pattern))
                    found_files.extend(token_files)

    logger.info(f"Found {len(found_files)} token usage files to aggregate")

    for token_file in found_files:
        try:
            with open(token_file, "r") as f:
                token_data = json.load(f)

            # Extract summary data
            summary = token_data.get("summary", {})
            script_name = token_file.stem  # Get filename without extension

            # Aggregate totals
            aggregated_stats["total_input_tokens"] += summary.get(
                "total_input_tokens", 0
            )
            aggregated_stats["total_output_tokens"] += summary.get(
                "total_output_tokens", 0
            )
            aggregated_stats["total_tokens"] += summary.get("total_tokens", 0)
            aggregated_stats["total_calls"] += summary.get("call_count", 0)

            # Aggregate maximum values
            aggregated_stats["max_input_tokens"] = max(
                aggregated_stats["max_input_tokens"], summary.get("max_input_tokens", 0)
            )
            aggregated_stats["max_output_tokens"] = max(
                aggregated_stats["max_output_tokens"],
                summary.get("max_output_tokens", 0),
            )
            aggregated_stats["max_total_tokens"] = max(
                aggregated_stats["max_total_tokens"], summary.get("max_total_tokens", 0)
            )

            # Aggregate app tokens if present
            app_tokens = token_data.get("app_tokens", {})
            if app_tokens:
                aggregated_stats["app_tokens"]["input"] += app_tokens.get("input", 0)
                aggregated_stats["app_tokens"]["output"] += app_tokens.get("output", 0)
                aggregated_stats["app_tokens"]["total"] += app_tokens.get("total", 0)
                aggregated_stats["app_tokens"]["calls"] += app_tokens.get("calls", 0)

                # Aggregate app token maximums
                aggregated_stats["app_tokens"]["max_input"] = max(
                    aggregated_stats["app_tokens"]["max_input"],
                    app_tokens.get("max_input", 0),
                )
                aggregated_stats["app_tokens"]["max_output"] = max(
                    aggregated_stats["app_tokens"]["max_output"],
                    app_tokens.get("max_output", 0),
                )
                aggregated_stats["app_tokens"]["max_total"] = max(
                    aggregated_stats["app_tokens"]["max_total"],
                    app_tokens.get("max_total", 0),
                )

            # Aggregate evaluation tokens if present
            eval_tokens = token_data.get("evaluation_tokens", {})
            if eval_tokens:
                aggregated_stats["evaluation_tokens"][
                    "total_input_tokens"
                ] += eval_tokens.get("total_input_tokens", 0)
                aggregated_stats["evaluation_tokens"][
                    "total_output_tokens"
                ] += eval_tokens.get("total_output_tokens", 0)
                aggregated_stats["evaluation_tokens"][
                    "total_tokens"
                ] += eval_tokens.get("total_tokens", 0)
                aggregated_stats["evaluation_tokens"]["call_count"] += eval_tokens.get(
                    "call_count", 0
                )

                # Aggregate evaluation token maximums
                aggregated_stats["evaluation_tokens"]["max_input_tokens"] = max(
                    aggregated_stats["evaluation_tokens"]["max_input_tokens"],
                    eval_tokens.get("max_input_tokens", 0),
                )
                aggregated_stats["evaluation_tokens"]["max_output_tokens"] = max(
                    aggregated_stats["evaluation_tokens"]["max_output_tokens"],
                    eval_tokens.get("max_output_tokens", 0),
                )
                aggregated_stats["evaluation_tokens"]["max_total_tokens"] = max(
                    aggregated_stats["evaluation_tokens"]["max_total_tokens"],
                    eval_tokens.get("max_total_tokens", 0),
                )

            # Store script-specific data
            aggregated_stats["scripts"][script_name] = {
                "summary": summary,
                "app_tokens": app_tokens,
                "evaluation_tokens": eval_tokens,
            }

            # Aggregate detailed calls
            detailed_calls = token_data.get("detailed_calls", [])
            aggregated_stats["detailed_calls"].extend(detailed_calls)

            logger.debug(
                f"Aggregated {summary.get('call_count', 0)} calls from {token_file.name}"
            )

        except Exception as e:
            logger.warning(f"Failed to process token file {token_file.name}: {e}")

    return aggregated_stats


def _print_aggregated_token_summary(stats: Dict[str, Any]) -> None:
    """
    Print a comprehensive summary of aggregated token usage from all pipeline steps.
    Now includes separate app and evaluation token tracking.

    Args:
        stats: Aggregated token statistics dictionary
    """
    print("\n" + "=" * 80)
    print("=== COMPLETE PIPELINE TOKEN USAGE SUMMARY ===")
    print("=" * 80)

    # App tokens (from chat agents)
    app_tokens = stats.get("app_tokens", {})
    print("\n📱 App Tokens (from chat agents):")
    print(f"  Input tokens: {app_tokens.get('input', 0):,}")
    print(f"  Output tokens: {app_tokens.get('output', 0):,}")
    print(f"  Total tokens: {app_tokens.get('total', 0):,}")
    print(f"  API calls: {app_tokens.get('calls', 0):,}")
    if app_tokens.get("calls", 0) > 0:
        print(f"  Max single request input: {app_tokens.get('max_input', 0):,}")
        print(f"  Max single request output: {app_tokens.get('max_output', 0):,}")
        print(f"  Max single request total: {app_tokens.get('max_total', 0):,}")

    # Evaluation tokens (from evaluation LLM calls)
    eval_tokens = stats.get("evaluation_tokens", {})
    print("\n🔬 Evaluation Tokens (from evaluation LLM calls):")
    print(f"  Input tokens: {eval_tokens.get('total_input_tokens', 0):,}")
    print(f"  Output tokens: {eval_tokens.get('total_output_tokens', 0):,}")
    print(f"  Total tokens: {eval_tokens.get('total_tokens', 0):,}")
    print(f"  API calls: {eval_tokens.get('call_count', 0):,}")
    if eval_tokens.get("call_count", 0) > 0:
        print(f"  Max single request input: {eval_tokens.get('max_input_tokens', 0):,}")
        print(
            f"  Max single request output: {eval_tokens.get('max_output_tokens', 0):,}"
        )
        print(f"  Max single request total: {eval_tokens.get('max_total_tokens', 0):,}")

    # Aggregate by script type
    script_types = {
        "run_conversations": {
            "max_input": 0,
            "max_output": 0,
            "max_total": 0,
            "total_calls": 0,
            "total_tokens": 0,
        },
        "generator": {
            "max_input": 0,
            "max_output": 0,
            "max_total": 0,
            "total_calls": 0,
            "total_tokens": 0,
        },
        "deep_eval": {
            "max_input": 0,
            "max_output": 0,
            "max_total": 0,
            "total_calls": 0,
            "total_tokens": 0,
        },
    }

    # Categorize and aggregate by script type
    for script_name, script_data in stats["scripts"].items():
        summary = script_data.get("summary", {})
        script_type = None

        if script_name.startswith("run_conversations_"):
            script_type = "run_conversations"
        elif script_name.startswith("generator_"):
            script_type = "generator"
        elif script_name.startswith("deep_eval_"):
            script_type = "deep_eval"

        if script_type and summary:
            # Update maximums for this script type
            script_types[script_type]["max_input"] = max(
                script_types[script_type]["max_input"],
                summary.get("max_input_tokens", 0),
            )
            script_types[script_type]["max_output"] = max(
                script_types[script_type]["max_output"],
                summary.get("max_output_tokens", 0),
            )
            script_types[script_type]["max_total"] = max(
                script_types[script_type]["max_total"],
                summary.get("max_total_tokens", 0),
            )
            script_types[script_type]["total_calls"] += summary.get("call_count", 0)
            script_types[script_type]["total_tokens"] += summary.get("total_tokens", 0)

    # Overall totals
    print("\n📊 Combined Pipeline Statistics:")
    print(f"  Total LLM calls: {stats['total_calls']:,}")
    print(f"  Total input tokens: {stats['total_input_tokens']:,}")
    print(f"  Total output tokens: {stats['total_output_tokens']:,}")
    print(f"  Total tokens used: {stats['total_tokens']:,}")
    if stats["total_calls"] > 0:
        print(f"  Max single request input: {stats['max_input_tokens']:,}")
        print(f"  Max single request output: {stats['max_output_tokens']:,}")
        print(f"  Max single request total: {stats['max_total_tokens']:,}")

    if stats["total_calls"] > 0:
        avg_input = stats["total_input_tokens"] / stats["total_calls"]
        avg_output = stats["total_output_tokens"] / stats["total_calls"]
        avg_total = stats["total_tokens"] / stats["total_calls"]
        print(
            f"  Average per call: {avg_input:.1f} input, {avg_output:.1f} output, {avg_total:.1f} total"
        )

    # Show breakdown by script type
    print("\n📈 Maximum Tokens by Script Type:")
    for script_type, data in script_types.items():
        if data["total_calls"] > 0:
            print(f"  {script_type.replace('_', ' ').title()}:")
            print(f"    Max single request input: {data['max_input']:,}")
            print(f"    Max single request output: {data['max_output']:,}")
            print(f"    Max single request total: {data['max_total']:,}")
            print(f"    Total calls: {data['total_calls']:,}")
            print(f"    Total tokens: {data['total_tokens']:,}")

    # Per-script breakdown
    if stats["scripts"]:
        print("\nBreakdown by Script:")
        print("-" * 60)
        for script_name, script_data in stats["scripts"].items():
            summary = script_data.get("summary", {})
            app_tokens_script = script_data.get("app_tokens", {})
            eval_tokens_script = script_data.get("evaluation_tokens", {})

            print(f"  📄 {script_name}:")

            if app_tokens_script:
                print(
                    f"    📱 App tokens: {app_tokens_script.get('total', 0):,} total, {app_tokens_script.get('calls', 0):,} calls"
                )

            if eval_tokens_script:
                print(
                    f"    🔬 Eval tokens: {eval_tokens_script.get('total_tokens', 0):,} total, {eval_tokens_script.get('call_count', 0):,} calls"
                )

            # Show summary if no separate app/eval breakdown available
            if not app_tokens_script and not eval_tokens_script and summary:
                call_count = summary.get("call_count", 0)
                total_tokens = summary.get("total_tokens", 0)
                print(f"    📊 Total: {total_tokens:,} tokens, {call_count:,} calls")

    print("=" * 80)


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
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check known bad conversations - run deepeval on results/known_bad_conversation_results and expect failures",
    )
    parser.add_argument(
        "--test-script",
        type=str,
        default="chat.py",
        help="Name of the test script to execute (default: chat.py)",
    )
    parser.add_argument(
        "--no-employee-id",
        action="store_true",
        help="Exclude employee ID-related checks in evaluation metrics",
    )
    return parser.parse_args()


def run_check_known_bad_conversations(timeout: int = 600) -> int:
    """
    Check known bad conversations by running deepeval on them.

    This function runs deepeval on the conversations in results/known_bad_conversation_results
    and expects them to fail. It returns a non-zero exit code unless all conversations
    report errors as expected.

    Args:
        timeout: Timeout in seconds for deepeval execution

    Returns:
        Exit code (0 if all known bad conversations failed as expected, 1 otherwise)
    """
    logger.info("🔍 Starting Check of Known Bad Conversations")
    logger.info("=" * 80)

    check_start_time = time.time()

    # Check if the known bad conversations directory exists
    known_bad_dir = Path("results/known_bad_conversation_results")
    if not known_bad_dir.exists():
        logger.error(f"❌ Directory {known_bad_dir} does not exist")
        return 1

    # Count the known bad conversation files
    known_bad_files = list(known_bad_dir.glob("*.json"))
    if not known_bad_files:
        logger.error(f"❌ No JSON files found in {known_bad_dir}")
        return 1

    logger.info(
        f"📁 Found {len(known_bad_files)} known bad conversation files to check"
    )
    logger.info("-" * 60)

    # Run deepeval on the known bad conversations
    logger.info("📊 Running deepeval on known bad conversations...")
    deep_eval_args = ["--results-dir", "results/known_bad_conversation_results"]
    # For the check option, we want to run deep_eval and analyze the results
    # even if it returns a non-zero exit code (which indicates it found issues)
    run_script("deep_eval.py", args=deep_eval_args, timeout=timeout)
    logger.info("📊 DeepEval completed, analyzing results...")

    # Check the results to see if the conversations failed as expected
    deep_eval_results_dir = Path("results/deep_eval_results")
    if not deep_eval_results_dir.exists():
        logger.error("❌ DeepEval results directory not found")
        return 1

    # Look for the combined results file
    combined_results_file = deep_eval_results_dir / "deepeval_all_results.json"
    if not combined_results_file.exists():
        logger.error("❌ Combined DeepEval results file not found")
        return 1

    # Parse the results to check if known bad conversations failed
    try:
        with open(combined_results_file, "r") as f:
            results_data = json.load(f)
    except Exception as e:
        logger.error(f"❌ Failed to parse DeepEval results: {e}")
        return 1

    # Analyze the results - the structure is different than expected
    total_known_bad = len(known_bad_files)
    successful_evaluations = 0
    failed_evaluations = []
    all_results = []

    # The results file has a different structure with 'successful_evaluations' array
    if "successful_evaluations" in results_data:
        for result in results_data["successful_evaluations"]:
            filename = result.get("filename", "")
            # Check if this is one of our known bad conversations
            if any(bad_file.stem in filename for bad_file in known_bad_files):
                successful_evaluations += 1
                all_results.append(result)

    # Check for failed evaluations
    if "failed_evaluations" in results_data:
        for result in results_data["failed_evaluations"]:
            filename = result.get("filename", "")
            # Check if this is one of our known bad conversations
            if any(bad_file.stem in filename for bad_file in known_bad_files):
                failed_evaluations.append(result)

    # Check results
    check_duration = time.time() - check_start_time
    logger.info("=" * 80)
    logger.info(f"🏁 Check Complete (Duration: {check_duration:.2f}s)")

    # Print summary similar to deep_eval_summary
    print(f"\n{'=' * 80}")
    print("🔍 KNOWN BAD CONVERSATIONS CHECK RESULTS")
    print("=" * 80)

    print("📊 OVERVIEW:")
    print(f"   • Total known bad conversations: {total_known_bad}")
    print(f"   • Successfully evaluated: {successful_evaluations}")
    print(f"   • LLM evaluation failures: {len(failed_evaluations)}")

    if successful_evaluations > 0:
        # Calculate metric statistics for successfully evaluated conversations
        total_metrics = 0
        total_passed_metrics = 0
        metric_stats = {}

        for result in all_results:
            metrics_results = result.get("metrics", [])
            for metric in metrics_results:
                metric_name = metric.get("metric", "Unknown")
                if metric_name not in metric_stats:
                    metric_stats[metric_name] = {"passed": 0, "total": 0}

                metric_stats[metric_name]["total"] += 1
                total_metrics += 1

                if metric.get("success", False):
                    metric_stats[metric_name]["passed"] += 1
                    total_passed_metrics += 1

        overall_metric_pass_rate = (
            (total_passed_metrics / total_metrics * 100) if total_metrics > 0 else 0
        )
        print(
            f"   • Overall metric pass rate: {total_passed_metrics}/{total_metrics} ({overall_metric_pass_rate:.1f}%)"
        )

        # Show individual metric pass rates
        if metric_stats:
            print("   • Individual metric performance:")
            for metric_name, stats in metric_stats.items():
                rate = (
                    (stats["passed"] / stats["total"] * 100)
                    if stats["total"] > 0
                    else 0
                )
                status = "✅" if rate >= 80 else "⚠️" if rate >= 50 else "❌"
                print(
                    f"     {status} {metric_name}: {stats['passed']}/{stats['total']} ({rate:.1f}%)"
                )

    # Show conversation results
    print(f"\n{'─' * 50}")
    print("\n🏁 CONVERSATION RESULTS:")

    passing_conversations = []
    failing_conversations = []

    if all_results:
        for result in all_results:
            filename = result.get("filename", "Unknown")
            metrics_results = result.get("metrics", [])

            if metrics_results:
                # Check if all metrics failed for this conversation (as expected for known bad)
                passed_metrics = [m for m in metrics_results if m.get("success", False)]
                failed_metrics = [
                    m for m in metrics_results if not m.get("success", False)
                ]

                # For known bad conversations, we expect most/all metrics to fail
                conversation_failed_as_expected = len(failed_metrics) > len(
                    passed_metrics
                )

                # Categorize conversations
                # A conversation is "passing" only if ALL metrics passed (no failures)
                # A conversation is "failing" if ANY metric failed
                if len(failed_metrics) == 0:
                    passing_conversations.append(
                        (filename, passed_metrics, metrics_results)
                    )
                else:
                    failing_conversations.append(
                        (filename, failed_metrics, metrics_results)
                    )

                status_icon = "❌" if conversation_failed_as_expected else "⚠️"
                print(
                    f"   {status_icon} {filename}: {len(failed_metrics)}/{len(metrics_results)} metrics failed (as expected: {conversation_failed_as_expected})"
                )

                # Show failed metrics details
                if failed_metrics:
                    print("      Failed metrics:")
                    for metric in failed_metrics:
                        metric_name = metric.get("metric", "Unknown")
                        score = metric.get("score", 0)
                        reason = metric.get("reason", "No reason provided")
                        print(
                            f"        • {metric_name} (score: {score:.3f}) - {reason}"
                        )
            else:
                print(f"   ⚠️  {filename}: No metric data available")

    # Show summary of passing vs failing conversations
    print(f"\n{'─' * 50}")
    print("\n📊 CONVERSATION SUMMARY:")
    print(f"   • Total conversations: {len(all_results)}")
    print(f"   • Passing conversations: {len(passing_conversations)}")
    print(f"   • Failing conversations: {len(failing_conversations)}")

    if passing_conversations:
        print("\n✅ PASSING CONVERSATIONS:")
        for filename, passed_metrics, total_metrics in passing_conversations:
            pass_rate = len(passed_metrics) / len(total_metrics) * 100
            print(
                f"   • {filename}: {len(passed_metrics)}/{len(total_metrics)} metrics passed ({pass_rate:.1f}%)"
            )

    if failing_conversations:
        print("\n❌ FAILING CONVERSATIONS:")
        for filename, failed_metrics, total_metrics in failing_conversations:
            fail_rate = len(failed_metrics) / len(total_metrics) * 100
            print(
                f"   • {filename}: {len(failed_metrics)}/{len(total_metrics)} metrics failed ({fail_rate:.1f}%)"
            )

    # Show LLM evaluation failures
    if failed_evaluations:
        print("\n🔥 LLM EVALUATION FAILURES:")
        print(f"   • Total LLM failures: {len(failed_evaluations)}")
        for failure in failed_evaluations:
            filename = failure.get("filename", "Unknown")
            error_type = failure.get("error_type", "Unknown error")
            print(f"   ❌ {filename}: {error_type}")

    # Overall status
    # For known bad conversations, we want them to fail the metrics (not pass)
    # The check passes if:
    # 1. All known bad conversations were evaluated successfully
    # 2. At least some metrics in each conversation failed (as expected for bad conversations)
    #
    # A conversation is considered "failing as expected" if it has at least one failed metric
    conversations_failing_as_expected = len(failing_conversations)

    if (
        successful_evaluations == total_known_bad
        and conversations_failing_as_expected > 0
    ):
        print(
            f"\n🎉 OVERALL RESULT: {conversations_failing_as_expected}/{total_known_bad} KNOWN BAD CONVERSATIONS FAILED AS EXPECTED"
        )
        exit_code = 0
    else:
        print("\n⚠️  OVERALL RESULT: NOT ALL KNOWN BAD CONVERSATIONS FAILED AS EXPECTED")
        exit_code = 1

    # Output files
    print("=" * 80)
    print("\n📁 OUTPUT FILES:")
    if successful_evaluations > 0:
        print(f"   • Individual results: {deep_eval_results_dir}/deepeval_*.json")
        print(
            f"   • Combined results: {deep_eval_results_dir}/deepeval_all_results.json"
        )
        print(f"   • Results directory: {deep_eval_results_dir}/")
    else:
        print("   • No output files generated due to evaluation failures")

    return exit_code


def run_evaluation_pipeline(
    num_conversations: int = 20,
    timeout: int = 600,
    max_turns: int = 20,
    test_script: str = "chat.py",
    no_employee_id: bool = False,
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
        test_script: Name of the test script to execute

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
    run_conversations_args = ["--test-script", test_script]
    if no_employee_id:
        run_conversations_args.append("--no-employee-id")
    if not run_script(
        "run_conversations.py", args=run_conversations_args, timeout=timeout
    ):
        failed_steps.append("run_conversations.py")
        logger.error("❌ Step 1 failed - continuing with remaining steps")
    else:
        logger.info("✅ Step 1 completed successfully")

    logger.info("-" * 60)

    # Step 2: Generate additional conversations
    logger.info(
        f"🤖 Step 2/3: Generating {num_conversations} additional test conversations..."
    )
    generator_args = [
        str(num_conversations),
        "--max-turns",
        str(max_turns),
        "--test-script",
        test_script,
    ]
    if not run_script("generator.py", args=generator_args, timeout=timeout):
        failed_steps.append("generator.py")
        logger.error("❌ Step 2 failed - continuing with remaining steps")
    else:
        logger.info("✅ Step 2 completed successfully")

    logger.info("-" * 60)

    # Step 3: Run deepeval evaluation
    logger.info("📊 Step 3/3: Running deepeval evaluation...")
    deep_eval_args = []
    if no_employee_id:
        deep_eval_args.append("--no-employee-id")
    if not run_script("deep_eval.py", args=deep_eval_args, timeout=timeout):
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

    # Aggregate and display token usage from all pipeline steps
    logger.info("📊 Aggregating token usage statistics...")
    try:
        aggregated_stats = _aggregate_token_usage()
        _print_aggregated_token_summary(aggregated_stats)

        # Save aggregated token stats to file
        if aggregated_stats["total_calls"] > 0:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            aggregated_file = (
                Path("results/token_usage") / f"pipeline_aggregated_{timestamp}.json"
            )
            aggregated_file.parent.mkdir(exist_ok=True)

            with open(aggregated_file, "w") as f:
                json.dump(aggregated_stats, f, indent=2)

            logger.info(f"💾 Aggregated token usage saved to: {aggregated_file}")

    except Exception as e:
        logger.warning(f"⚠️  Failed to aggregate token usage: {e}")

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

        # Check if help was requested
        if len(sys.argv) > 1 and any(arg in ["-h", "--help"] for arg in sys.argv):
            return 0

        if args.check:
            return run_check_known_bad_conversations(timeout=args.timeout)
        else:
            return run_evaluation_pipeline(
                num_conversations=args.num_conversations,
                timeout=args.timeout,
                max_turns=args.max_turns,
                test_script=args.test_script,
                no_employee_id=args.no_employee_id,
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
