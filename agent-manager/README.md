# Self-service agent blueprint: Agent Manager Module

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

Select the `Venv` environment `.venv` under the `agent-manager`.

Note: this is usually done automatically by the IDE if the `agent-manager` directory
is opened as root project.

## Play with the App

1. Run Llama Stack

To run it locally see [local_testing](local_testing/README.md)

2. Set `LLAMASTACK_SERVICE_HOST` environment variable:

For instance:
```shell
export LLAMASTACK_SERVICE_HOST=http://localhost:8321
```

For convenience I set it on my `~/.bashrc` on my Fedora machine.

3. Run the play app

```shell
uv run script/play.py
```

## Build the container

```shell
podman build -t backend-app .
```