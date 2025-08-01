# Local Llama Stack Server

First you need to run the Ollama server:

```shell
OLLAMA_HOST=0.0.0.0 ollama serve
```

Note: there are other alternatives, such as running it as a server.
I prefer this way, because we have more control over disposing of it when we don't use it on the local machine.
Also, the binding to `0.0.0.0` is necessary to make the server callable from the container.

On top of this you can run the Llama Stack server:

```shell
podman run --platform linux/amd64 -it \
    -v ~/.llama:/root/.llama \
    -p 8321:8321 \
    --env INFERENCE_MODEL="meta-llama/Llama-3.2-3B-Instruct" \
    --env OLLAMA_URL=http://host.containers.internal:11434 \
    --replace \
    --name llamastack \
    llamastack/distribution-ollama:0.2.9 \
    --port 8321
```

Note: the sh files provide the same commands.