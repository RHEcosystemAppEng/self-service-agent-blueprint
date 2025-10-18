#!/usr/bin/env python3

from typing import Any, Dict, List


def print_final_summary(
    total_files: int,
    successful_evaluations: int,
    all_results: List[Dict[str, Any]],
    failed_evaluations: List[Dict[str, Any]] | None = None,
    output_dir: str = "deep_eval_results",
) -> int:
    """
    Print a comprehensive, human-readable evaluation summary.

    Generates a detailed summary of deepeval conversation evaluation results,
    including overall statistics, individual metric performance, conversation
    pass/fail status, LLM evaluation failures, and output file locations.
    The summary is formatted with emojis and visual separators for better readability.

    Args:
        total_files: Total number of conversation files that were evaluated
        successful_evaluations: Number of evaluations that completed successfully
        all_results: List of evaluation result dictionaries containing metrics
        failed_evaluations: Optional list of evaluation failure dictionaries due to LLM issues
        output_dir: Directory where evaluation results were saved

    Returns:
        Exit code (0 for success, 1 for failures)

    The function calculates:
    - Overall success rate
    - Individual metric pass rates
    - Per-conversation results
    - Failed metric details for debugging
    - LLM evaluation failure details
    """
    failed_eval_count = total_files - successful_evaluations
    success_rate = (
        (successful_evaluations / total_files * 100) if total_files > 0 else 0
    )

    print(f"\n{'=' * 80}")
    print("🏆 DEEPEVAL CONVERSATION EVALUATION RESULTS")
    print("=" * 80)

    # Overview stats
    print("📊 OVERVIEW:")
    print(f"   • Total conversations evaluated: {total_files}")
    print(f"   • Successful evaluations: {successful_evaluations}")
    print(f"   • Failed evaluations: {failed_eval_count}")
    print(f"   • Success rate: {success_rate:.1f}%")

    # Calculate overall metric statistics
    if all_results:
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
            f"   • Overall metric pass rate: {total_passed_metrics}/{total_metrics} ({
                overall_metric_pass_rate:.1f}%)"
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
                    f"     {status} {metric_name}: {
                        stats['passed']}/{
                        stats['total']} ({
                        rate:.1f}%)"
                )

    # Status indicator
    if successful_evaluations == total_files:
        print("   • Status: ✅ ALL EVALUATIONS PASSED")
    elif successful_evaluations > 0:
        print("   • Status: ⚠️  PARTIAL SUCCESS")
    else:
        print("   • Status: ❌ ALL EVALUATIONS FAILED")

    print(f"\n{'─' * 50}")

    # Add conversation pass/fail summary
    print("\n🏁 CONVERSATION SUMMARY:")
    all_conversations_passed = True

    if all_results:
        for result in all_results:
            filename = result.get("filename", "Unknown")
            metrics_results = result.get("metrics", [])

            if metrics_results:
                # Check if all metrics passed for this conversation
                passed_metrics = [m for m in metrics_results if m.get("success", False)]
                failed_metrics = [
                    m for m in metrics_results if not m.get("success", False)
                ]

                conversation_passed = len(failed_metrics) == 0
                if not conversation_passed:
                    all_conversations_passed = False

                status_icon = "✅" if conversation_passed else "❌"
                print(
                    f"   {status_icon} {filename}: {
                        len(passed_metrics)}/{
                        len(metrics_results)} metrics passed"
                )

                # Show failed metrics for failed conversations
                if not conversation_passed:
                    print("      Failed metrics:")
                    for metric in failed_metrics:
                        metric_name = metric.get("metric", "Unknown")
                        score = metric.get("score", 0)
                        reason = metric.get("reason", "No reason provided")
                        print(
                            f"        • {metric_name} (score: {score:.3f}) - {reason}"
                        )
            else:
                # No metrics data available
                all_conversations_passed = False
                print(f"   ⚠️  {filename}: No metric data available")

    # Show LLM evaluation failures
    if failed_evaluations:
        print("\n🔥 LLM EVALUATION FAILURES:")
        print(f"   • Total LLM failures: {len(failed_evaluations)}")
        for failure in failed_evaluations:
            filename = failure.get("filename", "Unknown")
            error_type = failure.get("error_type", "Unknown error")
            print(f"   ❌ {filename}: {error_type}")
        all_conversations_passed = False

    # Overall status
    if all_conversations_passed and successful_evaluations == total_files:
        print("\n🎉 OVERALL RESULT: ALL CONVERSATIONS PASSED")
        exit_code = 0
    else:
        failed_count = sum(
            1
            for result in all_results
            if not all(m.get("success", False) for m in result.get("metrics", []))
        )
        print(f"\n⚠️  OVERALL RESULT: {failed_count} CONVERSATION(S) FAILED")
        exit_code = 1

    # Output files
    print("=" * 80)
    print("\n📁 OUTPUT FILES:")
    if successful_evaluations > 0:
        print(f"   • Individual results: {output_dir}/deepeval_*.json")
        print(f"   • Combined results: {output_dir}/deepeval_all_results.json")
        print(f"   • Results directory: {output_dir}/")
    else:
        print("   • No output files generated due to evaluation failures")

    return exit_code
