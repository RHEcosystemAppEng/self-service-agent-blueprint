#!/usr/bin/env python3
"""
Helper functions for loading conversation context from various sources.

This module provides functions to load context files from directories and
combine them for conversation evaluation.
"""

import json
import logging
import os
from typing import List, Optional

# Configure logging
logger = logging.getLogger(__name__)


def load_context_files_from_directory(
    directory: str, description: str = "context"
) -> List[str]:
    """
    Load all context files from a directory with clear file separation and naming

    Args:
        directory: Path to directory containing context files
        description: Description for logging purposes

    Returns:
        List of context strings loaded from files with file headers
    """
    context_list: list[str] = []

    if not os.path.exists(directory):
        return context_list

    try:
        # Get all files with supported extensions
        context_extensions = [".txt", ".md", ".context", ".json"]
        context_files = []

        for ext in context_extensions:
            pattern_files = [f for f in os.listdir(directory) if f.endswith(ext)]
            context_files.extend(pattern_files)

        # Sort files for consistent ordering
        context_files.sort()

        for context_file in context_files:
            file_path = os.path.join(directory, context_file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    # Create header for this file
                    file_header = f"\n{
                        '='
                        * 60}\nCONTEXT FILE: {context_file}\nSOURCE: {file_path}\n{
                        '='
                        * 60}\n"

                    if context_file.endswith(".json"):
                        # Handle JSON context files
                        context_data = json.load(f)
                        file_content = ""

                        if isinstance(context_data, list):
                            for i, item in enumerate(context_data):
                                file_content += f"Item {i + 1}:\n{str(item)}\n\n"
                        elif isinstance(context_data, dict):
                            if "context" in context_data:
                                if isinstance(context_data["context"], list):
                                    for i, item in enumerate(context_data["context"]):
                                        file_content += (
                                            f"Context Item {i + 1}:\n{str(item)}\n\n"
                                        )
                                else:
                                    file_content = str(context_data["context"])
                            else:
                                file_content = json.dumps(context_data, indent=2)
                        else:
                            file_content = str(context_data)

                        # Add the formatted content with header
                        if file_content.strip():
                            context_list.append(file_header + file_content.strip())

                    else:
                        # Handle text context files
                        context_content = f.read().strip()
                        if context_content:
                            context_list.append(file_header + context_content)

                logger.debug(f"Loaded {description} from {file_path}")
            except Exception as e:
                logger.warning(f"Failed to load {description} from {file_path}: {e}")

        if context_files:
            logger.debug(
                f"Loaded {len(context_files)} {description} file(s) from {directory}"
            )

    except Exception as e:
        logger.warning(f"Error accessing {description} directory {directory}: {e}")

    return context_list


def load_default_context() -> List[str]:
    """
    Load default context files that apply to all conversations.

    This method loads all context files from the default context directory
    (conversations_config/default_context/) without requiring any parameters.

    Returns:
        List of context strings loaded from default context files.
        Returns empty list if no default context files are available.
    """
    default_context_dir = "conversations_config/default_context"
    default_contexts = load_context_files_from_directory(
        default_context_dir, "default context"
    )

    if default_contexts:
        logger.info(
            f"Loaded {len(default_contexts)} default context file(s) from {default_context_dir}"
        )
    else:
        logger.info(f"No default context files found in {default_context_dir}")

    return default_contexts


def load_context_for_file(
    filename: str, context_dir: Optional[str] = None
) -> Optional[List[str]]:
    """
    Load context for a specific conversation file from multiple sources

    Args:
        filename: Name of the conversation file
        context_dir: Directory containing context files (matched by filename)

    Returns:
        List of context strings or None if no context available

    Context loading order:
        1. Default context files (conversations_config/default_context/ directory)
        2. Filename-matched context files (from --context-dir)
        3. Conversation-specific context files (conversations_config/conversation_context/{conversation_name}/ directory)
    """
    context_list = []
    base_name = os.path.splitext(filename)[0]

    # 1. Load default context files (applied to all conversations)
    default_context_dir = "conversations_config/default_context"
    default_contexts = load_context_files_from_directory(
        default_context_dir, "default context"
    )
    if default_contexts:
        context_list.extend(default_contexts)
        logger.debug(
            f"Using {len(default_contexts)} default context item(s) for {filename}"
        )

    # 3. Load filename-matched context files (existing functionality)
    if context_dir and os.path.exists(context_dir):
        # Try different context file extensions
        context_extensions = [".txt", ".md", ".context", ".json"]

        for ext in context_extensions:
            context_file_path = os.path.join(context_dir, f"{base_name}{ext}")
            if os.path.exists(context_file_path):
                try:
                    with open(context_file_path, "r", encoding="utf-8") as f:
                        # Create header for filename-matched context file
                        context_filename = f"{base_name}{ext}"
                        file_header = f"\n{
                            '=' * 60}\nFILENAME-MATCHED CONTEXT: {context_filename}\nSOURCE: {context_file_path}\n{
                            '=' * 60}\n"

                        if ext == ".json":
                            # Handle JSON context files
                            context_data = json.load(f)
                            file_content = ""

                            if isinstance(context_data, list):
                                for i, item in enumerate(context_data):
                                    file_content += f"Item {i + 1}:\n{str(item)}\n\n"
                            elif isinstance(context_data, dict):
                                if "context" in context_data:
                                    if isinstance(context_data["context"], list):
                                        for i, item in enumerate(
                                            context_data["context"]
                                        ):
                                            file_content += f"Context Item {
                                                i
                                                + 1}:\n{
                                                str(item)}\n\n"
                                    else:
                                        file_content = str(context_data["context"])
                                else:
                                    file_content = json.dumps(context_data, indent=2)
                            else:
                                file_content = str(context_data)

                            if file_content.strip():
                                context_list.append(file_header + file_content.strip())
                        else:
                            # Handle text context files
                            context_content = f.read().strip()
                            if context_content:
                                context_list.append(file_header + context_content)

                    logger.debug(
                        f"Loaded filename-matched context from {context_file_path} for {filename}"
                    )
                    break  # Use the first matching context file
                except Exception as e:
                    logger.warning(
                        f"Failed to load filename-matched context from {context_file_path}: {e}"
                    )

    # 4. Load conversation-specific context files
    conversation_context_dir = os.path.join(
        "conversations_config/conversation_context", base_name
    )
    conversation_contexts = load_context_files_from_directory(
        conversation_context_dir, f"conversation-specific context for {base_name}"
    )
    if conversation_contexts:
        context_list.extend(conversation_contexts)
        logger.debug(
            f"Using {
                len(conversation_contexts)} conversation-specific context item(s) for {filename}"
        )

    # Return context list or None if empty
    return context_list if context_list else None
