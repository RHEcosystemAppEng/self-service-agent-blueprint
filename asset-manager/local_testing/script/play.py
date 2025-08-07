from asset_manager.agent_manager import AgentManager
from asset_manager.util import load_config_from_path
from pathlib import Path


def main():
    config = load_config_from_path(Path("local_testing/config"))
    agent_manager = AgentManager(config)
    print("config:", agent_manager.config())
    print("is_connected:", agent_manager.is_connected())

    print("connecting to llama stack...")
    agent_manager.connect_to_llama_stack()
    print("is_connected:", agent_manager.is_connected())

    print("deleting agents...")
    agent_manager.delete_agents()
    print("agents", len(agent_manager.agents().data))

    print("creating agents...")
    agent_manager.create_agents()
    print("agents", len(agent_manager.agents().data))


if __name__ == "__main__":
    main()
