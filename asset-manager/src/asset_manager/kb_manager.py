import logging
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import openai

from .manager import Manager


class KnowledgeBaseManager(Manager):
    def __init__(self, config):
        self._client = None
        self._openai_client = None
        self._config = config
        self._knowledge_bases_path = Path("config/knowledge_bases")
        self._vector_store_registry = {}  # Map kb_name to vector_store_id

    def connect_to_openai_client(self):
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

    def register_knowledge_bases(self):
        """Register all knowledge bases by processing directories in knowledge_bases path"""
        if self._client is None:
            self.connect_to_llama_stack()

        if self._openai_client is None:
            self.connect_to_openai_client()

        logging.debug("Registering knowledge bases via both LlamaStack and OpenAI APIs")

        if not self._knowledge_bases_path.exists():
            logging.warning(
                f"Knowledge bases path {self._knowledge_bases_path} does not exist"
            )
            return

        # Process each directory in knowledge_bases
        for kb_dir in self._knowledge_bases_path.iterdir():
            if kb_dir.is_dir():
                # Register via both APIs
                llamastack_result = self.register_knowledge_base_llamastack(kb_dir)
                openai_result = self.register_knowledge_base_openai(kb_dir)

                # Log results
                kb_name = kb_dir.name
                if llamastack_result and openai_result:
                    logging.info(
                        f"Successfully registered {kb_name} via both LlamaStack and OpenAI APIs"
                    )
                elif llamastack_result:
                    logging.warning(
                        f"Registered {kb_name} via LlamaStack only (OpenAI failed)"
                    )
                elif openai_result:
                    logging.warning(
                        f"Registered {kb_name} via OpenAI only (LlamaStack failed)"
                    )
                else:
                    logging.error(f"Failed to register {kb_name} via both APIs")

    def register_knowledge_base_llamastack(self, kb_directory: Path):
        """Register a single knowledge base from a directory via LlamaStack API"""
        vector_db_id = kb_directory.name

        logging.info(f"Registering knowledge base: {vector_db_id}")

        try:
            # Select the first embedding model
            models = self._client.models.list()
            embedding_model_id = (
                em := next(m for m in models if m.model_type == "embedding")
            ).identifier
            embedding_dimension = em.metadata["embedding_dimension"]

            # Get the first available vector_io provider
            providers = self._client.providers.list()
            vector_provider = next((p for p in providers if p.api == "vector_io"), None)

            if not vector_provider:
                logging.error("No vector_io provider found")
                return None

            # Register the vector database
            self._client.vector_dbs.register(
                vector_db_id=vector_db_id,
                embedding_model=embedding_model_id,
                embedding_dimension=embedding_dimension,
                provider_id=vector_provider.provider_id,
            )

            logging.info(f"Registered vector database: {vector_db_id}")

            # Insert documents from txt files in the directory
            self._insert_documents_from_directory(kb_directory, vector_db_id)

            return vector_db_id

        except Exception as e:
            logging.error(f"Failed to create knowledge base {vector_db_id}: {str(e)}")
            return None

    def _insert_documents_from_directory(self, directory: Path, vector_db_id: str):
        """Insert all txt files from a directory into the vector database"""
        rag_documents = []
        doc_counter = 0

        # Find all .txt files in the directory
        for file_path in directory.rglob("*.txt"):
            if file_path.is_file():
                doc_counter += 1
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    logging.debug(f"Processing file: {file_path}")

                    rag_documents.append(
                        {
                            "document_id": f"doc-{doc_counter}",
                            "content": content,
                            "mime_type": "text/plain",
                            "metadata": {
                                "source_file": str(file_path.name),
                                "kb_name": directory.name,
                            },
                        }
                    )

                except Exception as e:
                    logging.error(f"Failed to read file {file_path}: {str(e)}")
                    continue

        if rag_documents:
            for doc in rag_documents:
                print(doc["document_id"])
            try:
                logging.info(
                    f"Inserting {len(rag_documents)} documents into {vector_db_id}"
                )
                self._client.tool_runtime.rag_tool.insert(
                    documents=rag_documents,
                    vector_db_id=vector_db_id,
                    chunk_size_in_tokens=1024,
                )
                logging.info(f"Successfully inserted documents into {vector_db_id}")
            except Exception as e:
                logging.error(
                    f"Failed to insert documents into {vector_db_id}: {str(e)}"
                )
        else:
            logging.warning(f"No txt files found in {directory}")

    def register_knowledge_base_openai(self, kb_directory: Path) -> Optional[str]:
        """Register a single knowledge base from a directory via OpenAI API"""
        kb_name = kb_directory.name

        logging.info(f"Registering knowledge base via OpenAI API: {kb_name}")

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

            # Store mapping for later reference
            self._vector_store_registry[kb_name] = vector_store_id

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

    def get_vector_store_id(self, kb_name: str) -> Optional[str]:
        """Get the OpenAI vector store ID for a knowledge base"""
        return self._vector_store_registry.get(kb_name)

    def list_vector_stores(self) -> Dict[str, str]:
        """List all registered vector stores (kb_name -> vector_store_id mapping)"""
        return self._vector_store_registry.copy()

    def unregister_knowledge_bases(self):
        """Unregister all registered vector databases"""
        if self._client is None:
            self.connect_to_llama_stack()

        logging.debug("Unregistering knowledge bases")

        try:
            # Get list of vector databases (if available)
            # Note: This depends on the LlamaStack API having a list method
            vector_dbs = self._client.vector_dbs.list()

            for vector_db in vector_dbs:
                try:
                    self._client.vector_dbs.unregister(vector_db.identifier)
                    logging.info(
                        f"Unregistered vector database: {vector_db.identifier}"
                    )
                except Exception as e:
                    logging.error(
                        f"Failed to unregister vector database {vector_db.identifier}: {str(e)}"
                    )

        except Exception as e:
            logging.error(f"Failed to list/unregister vector databases: {str(e)}")

    def list_knowledge_bases(self) -> List[str]:
        """List all available knowledge base directories"""
        knowledge_bases = []

        if not self._knowledge_bases_path.exists():
            return knowledge_bases

        for kb_dir in self._knowledge_bases_path.iterdir():
            if kb_dir.is_dir():
                knowledge_bases.append(kb_dir.name)

        return knowledge_bases

    def get_knowledge_base_by_vector_db_id(self, vector_db_id: str):
        """Get a knowledge base by its vector database ID"""
        if self._client is None:
            self.connect_to_llama_stack()

        try:
            # Get list of all registered vector databases
            vector_dbs = self._client.vector_dbs.list()

            # Find the vector database with the matching ID
            for vector_db in vector_dbs:
                if vector_db.identifier == vector_db_id:
                    return vector_db

            logging.warning(f"No knowledge base found with vector ID: {vector_db_id}")
            return None

        except Exception as e:
            logging.error(
                f"Failed to get knowledge base by vector ID {vector_db_id}: {str(e)}"
            )
            return None

    def get_vector_db_ids(self) -> List[str]:
        """Get vector database IDs for all knowledge bases"""
        kb_names = self.list_knowledge_bases()
        return [kb_name for kb_name in kb_names]
