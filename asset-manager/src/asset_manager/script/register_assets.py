from pathlib import Path

from asset_manager.kb_manager import KnowledgeBaseManager
from asset_manager.tg_manager import ToolgroupsManager
from asset_manager.util import load_config_from_path


def main() -> None:
    config_path = Path("config")
    config = load_config_from_path(config_path)

    # Initialize managers
    kb_manager = KnowledgeBaseManager(config)
    tg_manager = ToolgroupsManager(config)

    # Connect to llama stack
    print("connecting to llama stack...")
    kb_manager.connect_to_llama_stack()
    tg_manager.connect_to_llama_stack()

    # Register knowledge bases first
    print("kb_manager is_connected:", kb_manager.is_connected())
    print("unregistering knowledge bases...")  # temporary
    kb_manager.unregister_knowledge_bases()  # temporary
    print("registering knowledge bases...")
    kb_manager.register_knowledge_bases()

    # Register toolgroups
    print("tg_manager is_connected:", tg_manager.is_connected())
    print("unregistering toolgroups...")  # temporary
    tg_manager.unregister_toolgroups()  # temporary
    print("registering toolgroups...")
    tg_manager.register_mcp_toolgroups()

    print("Asset registration completed successfully")


if __name__ == "__main__":
    main()
