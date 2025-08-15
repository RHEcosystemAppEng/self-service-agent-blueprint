#!/usr/bin/env python3
"""
Helper functions for extracting metrics from deepeval results.

This module provides functionality to parse deepeval evaluation results
and extract metric information in a standardized format.
"""

import logging
import traceback
from typing import Any, Dict, List, Optional

# Configure logging
logger = logging.getLogger(__name__)


def extract_metrics_from_results(
    results: Any, filename: str, metrics: List[Any]
) -> Optional[List[Dict[str, Any]]]:
    """
    Extract detailed metric information from deepeval results.

    Args:
        results: The deepeval results object
        filename: Name of the conversation file being processed
        metrics: List of metrics that were used for evaluation

    Returns:
        List of metric dictionaries or None if extraction fails

    Raises:
        Exception: If metric extraction fails completely
    """
    extracted_metrics = []

    try:
        logger.debug(f"Processing results for {filename}: {type(results)}")
        logger.debug(f"Results object attributes: {dir(results)}")

        if results:
            if hasattr(results, "test_results") and results.test_results:
                logger.debug(f"Found test_results: {len(results.test_results)} test(s)")
                for test_result in results.test_results:
                    logger.debug(f"Test result type: {type(test_result)}")
                    logger.debug(f"Test result attributes: {dir(test_result)}")

                    if (
                        hasattr(test_result, "metrics_data")
                        and test_result.metrics_data
                    ):
                        logger.debug(
                            f"Found {len(test_result.metrics_data)} metrics in test_result"
                        )
                        for metric_data in test_result.metrics_data:
                            metric_name = getattr(metric_data, "name", "Unknown Metric")
                            metric_score = getattr(metric_data, "score", 0.0)
                            metric_success = getattr(metric_data, "success", False)
                            metric_reason = getattr(
                                metric_data, "reason", "No reason provided"
                            )
                            metric_threshold = getattr(metric_data, "threshold", 0.5)

                            extracted_metrics.append(
                                {
                                    "metric": metric_name,
                                    "score": (
                                        float(metric_score)
                                        if metric_score is not None
                                        else 0.0
                                    ),
                                    "success": bool(metric_success),
                                    "reason": str(metric_reason),
                                    "threshold": float(metric_threshold),
                                }
                            )
                            logger.debug(
                                f"Extracted metric: {metric_name} - {metric_success} (score: {metric_score})"
                            )

                        break
        else:
            logger.warning(f"No results to process for {filename}")

        return extracted_metrics

    except Exception as e:
        logger.error(f"Error in metric extraction for {filename}: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise  # Re-raise the exception to be handled by the caller
