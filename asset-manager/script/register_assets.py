from asset_manager.agent_manager import AgentManager
from asset_manager.kb_manager import KnowledgeBaseManager
from asset_manager.tg_manager import ToolgroupsManager
from asset_manager.util import load_config_from_path
from pathlib import Path


def main():
    config = load_config_from_path(Path("config"))

    # Initialize managers
    agent_manager = AgentManager(config)
    kb_manager = KnowledgeBaseManager(config)
    tg_manager = ToolgroupsManager(config)

    # Connect to llama stack
    print("connecting to llama stack...")
    agent_manager.connect_to_llama_stack()
    kb_manager.connect_to_llama_stack()
    tg_manager.connect_to_llama_stack()

    # Register knowledge bases first (agents may depend on them)
    print("kb_manager is_connected:", kb_manager.is_connected())
    print("unregistering knowledge bases...")  # temporary
    kb_manager.unregister_knowledge_bases()  # temporary
    print("registering knowledge bases...")
    kb_manager.register_knowledge_bases()

    # Register toolgroups (agents may depend on them)
    print("tg_manager is_connected:", tg_manager.is_connected())
    print("unregistering toolgroups...")  # temporary
    tg_manager.unregister_toolgroups()  # temporary
    print("registering toolgroups...")
    tg_manager.register_mcp_toolgroups()

    # Then create agents
    print("agent_manager is_connected:", agent_manager.is_connected())
    print("deleting agents...")  # temporary
    agent_manager.delete_agents()  # temporary
    print("creating agents...")
    agent_manager.create_agents()


if __name__ == "__main__":
    main()
