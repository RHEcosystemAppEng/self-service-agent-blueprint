import os
from pathlib import Path

import yaml


def load_yaml(file_path) -> dict:
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


def load_config_from_path(path: Path) -> dict:
    config = {}
    # Load main config.yaml first to ensure base settings are loaded
    main_config_file = path / "config.yaml"
    if main_config_file.exists():
        config.update(load_yaml(main_config_file))

    # Load other YAML files (excluding config.yaml to avoid overwriting)
    for file in path.glob("*.yaml"):
        if file.name != "config.yaml":
            config.update(load_yaml(file))

    config["agents"] = []
    agent_path = path / "agents"
    prompts_path = path / "prompts"
    for file in agent_path.glob("*.yaml"):
        agent_config = load_yaml(file)
        prompt = prompts_path / os.path.join(Path(file).stem + ".txt")
        if os.path.exists(prompt):
            agent_config["instructions"] = open(prompt).read()
        config["agents"].append(agent_config)

    config["toolgroups"] = []
    toolgroups_path = path / "toolgroups"
    for file in toolgroups_path.glob("*.yaml"):
        agent_config = load_yaml(file)
        config["toolgroups"].append(agent_config)
    return config
