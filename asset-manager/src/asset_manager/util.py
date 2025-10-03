import os
from pathlib import Path

import yaml


def load_yaml(file_path) -> dict:
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


def resolve_asset_manager_path(relative_path: str) -> Path:
    """
    Resolve a path relative to the asset-manager root, trying multiple possible locations.

    This function handles the path resolution issues that occur when running in containers
    where the asset-manager directory structure may be different from development.

    Args:
        relative_path: Path relative to asset-manager root (e.g., "config", "config/lg-prompts/routing.yaml")

    Returns:
        Path: Resolved absolute path to the requested file/directory

    Raises:
        FileNotFoundError: If the path cannot be found in any of the possible locations
    """
    # Try multiple possible asset-manager root locations
    possible_roots = [
        Path(__file__).parent.parent.parent,  # Original path: asset-manager/
        Path("/app/asset-manager"),  # Container path
        Path("."),  # Current directory (fallback)
    ]

    for root in possible_roots:
        full_path = root / relative_path
        if full_path.exists():
            return full_path

    # If no path found, raise error with helpful message
    tried_paths = [str(root / relative_path) for root in possible_roots]
    raise FileNotFoundError(
        f"Could not find '{relative_path}' in any of the expected locations: {tried_paths}"
    )


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
