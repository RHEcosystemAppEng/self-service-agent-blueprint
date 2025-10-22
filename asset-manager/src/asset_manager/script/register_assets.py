from asset_manager.kb_manager import KnowledgeBaseManager


def main() -> None:
    # Initialize managers
    kb_manager = KnowledgeBaseManager()

    # Register knowledge bases
    print("registering knowledge bases...")
    kb_manager.register_knowledge_bases()

    print("Asset registration completed successfully")


if __name__ == "__main__":
    main()
