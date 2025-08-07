#!/bin/bash

podman run --platform linux/amd64 -it \
    -v ~/.llama:/root/.llama \
    -p 8321:8321 \
    --env INFERENCE_MODEL="meta-llama/Llama-3.2-3B-Instruct" \
    --env OLLAMA_URL=http://host.containers.internal:11434 \
    --replace \
    --name llamastack \
    --network bridge \
    llamastack/distribution-ollama:0.2.9