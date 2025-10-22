import logging
import os
from typing import Any

from llama_stack_client import LlamaStackClient


class Manager:
    def __init__(self, config: Any) -> None:
        self._client: LlamaStackClient | None = None
        self._config = config

    def connect_to_llama_stack(self) -> None:
        if self._client is None:
            logging.debug("Connecting to LlamaStack")
            llama_stack_host = os.environ["LLAMASTACK_SERVICE_HOST"]
            self._client = LlamaStackClient(
                base_url=f"http://{llama_stack_host}:8321",
                timeout=self._config["timeout"],
            )
        else:
            logging.debug("Already connected to LlamaStack")

    def config(self) -> Any:
        return self._config

    def is_connected(self) -> bool:
        return self._client is not None
