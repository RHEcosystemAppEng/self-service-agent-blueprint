from pathlib import Path

from asset_manager.kb_manager import KnowledgeBaseManager
from asset_manager.util import load_config_from_path


def main() -> None:
    config_path = Path("config")
    config = load_config_from_path(config_path)

    # Initialize managers
    kb_manager = KnowledgeBaseManager(config)

    # Register knowledge bases
    print("registering knowledge bases...")
    kb_manager.register_knowledge_bases()

    print("Asset registration completed successfully")


if __name__ == "__main__":
    main()
