import logging
from pathlib import Path
from typing import List

from .manager import Manager


class KnowledgeBaseManager(Manager):
    def __init__(self, config):
        self._client = None
        self._config = config
        self._knowledge_bases_path = Path("config/knowledge_bases")

    def register_knowledge_bases(self):
        """Register all knowledge bases by processing directories in knowledge_bases path"""
        if self._client is None:
            self.connect_to_llama_stack()

        logging.debug("Registering knowledge bases")

        if not self._knowledge_bases_path.exists():
            logging.warning(
                f"Knowledge bases path {self._knowledge_bases_path} does not exist"
            )
            return

        # Process each directory in knowledge_bases
        for kb_dir in self._knowledge_bases_path.iterdir():
            if kb_dir.is_dir():
                self.register_knowledge_base(kb_dir)

    def register_knowledge_base(self, kb_directory: Path):
        """Register a single knowledge base from a directory"""
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
