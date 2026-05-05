"""Asset registration script for agent service."""

import os
import sys
from pathlib import Path

from agent_service.knowledge import KnowledgeBaseManager


def main() -> None:
    """Main entry point for asset registration."""
    kb_manager = KnowledgeBaseManager()

    extra_kb_path_str = os.environ.get("EXTRA_KB_PATH", "")
    extra_path = Path(extra_kb_path_str) if extra_kb_path_str else None

    print("Registering knowledge bases...")
    success = kb_manager.register_knowledge_bases(extra_path=extra_path)

    if success:
        print("Asset registration completed successfully")
        sys.exit(0)
    else:
        print(
            "Asset registration failed - one or more knowledge bases could not be registered"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
