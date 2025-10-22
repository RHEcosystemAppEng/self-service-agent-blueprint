import logging
from typing import Any

from .manager import Manager


class ToolgroupsManager(Manager):
    def __init__(self, config: dict[str, Any]) -> None:
        self._client = None
        self._config = config

    def is_connected(self) -> bool:
        return self._client is not None

    def unregister_toolgroups(self) -> None:
        """Unregister all registered toolgroups"""
        if self._client is None:
            self.connect_to_llama_stack()

        logging.debug("Unregistering toolgroups")

        for tg in self._config["toolgroups"]:
            self.unregister_mcp_toolgroup(tg)

    def unregister_mcp_toolgroup(self, tg: dict[str, Any]) -> str | None:
        """Unregister a single toolgroup_id"""
        toolgroup_id = f"mcp::{tg.get('name')}"

        logging.info(f"Unregistering toolgroup_id: {toolgroup_id}")

        if self._client is None:
            logging.error("Client not connected. Cannot unregister toolgroups.")
            return None

        try:
            self._client.toolgroups.unregister(toolgroup_id=toolgroup_id)

            logging.info(f"Unregistered toolgroup: {toolgroup_id}")

            return toolgroup_id

        except Exception as e:
            logging.error(f"Failed to unregister toolgroup_id {toolgroup_id}: {str(e)}")
            return None

    def register_mcp_toolgroups(self) -> None:
        """Register all toolgroups by processing directories in toolgroups path"""
        if self._client is None:
            self.connect_to_llama_stack()

        logging.debug("Registering toolgroups")

        for tg in self._config["toolgroups"]:
            self.register_mcp_toolgroup(tg)

    def register_mcp_toolgroup(self, tg: dict[str, Any]) -> str | None:
        """Register a single toolgroup_id from a directory"""
        toolgroup_id = f"mcp::{tg.get('name')}"

        logging.info(f"Registering toolgroup_id: {toolgroup_id}")

        if self._client is None:
            logging.error("Client not connected. Cannot register toolgroups.")
            return None

        try:
            self._client.toolgroups.register(
                toolgroup_id=toolgroup_id,
                provider_id="model-context-protocol",
                mcp_endpoint={"uri": tg.get("uri")},  # type: ignore[arg-type]
                args={},
            )

            logging.info(f"Registered toolgroup: {toolgroup_id}")

            return toolgroup_id

        except Exception as e:
            logging.error(f"Failed to create toolgroup_id {toolgroup_id}: {str(e)}")
            return None
