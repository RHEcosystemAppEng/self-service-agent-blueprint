import uuid
from pathlib import Path
from typing import Any, Optional

from agent_service.utils import create_llamastack_client
from shared_models import configure_logging

logger = configure_logging("agent-service")


class KnowledgeBaseManager:
    def __init__(self) -> None:
        self._llama_client: Any = None
        self._knowledge_bases_path = Path("config/knowledge_bases")

    def connect_to_llamastack_client(self) -> None:
        """Initialize LlamaStack client for OpenAI-compatible APIs"""
        if self._llama_client is None:
            logger.debug(
                "Connecting to LlamaStack client for knowledge base operations"
            )
            self._llama_client = create_llamastack_client()
        else:
            logger.debug("Already connected to LlamaStack client")

    def register_knowledge_bases(self) -> None:
        """Register all knowledge bases by processing directories in knowledge_bases path"""
        if self._llama_client is None:
            self.connect_to_llamastack_client()

        logger.debug("Registering knowledge bases via LlamaStack OpenAI-compatible API")

        if not self._knowledge_bases_path.exists():
            logger.warning(
                f"Knowledge bases path {self._knowledge_bases_path} does not exist"
            )
            return

        # Process each directory in knowledge_bases
        for kb_dir in self._knowledge_bases_path.iterdir():
            if kb_dir.is_dir():
                # Register via LlamaStack OpenAI-compatible API
                result = self.register_knowledge_base(kb_dir)

                # Log results
                kb_name = kb_dir.name
                if result:
                    logger.info(f"Successfully registered {kb_name} via LlamaStack")
                else:
                    logger.error(f"Failed to register {kb_name} via LlamaStack")

    def register_knowledge_base(self, kb_directory: Path) -> Optional[str]:
        """Register a single knowledge base from a directory via LlamaStack OpenAI-compatible API"""
        kb_name = kb_directory.name

        logger.info(f"Registering knowledge base via LlamaStack: {kb_name}")

        if self._llama_client is None:
            logger.error(
                "LlamaStack client not connected. Cannot register knowledge base."
            )
            return None

        try:
            # Create vector store with unique name using LlamaStack's OpenAI-compatible API
            vector_store_name = f"{kb_name}-kb-{uuid.uuid4().hex[:8]}"
            vector_store = self._llama_client.vector_stores.create(
                name=vector_store_name
            )
            vector_store_id = vector_store.id

            logger.info(
                f"Created vector store via LlamaStack: {vector_store_id} with name: {vector_store_name}"
            )

            # Upload files to vector store
            uploaded_files = self._upload_files_to_vector_store(
                kb_directory, vector_store_id
            )

            if uploaded_files > 0:
                logger.info(
                    f"Successfully uploaded {uploaded_files} files via LlamaStack to vector store"
                )
                return str(vector_store_id)
            else:
                logger.warning(
                    "No knowledge base files uploaded via LlamaStack - vector store will be empty"
                )
                return str(vector_store_id)  # Return ID even if empty for consistency

        except Exception as e:
            logger.error(
                f"Failed to register knowledge base {kb_name} via LlamaStack: {str(e)}"
            )
            return None

    def _upload_files_to_vector_store(
        self, directory: Path, vector_store_id: str
    ) -> int:
        """Upload all txt files from a directory to LlamaStack vector store"""
        if self._llama_client is None:
            logger.error("LlamaStack client not connected. Cannot upload files.")
            return 0

        uploaded_count = 0

        # Find all .txt files in the directory
        txt_files = list(directory.rglob("*.txt"))
        logger.info(
            f"Found {len(txt_files)} knowledge base files: {[f.name for f in txt_files]}"
        )

        for file_path in txt_files:
            if file_path.is_file():
                try:
                    logger.info(
                        f"Uploading knowledge base file via LlamaStack: {file_path}"
                    )

                    # Upload file using LlamaStack's OpenAI-compatible API
                    with open(file_path, "rb") as f:
                        file_create_response = self._llama_client.files.create(
                            file=f, purpose="assistants"
                        )

                    file_id = file_create_response.id

                    # Attach file to vector store using LlamaStack's OpenAI-compatible API
                    self._llama_client.vector_stores.files.create(
                        vector_store_id=vector_store_id, file_id=file_id
                    )

                    uploaded_count += 1
                    logger.info(
                        f"Successfully uploaded and attached file via LlamaStack: {file_id}"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to upload file {file_path} to LlamaStack: {e}"
                    )
                    continue

        return uploaded_count
