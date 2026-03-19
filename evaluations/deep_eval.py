#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from deepeval.evaluate import DisplayConfig, evaluate
from deepeval.test_case import ConversationalTestCase, Turn
from deepeval.test_run import global_test_run_manager
from flow_registry import get_flow_paths, list_flows, load_flow, load_flow_metrics
from get_deepeval_metrics import get_metrics
from helpers.copy_context import copy_context_files, copy_flow_context
from helpers.custom_llm import CustomLLM, get_api_configuration
from helpers.deep_eval_summary import print_final_summary
from helpers.extract_deepeval_metrics import extract_metrics_from_results
from helpers.load_conversation_context import load_context_for_file

# Configure logging for evaluation process tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _no_op_wrap_up_test_run(*args: Any, **kwargs: Any) -> None:
    """
    No-operation function to override DeepEval's default wrap_up_test_run behavior.

    This function prevents DeepEval from attempting to connect to online services
    and suggesting user login

    Args:
        *args: Variable length argument list (ignored)
        **kwargs: Arbitrary keyword arguments (ignored)
    """
    pass


# Override DeepEval's default behavior to prevent online connectivity
global_test_run_manager.wrap_up_test_run = _no_op_wrap_up_test_run  # type: ignore[method-assign]

_DEFAULT_CHATBOT_ROLE = """You are an IT Support Agent specializing in hardware replacement.

Your responsibilities:
1. Determine if the authenticated user's laptop is eligible for replacement based on company policy
2. Clearly communicate the eligibility status and policy reasons to the user
3. If the user is NOT eligible:
   - Inform them of their ineligibility with the policy reason (e.g., laptop age)
   - Provide clear, factual information that proceeding may require additional approvals or be rejected
   - Allow them to continue with the laptop selection process if they choose to
4. Guide the user through laptop selection
5. After the user selects a laptop, ALWAYS ask for explicit confirmation before creating the ServiceNow ticket (e.g., "Would you like to proceed with creating a ServiceNow ticket for this laptop?")
6. Only create the ServiceNow ticket AFTER the user confirms they want to proceed
7. After creating the ticket, provide the ticket number and next steps
8. Maintain a professional, helpful, and informative tone throughout

Note: Providing clear, factual information about potential rejection or additional approvals is sufficient. You do not need to be overly cautionary or repeatedly emphasize warnings. Always confirm with the user before creating tickets."""


def _convert_to_turns(conversation_data: List[Dict[str, str]]) -> List[Turn]:
    """
    Convert conversation data from role/content format to DeepEval Turn objects.

    This function transforms conversation data from a list of dictionaries containing
    'role' and 'content' keys into DeepEval Turn objects that can be used for
    conversational evaluation. Empty content is automatically filtered out.

    Args:
        conversation_data: List of dictionaries with 'role' and 'content' keys
                          representing the conversation turns

    Returns:
        List[Turn]: List of DeepEval Turn objects ready for evaluation
    """
    turns = []
    for turn_data in conversation_data:
        role = turn_data.get("role", "")
        content = turn_data.get("content", "")

        # Skip empty content to avoid creating invalid turns
        if not content.strip():
            continue

        # Ensure role is valid for Turn
        if role not in ["user", "assistant"]:
            role = "user"  # Default to user if role is invalid

        turns.append(Turn(role=role, content=content))  # type: ignore[arg-type]

    return turns


def _evaluate_conversations(
    api_endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    results_dir: str = "results/conversation_results",
    output_dir: str = "results/deep_eval_results",
    context_dir: Optional[str] = None,
    validate_full_laptop_details: bool = True,
    use_structured_output: bool = False,
    metrics: Optional[List[Any]] = None,
    chatbot_role: Optional[str] = None,
    default_context_dir: Optional[str] = None,
) -> int:
    """
    Main evaluation function that processes conversation files and generates assessment reports.

    This function orchestrates the complete evaluation workflow:
    1. Configures the LLM model for evaluation
    2. Loads conversation files from the results directory
    3. Applies evaluation metrics
    4. Generates individual and combined evaluation reports
    5. Provides detailed pass/fail analysis with scoring

    The function processes each conversation file independently and terminates
    on critical errors to ensure data integrity.

    Args:
        api_endpoint: Optional custom OpenAI-compatible API endpoint URL
        api_key: API key for the LLM service. Falls back to environment variables
        results_dir: Path to directory containing conversation JSON files to evaluate
        output_dir: Path to directory where evaluation results will be saved
        context_dir: Optional path to directory with context files for conversations
        validate_full_laptop_details: Enable validation of all 15 laptop specification fields
        use_structured_output: Enable structured output with Pydantic schema validation and retries
        metrics: Pre-loaded metrics list. If None, uses default get_metrics() with a new model.
        chatbot_role: Override for the chatbot role description. If None, uses the default role.
        default_context_dir: Override for the default context directory. If None, uses the standard path.

    Returns:
        int: Exit code (0 for success, 1 for failure) indicating evaluation outcome
    """
    if metrics is None:
        api_key_found, current_endpoint, model_name = get_api_configuration(
            api_endpoint, api_key
        )
        if not api_key_found:
            logger.error("No API key configured. Cannot proceed with evaluation.")
            return 1

        assert api_key_found is not None
        custom_model = CustomLLM(
            api_key=api_key_found,
            base_url=current_endpoint or "",
            model_name=model_name,
            use_structured_output=use_structured_output,
        )
        if not custom_model:
            logger.error(
                "Could not create model object. Cannot proceed with evaluation."
            )
            return 1

        metrics = get_metrics(
            custom_model, validate_full_laptop_details=validate_full_laptop_details
        )

    effective_chatbot_role = (
        chatbot_role if chatbot_role is not None else _DEFAULT_CHATBOT_ROLE
    )

    if not os.path.exists(results_dir):
        logger.error(f"Results directory {results_dir} does not exist")
        return 1

    os.makedirs(output_dir, exist_ok=True)

    # Discover all conversation files to evaluate
    json_files = [f for f in os.listdir(results_dir) if f.endswith(".json")]

    if not json_files:
        logger.warning(f"No JSON files found in {results_dir}")
        return 0

    print(f"Found {len(json_files)} conversation files to evaluate")

    # Initialize tracking for evaluation results and success metrics
    all_results = []
    failed_evaluations = []
    successful_evaluations = 0

    # Process each conversation file individually
    for filename in json_files:
        file_path = os.path.join(results_dir, filename)

        try:
            print(f"Processing {filename}")
            # Load relevant context data for this specific conversation
            context_for_file = load_context_for_file(
                filename, context_dir, default_context_dir
            )

            # Load single conversation
            with open(file_path, "r", encoding="utf-8") as f:
                file_data = json.load(f)

            # Expected format: object with metadata and conversation
            if not isinstance(file_data, dict) or "conversation" not in file_data:
                logger.error(
                    f"Invalid conversation format in {filename} - expected object with metadata and conversation"
                )
                continue

            conversation_data = file_data["conversation"]
            authoritative_user_id = file_data.get("metadata", {}).get(
                "authoritative_user_id"
            )

            if not authoritative_user_id:
                logger.error(
                    f"No authoritative_user_id found in metadata for {filename}"
                )
                continue

            logger.info(
                f"Processing {filename} with authoritative_user_id: {authoritative_user_id}"
            )

            # Convert to turns
            turns = _convert_to_turns(conversation_data)

            if len(turns) < 2:
                logger.warning(
                    f"Skipping {filename} - insufficient conversation turns ({
                        len(turns)})"
                )
                continue

            # Build test case context starting with conversation identifier
            test_case_context = [f"Laptop refresh conversation from {filename}"]

            # Add retrieval context if available
            if context_for_file:
                test_case_context.extend(context_for_file)
                logger.debug(
                    f"Using {len(context_for_file)} context item(s) for {filename}"
                )

            # Note: DeepEval's type hints incorrectly say context is Optional[str]
            # but the runtime implementation in __post_init__ expects List[str]
            test_case = ConversationalTestCase(
                turns=turns,
                context=test_case_context if test_case_context else None,  # type: ignore[arg-type]
                chatbot_role=effective_chatbot_role,
            )

            # Execute evaluation with suppressed output for cleaner reporting
            display_config = DisplayConfig(print_results=False)
            results = evaluate(
                test_cases=[test_case], metrics=metrics, display_config=display_config
            )

            # Store results with basic tracking for summary
            conversation_result: dict[str, Any] = {
                "filename": filename,
                "conversation_turns": len(turns),
                "evaluation_results": results,
                "metrics": [],
                "total_metrics": len(metrics),
            }

            # Extract and process detailed metric information for reporting
            try:
                extracted_metrics = extract_metrics_from_results(
                    results, filename, metrics
                )
                if extracted_metrics:
                    conversation_result["metrics"].extend(extracted_metrics)

            except Exception:
                logger.error(f"Skipping {filename} due to metric extraction failure")
                continue

            all_results.append(conversation_result)
            successful_evaluations += 1

            # Display formatted results for this conversation
            print(f"\n{'=' * 60}")
            print(f"RESULTS FOR: {filename}")
            print("=" * 60)

            # Show detailed metric breakdown
            if conversation_result["metrics"]:
                print("📊 METRIC BREAKDOWN:")
                for metric in conversation_result["metrics"]:
                    status = "✅ PASS" if metric["success"] else "❌ FAIL"
                    print(
                        f"   {status} {
                            metric['metric']}: {
                            metric['score']:.3f} (threshold: {
                            metric.get(
                                'threshold', 0.5)})"
                    )
                    if not metric["success"]:
                        print(
                            f"      Reason: {
                                metric['reason'][
                                    :200]}{
                                '...' if len(
                                    metric['reason']) > 200 else ''}"
                        )

                # Calculate and show pass rate
                passed = sum(1 for m in conversation_result["metrics"] if m["success"])
                total = len(conversation_result["metrics"])
                rate = (passed / total * 100) if total > 0 else 0
                print(f"\n   📈 PASS RATE: {passed}/{total} ({rate:.1f}%)")
            else:
                print("⚠️  No detailed metrics available")

            # Save individual results to separate file
            individual_output_file = os.path.join(output_dir, f"deepeval_{filename}")
            try:
                with open(individual_output_file, "w", encoding="utf-8") as f:
                    json.dump(
                        conversation_result,
                        f,
                        indent=2,
                        ensure_ascii=False,
                        default=str,
                    )
                logger.debug(f"Individual results saved to {individual_output_file}")
            except Exception as e:
                logger.error(f"Failed to save individual results for {filename}: {e}")

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse JSON in {filename}: {e}"
            logger.error(error_msg)
            print(f"\n{'=' * 60}")
            print("❌ EVALUATION STOPPED DUE TO ERROR")
            print("=" * 60)
            print(f"📊 JSON Parse Error: {error_msg}")
            print("=" * 60)
            print(
                "\n🛑 Program terminated due to error. Please fix the issue and try again."
            )
            sys.exit(1)

        except Exception as e:
            # Determine the specific error type for better reporting
            error_reason = str(e)
            if "Connection error" in error_reason:
                error_type = "Connection error - unable to reach LLM endpoint"
            elif "401" in error_reason or "Unauthorized" in error_reason:
                error_type = "Authentication error - invalid API key"
            elif "timeout" in error_reason.lower():
                error_type = "Timeout error - LLM endpoint not responding"
            else:
                error_type = f"Evaluation error: {error_reason}"

            # Record the failed evaluation and continue with next conversation
            failed_evaluation = {
                "filename": filename,
                "error_type": error_type,
                "error_details": str(e),
                "failure_reason": "LLM evaluator problem",
            }
            failed_evaluations.append(failed_evaluation)

            logger.error(f"Error processing {filename}: {e}")
            print(f"\n{'=' * 60}")
            print("❌ EVALUATION FAILED FOR CONVERSATION")
            print("=" * 60)
            print(f"📊 File: {filename}")
            print(f"📊 Error: {error_type}")
            print("📊 Continuing with next conversation...")
            print("=" * 60)
            continue

    # Print enhanced final summary and get exit code
    exit_code = print_final_summary(
        len(json_files),
        successful_evaluations,
        all_results,
        failed_evaluations,
        output_dir,
    )

    if all_results or failed_evaluations:
        # Save combined results to output directory including failed evaluations
        combined_output_file = os.path.join(output_dir, "deepeval_all_results.json")
        try:
            combined_results = {
                "successful_evaluations": all_results,
                "failed_evaluations": failed_evaluations,
                "summary": {
                    "total_files": len(json_files),
                    "successful_count": successful_evaluations,
                    "failed_count": len(failed_evaluations),
                },
            }
            with open(combined_output_file, "w", encoding="utf-8") as f:
                json.dump(
                    combined_results, f, indent=2, ensure_ascii=False, default=str
                )
        except Exception as e:
            logger.error(f"Failed to save combined results: {e}")

    print("=" * 80)

    return exit_code


def _parse_arguments() -> argparse.Namespace:
    """
    Parse and validate command-line arguments for the evaluation script.

    Configures argument parser with all available options for customizing
    the evaluation process, including API configuration, directory paths,
    and context file locations.

    Returns:
        argparse.Namespace: Parsed command-line arguments with the following attributes:
            - api_endpoint: Custom API endpoint URL
            - api_key: API key for authentication
            - results_dir: Directory containing conversation files
            - output_dir: Directory for evaluation results
            - context_dir: Directory containing context files
    """
    parser = argparse.ArgumentParser(
        description="Evaluate conversations using deepeval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--api-endpoint",
        type=str,
        help="Custom OpenAI API endpoint URL (e.g., Azure OpenAI endpoint)",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="API key or token. If not provided, will use LLM_API_TOKEN or OPENAI_API_KEY environment variable",
    )

    parser.add_argument(
        "--flow",
        type=str,
        default=None,
        metavar="FLOW_NAME",
        help="Run evaluation for a specific flow (e.g., ticket_laptop_refresh). "
        "Uses flow-specific directories, metrics, and chatbot role.",
    )

    parser.add_argument(
        "--all-flows",
        action="store_true",
        default=False,
        help="Run evaluation for the default mode AND all registered flows sequentially.",
    )

    parser.add_argument(
        "--known-bad",
        action="store_true",
        default=False,
        help="Evaluate known-bad conversations instead of generated conversations. "
        "For default mode uses results/known_bad_conversation_results/. "
        "For flows uses flows/{name}/known_bad_conversations/.",
    )

    parser.add_argument(
        "--results-dir",
        type=str,
        default=None,
        help="Directory containing conversation result files. "
        "Overrides the default path for the selected mode.",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save deepeval results and reports. "
        "Overrides the default path for the selected mode.",
    )

    parser.add_argument(
        "--context-dir",
        type=str,
        help="Directory containing context files (matched by conversation filename). Note: 'conversations_config/default_context/' and 'conversations_config/conversation_context/' directories are automatically used if they exist.",
    )

    parser.add_argument(
        "--validate-full-laptop-details",
        action="store_true",
        dest="validate_full_laptop_details",
        default=True,
        help="Enable validation that all 15 laptop specification fields are presented (default: True). "
        "The 'Correct laptop options for user location' metric verifies "
        "complete laptop specifications including: Manufacturer, Model, ServiceNow Code, Target User, "
        "Cost, Operating System, Display Size, Display Resolution, Graphics Card, Minimum Storage, "
        "Weight, Ports, Minimum Processor, Minimum Memory, and Dimensions.",
    )
    parser.add_argument(
        "--no-validate-full-laptop-details",
        action="store_false",
        dest="validate_full_laptop_details",
        help="Disable validation of the 15 laptop specification fields.",
    )

    parser.add_argument(
        "--use-structured-output",
        action="store_true",
        default=False,
        help="Enable structured output with Pydantic schema validation and retries. "
        "Recommended for models with unreliable JSON formatting (e.g., Google Gemini).",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_arguments()

    if args.flow and args.all_flows:
        print("Error: --flow and --all-flows are mutually exclusive")
        sys.exit(1)

    final_api_endpoint = args.api_endpoint or os.getenv("LLM_URL")
    final_api_key = args.api_key or os.getenv("LLM_API_TOKEN")

    # Print configuration
    print("=" * 80)
    print("DEEPEVAL CONVERSATION EVALUATION")
    print("=" * 80)

    if args.api_key:
        print("API key: Provided via command line")
    elif os.getenv("LLM_API_TOKEN"):
        print("API key: Using environment variable LLM_API_TOKEN")
    else:
        print("API key: Not configured - evaluation may fail")

    if os.getenv("LLM_ID"):
        print(f"LLM Model ID: {os.getenv('LLM_ID')}")

    print(f"Custom endpoint: {final_api_endpoint}")

    if args.use_structured_output:
        print(
            "Structured output: ENABLED (using Pydantic schema validation with retries)"
        )
    else:
        print("Structured output: DISABLED (using standard JSON mode)")

    if args.flow:
        print(f"Mode: single flow '{args.flow}'")
    elif args.all_flows:
        print(f"Mode: all flows (default + {list_flows()})")
    else:
        print("Mode: default")

    if args.known_bad:
        print("Evaluating: known-bad conversations")

    print("=" * 80)
    print("")

    # Determine which evaluations to run
    run_default = not args.flow  # default runs unless a specific flow is selected
    flows_to_run = (
        [args.flow] if args.flow else (list_flows() if args.all_flows else [])
    )

    overall_exit_code = 0

    # --- Default evaluation ---
    if run_default:
        copy_context_files()

        if args.known_bad:
            results_dir = args.results_dir or "results/known_bad_conversation_results"
            output_dir = args.output_dir or "results/known_bad_eval_results"
        else:
            results_dir = args.results_dir or "results/conversation_results"
            output_dir = args.output_dir or "results/deep_eval_results"

        print(f"Running default evaluation: {results_dir} -> {output_dir}")
        exit_code = _evaluate_conversations(
            api_endpoint=final_api_endpoint,
            api_key=final_api_key,
            results_dir=results_dir,
            output_dir=output_dir,
            context_dir=args.context_dir,
            validate_full_laptop_details=args.validate_full_laptop_details,
            use_structured_output=args.use_structured_output,
        )
        overall_exit_code = max(overall_exit_code, exit_code)

    # --- Flow evaluations ---
    for flow_name in flows_to_run:
        copy_flow_context(flow_name)

        flow_module = load_flow(flow_name)
        flow_paths = get_flow_paths(flow_name)

        if args.known_bad:
            results_dir = args.results_dir or str(flow_paths.known_bad_dir)
            output_dir = args.output_dir or str(flow_paths.results_known_bad_dir)
        else:
            results_dir = args.results_dir or str(flow_paths.results_conv_dir)
            output_dir = args.output_dir or str(flow_paths.results_eval_dir)

        # Create model and load flow-specific metrics
        api_key_found, current_endpoint, model_name = get_api_configuration(
            final_api_endpoint, final_api_key
        )
        if not api_key_found:
            logger.error(f"No API key configured for flow '{flow_name}'. Skipping.")
            overall_exit_code = max(overall_exit_code, 1)
            continue

        assert api_key_found is not None
        custom_model = CustomLLM(
            api_key=api_key_found,
            base_url=current_endpoint or "",
            model_name=model_name,
            use_structured_output=args.use_structured_output,
        )

        flow_metrics_module = load_flow_metrics(flow_name)
        flow_metrics = flow_metrics_module.get_metrics(
            custom_model,
            validate_full_laptop_details=args.validate_full_laptop_details,
        )
        flow_chatbot_role = getattr(flow_module, "CHATBOT_ROLE", None)
        flow_context_dir = str(flow_paths.context_dir)

        print(f"Running flow '{flow_name}': {results_dir} -> {output_dir}")
        exit_code = _evaluate_conversations(
            api_endpoint=final_api_endpoint,
            api_key=final_api_key,
            results_dir=results_dir,
            output_dir=output_dir,
            context_dir=args.context_dir,
            validate_full_laptop_details=args.validate_full_laptop_details,
            use_structured_output=args.use_structured_output,
            metrics=flow_metrics,
            chatbot_role=flow_chatbot_role,
            default_context_dir=flow_context_dir,
        )
        overall_exit_code = max(overall_exit_code, exit_code)

    # Print token usage summary using shared function
    print("\n" + "=" * 80)
    from helpers.token_counter import print_token_summary

    print_token_summary(
        app_tokens=None,  # deep_eval.py only uses evaluation tokens
        save_file_prefix="deep_eval",
    )

    print("=" * 80)

    # Exit with appropriate code: 0 for success, 1 for failure
    sys.exit(overall_exit_code)
