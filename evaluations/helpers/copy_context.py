#!/usr/bin/env python3
"""
Script to copy context files to the default_context directory for evaluations.

This script copies:
1. All files from agent-service/config/knowledge_bases/laptop-refresh/
2. The ServiceNow data file from mock-employee-data/src/mock_employee_data/data.py

All files are copied to evaluations/conversations_config/default_context/
"""

import logging
import shutil
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def copy_context_files() -> None:
    """
    Copy context files from source locations to the default_context directory.

    This function copies:
    1. All files from agent-service/config/knowledge_bases/laptop-refresh/
    2. The ServiceNow data file from mock-employee-data/src/mock_employee_data/data.py

    All files are copied to evaluations/conversations_config/default_context/

    The target directory is created if it doesn't exist. Missing source files
    or directories result in warning logs but do not cause the function to fail.

    Raises:
        Exception: If there are critical errors accessing the workspace structure
    """
    # Get the workspace root (assuming this script is in evaluations/helpers/)
    workspace_root = Path(__file__).parent.parent.parent

    # Define source and target paths
    laptop_refresh_source = (
        workspace_root
        / "agent-service"
        / "config"
        / "knowledge_bases"
        / "laptop-refresh"
    )
    snow_data_source = (
        workspace_root / "mock-employee-data" / "src" / "mock_employee_data" / "data.py"
    )
    target_dir = (
        workspace_root / "evaluations" / "conversations_config" / "default_context"
    )

    # Create target directory if it doesn't exist
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy all files from laptop-refresh directory
    if laptop_refresh_source.exists():
        for file_path in laptop_refresh_source.iterdir():
            if file_path.is_file():
                target_file = target_dir / file_path.name
                shutil.copy2(file_path, target_file)
    else:
        logger.warning(f"Source directory not found: {laptop_refresh_source}")

    # Copy the ServiceNow data file
    if snow_data_source.exists():
        target_file = target_dir / "snow_data.py"
        shutil.copy2(snow_data_source, target_file)
    else:
        logger.warning(f"ServiceNow data file not found: {snow_data_source}")


def copy_flow_context(flow_name: str) -> None:
    """
    Copy context files for the named flow into flows/{name}/context/.

    Reads KNOWLEDGE_BASE_DIRS and INCLUDE_SNOW_DATA from the flow module and
    copies the corresponding files from the agent-service knowledge bases and
    mock-employee-data into the flow's context directory.

    Args:
        flow_name: Name of the flow (must match a subdirectory under evaluations/flows/)
    """
    import sys

    # Ensure evaluations dir is on path so flow_registry can be imported
    evaluations_dir = str(Path(__file__).parent.parent)
    if evaluations_dir not in sys.path:
        sys.path.insert(0, evaluations_dir)

    from flow_registry import get_flow_paths, load_flow

    flow_module = load_flow(flow_name)
    knowledge_base_dirs = getattr(flow_module, "KNOWLEDGE_BASE_DIRS", [])
    include_snow_data = getattr(flow_module, "INCLUDE_SNOW_DATA", False)

    flow_paths = get_flow_paths(flow_name)
    target_dir = flow_paths.context_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    workspace_root = Path(__file__).parent.parent.parent

    for kb_dir_name in knowledge_base_dirs:
        source = (
            workspace_root
            / "agent-service"
            / "config"
            / "knowledge_bases"
            / kb_dir_name
        )
        if source.exists():
            for file_path in source.iterdir():
                if file_path.is_file():
                    shutil.copy2(file_path, target_dir / file_path.name)
                    logger.info(f"Copied {file_path.name} to {target_dir}")
        else:
            logger.warning(f"Source directory not found: {source}")

    if include_snow_data:
        snow_source = (
            workspace_root
            / "mock-employee-data"
            / "src"
            / "mock_employee_data"
            / "data.py"
        )
        if snow_source.exists():
            shutil.copy2(snow_source, target_dir / "snow_data.py")
            logger.info(f"Copied snow_data.py to {target_dir}")
        else:
            logger.warning(f"ServiceNow data file not found: {snow_source}")


if __name__ == "__main__":
    copy_context_files()
