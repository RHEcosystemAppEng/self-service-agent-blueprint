#!/usr/bin/env python3
"""Database migration script for init containers."""

import asyncio
import logging
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

# Add the src directory to Python path and import shared_db modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
try:
    from shared_db.config import get_db_config
    from shared_db.session import get_database_manager
except ImportError:
    # If running in container, try direct import
    from shared_db.config import get_db_config  # noqa: F401
    from shared_db.session import get_database_manager  # noqa: F401

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Also enable Alembic logging
alembic_logger = logging.getLogger("alembic")
alembic_logger.setLevel(logging.DEBUG)


async def wait_for_database(max_retries: int = 30, retry_delay: int = 2) -> bool:
    """Wait for database to become available."""
    logger.info("Waiting for database to become available...")

    db_manager = get_database_manager()

    for attempt in range(max_retries):
        try:
            if await db_manager.health_check():
                logger.info("Database is available")
                return True
        except Exception as e:
            logger.debug(
                f"Database not ready (attempt {attempt + 1}/{max_retries}): {e}"
            )

        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)

    logger.error("Database failed to become available")
    return False


def run_migrations() -> None:
    """Run Alembic migrations."""
    logger.info("Running database migrations...")

    # Get the directory containing this script
    script_dir = Path(__file__).parent.parent
    alembic_cfg_path = script_dir / "alembic.ini"

    logger.debug(f"Script directory: {script_dir}")
    logger.debug(f"Alembic config path: {alembic_cfg_path}")

    if not alembic_cfg_path.exists():
        logger.error(f"Alembic configuration not found: {alembic_cfg_path}")
        sys.exit(1)

    # Create Alembic config
    logger.debug("Creating Alembic configuration...")
    alembic_cfg = Config(str(alembic_cfg_path))

    # Override database URL from environment
    db_config = get_db_config()
    logger.debug(
        f"Database config: host={db_config.host}, port={db_config.port}, db={db_config.database}"
    )
    logger.debug(f"Connection string: {db_config.sync_connection_string}")
    alembic_cfg.set_main_option("sqlalchemy.url", db_config.sync_connection_string)

    try:
        logger.info("Starting Alembic upgrade to head...")
        # Change to the shared-db directory so Alembic can find the alembic/ folder
        original_cwd = os.getcwd()
        os.chdir(script_dir)
        logger.debug(f"Changed working directory to: {script_dir}")

        # Run migrations
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")

        # Restore original working directory
        os.chdir(original_cwd)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        logger.exception("Full migration error traceback:")
        sys.exit(1)


async def main() -> None:
    """Main migration function."""
    logger.info("Starting database migration process")

    try:
        # Wait for database to be available
        logger.debug("Checking database availability...")
        if not await wait_for_database():
            logger.error("Database is not available, exiting")
            sys.exit(1)

        # Run migrations
        logger.debug("Database is ready, starting migrations...")
        run_migrations()

        # Close database connections
        logger.debug("Closing database connections...")
        db_manager = get_database_manager()
        await db_manager.close()

        logger.info("Migration process completed successfully")
    except Exception as e:
        logger.error(f"Migration process failed: {e}")
        logger.exception("Full process error traceback:")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
