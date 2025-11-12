#!/usr/bin/env python3
"""Standalone script to check for logging pattern violations.

This script enforces:
1. No direct 'import logging' (except in logging configuration modules)
2. No print() statements in src/ directories (except in scripts/ directories)
3. Structured logging with keyword arguments (no f-strings in logger calls)
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple


class LoggingPatternChecker:
    """Check for logging pattern violations."""

    def __init__(self, root_dir: Path):
        """Initialize the checker.

        Args:
            root_dir: Root directory to scan
        """
        self.root_dir = root_dir
        self.errors: List[Tuple[Path, int, str]] = []

    def check_file(self, file_path: Path) -> None:
        """Check a single file for logging pattern violations.

        Args:
            file_path: Path to the file to check
        """
        # Skip excluded files
        if self._is_excluded_file(file_path):
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=str(file_path))
            self._check_ast(tree, file_path)

        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error checking {file_path}: {e}", file=sys.stderr)

    def _check_ast(self, tree: ast.AST, file_path: Path) -> None:
        """Check AST for logging pattern violations.

        Args:
            tree: AST tree to check
            file_path: Path to the file being checked
        """
        # Check for direct logging imports (LOG001)
        # Skip for script files and excluded files
        if not self._is_script_file(file_path):
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "logging":
                            self.errors.append(
                                (
                                    file_path,
                                    node.lineno,
                                    "LOG001: Direct 'import logging' is not allowed - use 'from shared_models import configure_logging'",
                                )
                            )

                elif isinstance(node, ast.ImportFrom):
                    # Only flag direct "from logging import ..." not relative imports like "from .logging import ..."
                    if node.module == "logging" and node.level == 0:
                        self.errors.append(
                            (
                                file_path,
                                node.lineno,
                                "LOG001: Direct 'import logging' is not allowed - use 'from shared_models import configure_logging'",
                            )
                        )

        # Check for print() statements in src/ directories (LOG002)
        if self._is_src_file(file_path) and not self._is_script_file(file_path):
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "print":
                        self.errors.append(
                            (
                                file_path,
                                node.lineno,
                                "LOG002: print() is not allowed in src/ directories - use logger instead",
                            )
                        )

        # Check for f-strings in logger calls (LOG003)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check if this is a logger call
                if isinstance(node.func, ast.Attribute):
                    if (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "logger"
                        and node.func.attr
                        in ["debug", "info", "warning", "error", "critical"]
                    ):
                        # Check for f-strings in arguments
                        if self._has_fstring_args(node):
                            self.errors.append(
                                (
                                    file_path,
                                    node.lineno,
                                    "LOG003: Logger calls must use structured logging with keyword arguments, not f-strings",
                                )
                            )

    def _is_excluded_file(self, file_path: Path) -> bool:
        """Check if the file should be excluded from checks.

        Args:
            file_path: Path to check

        Returns:
            True if file should be excluded, False otherwise
        """
        # Exclude files in these directories
        excluded_parts = {
            ".venv",
            "venv",
            "env",
            ".env",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            "build",
            "dist",
            ".eggs",
            "node_modules",
            "evaluations",
            "alembic",
            ".git",
        }

        # Exclude logging configuration modules and __init__ files from LOG001
        excluded_files = {
            "configure_logging.py",
            "logging_config.py",
            "logging.py",  # shared-models logging module
            "__init__.py",  # May need to configure logging
            "session_manager.py",  # Uses logging to configure third-party loggers
        }

        # Files that are allowed to use print() (user-facing output)
        print_allowed_files = {
            "token_counter.py",  # Token summary output
            "request_manager_client.py",  # CLI chat interface
            "responses_agent.py",  # Debug output in specific functions
        }

        # Check if any part of the path is in excluded directories
        if any(part in excluded_parts for part in file_path.parts):
            return True

        # Check if filename is excluded
        if file_path.name in excluded_files:
            return True

        # Check if this is a data/utility script (allowed to use print)
        if file_path.name in print_allowed_files:
            return True

        # Exclude files in data/ directories (utility scripts)
        if "data" in file_path.parts:
            return True

        return False

    def _is_src_file(self, file_path: Path) -> bool:
        """Check if the file is in a src/ directory.

        Args:
            file_path: Path to check

        Returns:
            True if file is in src/, False otherwise
        """
        return "src" in file_path.parts

    def _is_script_file(self, file_path: Path) -> bool:
        """Check if the file is in a scripts/ directory.

        Args:
            file_path: Path to check

        Returns:
            True if file is in scripts/, False otherwise
        """
        return "scripts" in file_path.parts

    def _has_fstring_args(self, node: ast.Call) -> bool:
        """Check if a function call has f-string arguments.

        Args:
            node: AST Call node to check

        Returns:
            True if any argument is an f-string, False otherwise
        """
        # Check positional arguments
        for arg in node.args:
            if isinstance(arg, ast.JoinedStr):  # JoinedStr is an f-string
                return True

        # Check keyword arguments
        for keyword in node.keywords:
            if isinstance(keyword.value, ast.JoinedStr):
                return True

        return False

    def scan_directory(self, directory: Path = None) -> None:
        """Scan a directory recursively for Python files.

        Args:
            directory: Directory to scan (defaults to root_dir)
        """
        if directory is None:
            directory = self.root_dir

        for py_file in directory.rglob("*.py"):
            self.check_file(py_file)

    def report(self) -> int:
        """Print errors and return exit code.

        Returns:
            0 if no errors, 1 if errors found
        """
        if not self.errors:
            print("✅ No logging pattern violations found!")
            return 0

        print(f"❌ Found {len(self.errors)} logging pattern violation(s):\n")

        # Sort errors by file and line number
        sorted_errors = sorted(self.errors, key=lambda x: (str(x[0]), x[1]))

        for file_path, line_no, message in sorted_errors:
            # Make path relative to root for cleaner output
            try:
                rel_path = file_path.relative_to(self.root_dir)
            except ValueError:
                rel_path = file_path

            print(f"{rel_path}:{line_no}: {message}")

        return 1


def main():
    """Main entry point."""
    # Get the repository root (parent of scripts directory)
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent

    print(f"Checking logging patterns in {root_dir}...\n")

    checker = LoggingPatternChecker(root_dir)
    checker.scan_directory()
    exit_code = checker.report()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
