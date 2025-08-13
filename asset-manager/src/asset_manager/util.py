import yaml
from pathlib import Path


def load_yaml(file_path) -> dict:
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


def load_config_from_path(path: Path) -> dict:
    config = {}
    for file in path.glob("*.yaml"):
        config.update(load_yaml(file))

    config["agents"] = []
    agent_path = path / "agents"
    for file in agent_path.glob("*.yaml"):
        agent_config = load_yaml(file)
        config["agents"].append(agent_config)

    config["toolgroups"] = []
    toolgroups_path = path / "toolgroups"
    for file in toolgroups_path.glob("*.yaml"):
        agent_config = load_yaml(file)
        config["toolgroups"].append(agent_config)
    return config
