# Self-service agent blueprint: Asset Manager Module

This module provides two main components:
- **AgentManager**: Manages agent creation and configuration
- **KnowledgeBaseManager**: Manages knowledge bases (vector databases) for RAG functionality

## Project sync

To alig `.venv` environment with any change applied to the project.

```shell
uv sync --all-packages
```

## Run unit tests

```shell
uv run pytest
```

## Configure the IDE

Select the `Venv` environment `.venv` under the `asset-manager`.

Note: this is usually done automatically by the IDE if the `asset-manager` directory
is opened as root project.

## Play with the App

1. Run Llama Stack

To run it locally see [local_testing](local_testing/README.md)

2. Set `LLAMASTACK_SERVICE_HOST` environment variable:

For instance:
```shell
export LLAMASTACK_SERVICE_HOST=http://localhost:8321
```

For convenience, I set it on my `~/.bashrc` on my Fedora machine.

3. Run the play app

```shell
uv run script/register_assets.py
```

This will create both knowledge bases and agents. The knowledge bases are created from directories in `config/knowledge_bases/`, where each directory becomes a separate vector database with all `.txt` files in that directory inserted as documents.

## Knowledge Base Management

The `KnowledgeBaseManager` automatically processes knowledge base directories:

1. **Directory Structure**: Each subdirectory in `config/knowledge_bases/` becomes a separate knowledge base
2. **Document Processing**: All `.txt` files in each directory are inserted into the corresponding vector database
3. **Vector DB Naming**: Knowledge bases are named as `{directory-name}`

### Example Directory Structure:
```
config/knowledge_bases/
├── laptop-refresh/
│   ├── laptop_offerings.txt
│   └── refresh_policy.txt
└── hr-policies/
    ├── vacation_policy.txt
    └── benefits_guide.txt
```

This creates two knowledge bases:
- `laptop-refresh`
- `hr-policies`

## Build the container

```shell
podman build -t asset-manager .
```

Get the llamastack container podman network bridge IP {{LLAMA_STACK_IP}}: 

```shell
podman inspect llamastack | grep -i ipaddress
```

```shell
podman run --rm -e LLAMASTACK_SERVICE_HOST="http://{{LLAMA_STACK_IP}}:8321" --network bridge asset-manager
```