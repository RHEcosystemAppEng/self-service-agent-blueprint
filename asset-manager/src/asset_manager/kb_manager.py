import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import openai


class KnowledgeBaseManager:
    def __init__(self) -> None:
        self._openai_client: openai.OpenAI | None = None
        self._knowledge_bases_path = Path("config/knowledge_bases")

    def connect_to_openai_client(self) -> None:
        """Initialize OpenAI client configured to use LlamaStack"""
        if self._openai_client is None:
            logging.debug("Connecting to OpenAI client via LlamaStack")
            llama_stack_host = os.environ.get("LLAMASTACK_SERVICE_HOST", "llamastack")

            # Extract hostname without protocol if present
            if llama_stack_host.startswith(("http://", "https://")):
                llama_stack_host = llama_stack_host.split("://", 1)[1]

            self._openai_client = openai.OpenAI(
                api_key="dummy-key",  # LlamaStack doesn't require real API key
                base_url=f"http://{llama_stack_host}:8321/v1/openai/v1",
            )
        else:
            logging.debug("Already connected to OpenAI client")

    def register_knowledge_bases(self) -> None:
        """Register all knowledge bases by processing directories in knowledge_bases path"""
        if self._openai_client is None:
            self.connect_to_openai_client()

        logging.debug("Registering knowledge bases via OpenAI API")

        if not self._knowledge_bases_path.exists():
            logging.warning(
                f"Knowledge bases path {self._knowledge_bases_path} does not exist"
            )
            return

        # Process each directory in knowledge_bases
        for kb_dir in self._knowledge_bases_path.iterdir():
            if kb_dir.is_dir():
                # Register via OpenAI API
                openai_result = self.register_knowledge_base_openai(kb_dir)

                # Log results
                kb_name = kb_dir.name
                if openai_result:
                    logging.info(f"Successfully registered {kb_name} via OpenAI API")
                else:
                    logging.error(f"Failed to register {kb_name} via OpenAI API")

    def register_knowledge_base_openai(self, kb_directory: Path) -> Optional[str]:
        """Register a single knowledge base from a directory via OpenAI API"""
        kb_name = kb_directory.name

        logging.info(f"Registering knowledge base via OpenAI API: {kb_name}")

        if self._openai_client is None:
            logging.error(
                "OpenAI client not connected. Cannot register knowledge base."
            )
            return None

        try:
            # Create vector store with unique name
            vector_store_name = f"{kb_name}-kb-{uuid.uuid4().hex[:8]}"
            vector_store = self._openai_client.vector_stores.create(
                name=vector_store_name
            )
            vector_store_id = vector_store.id

            logging.info(
                f"Created vector store via OpenAI client: {vector_store_id} with name: {vector_store_name}"
            )

            # Upload files to vector store
            uploaded_files = self._upload_files_to_vector_store(
                kb_directory, vector_store_id
            )

            if uploaded_files > 0:
                logging.info(
                    f"Successfully uploaded {uploaded_files} files via OpenAI client to vector store"
                )
                return vector_store_id
            else:
                logging.warning(
                    "No knowledge base files uploaded via OpenAI client - vector store will be empty"
                )
                return vector_store_id  # Return ID even if empty for consistency

        except Exception as e:
            logging.error(
                f"Failed to register knowledge base {kb_name} via OpenAI API: {str(e)}"
            )
            return None

    def _upload_files_to_vector_store(
        self, directory: Path, vector_store_id: str
    ) -> int:
        """Upload all txt files from a directory to OpenAI vector store"""
        if self._openai_client is None:
            logging.error("OpenAI client not connected. Cannot upload files.")
            return 0

        uploaded_count = 0

        # Find all .txt files in the directory
        txt_files = list(directory.rglob("*.txt"))
        logging.info(
            f"Found {len(txt_files)} knowledge base files: {[f.name for f in txt_files]}"
        )

        for file_path in txt_files:
            if file_path.is_file():
                try:
                    logging.info(
                        f"Uploading knowledge base file via OpenAI client: {file_path}"
                    )

                    # Upload file to OpenAI
                    with open(file_path, "rb") as f:
                        file_create_response = self._openai_client.files.create(
                            file=f, purpose="assistants"
                        )

                    file_id = file_create_response.id

                    # Attach file to vector store
                    self._openai_client.vector_stores.files.create(
                        vector_store_id=vector_store_id, file_id=file_id
                    )

                    uploaded_count += 1
                    logging.info(
                        f"Successfully uploaded and attached file via OpenAI client: {file_id}"
                    )

                except Exception as e:
                    logging.error(f"Failed to upload file {file_path} to OpenAI: {e}")
                    continue

        return uploaded_count
