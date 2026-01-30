#!/usr/bin/env python3
"""Database migration script for init containers."""

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

import psycopg
from alembic import command
from alembic.config import Config

# Add the src directory to Python path and import shared_models modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
try:
    from shared_models import configure_logging
    from shared_models.database import get_database_manager, get_db_config
except ImportError:
    # If running in container, try direct import
    from shared_models import configure_logging  # noqa: F401
    from shared_models.database import get_database_manager, get_db_config  # noqa: F401

# Configure logging with structured logging support
logger = configure_logging("migrate")

# Also enable Alembic logging at DEBUG level
logging.basicConfig(level=logging.DEBUG)
alembic_logger = logging.getLogger("alembic")
alembic_logger.setLevel(logging.DEBUG)


async def wait_for_database(max_retries: int = 150, retry_delay: int = 2) -> bool:
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
                "Database not ready",
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(e),
                error_type=type(e).__name__,
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

    logger.debug("Script directory", script_dir=str(script_dir))
    logger.debug("Alembic config path", alembic_cfg_path=str(alembic_cfg_path))

    if not alembic_cfg_path.exists():
        logger.error(
            "Alembic configuration not found",
            alembic_cfg_path=str(alembic_cfg_path),
        )
        sys.exit(1)

    # Create Alembic config
    logger.debug("Creating Alembic configuration...")
    alembic_cfg = Config(str(alembic_cfg_path))

    # Override database URL from environment
    db_config = get_db_config()
    logger.debug(
        "Database config",
        host=db_config.host,
        port=db_config.port,
        database=db_config.database,
    )

    # Only log connection string in debug mode
    if os.getenv("SQL_DEBUG", "false").lower() == "true":
        logger.debug(
            "Connection string",
            connection_string=db_config.sync_connection_string,
        )

    alembic_cfg.set_main_option("sqlalchemy.url", db_config.sync_connection_string)

    try:
        # Change to the shared-db directory so Alembic can find the alembic/ folder
        original_cwd = os.getcwd()
        os.chdir(script_dir)
        logger.debug("Changed working directory", script_dir=str(script_dir))

        # Setup LangGraph PostgreSQL checkpoint tables FIRST
        # This ensures checkpoint infrastructure is ready before application migrations
        print("Setting up LangGraph PostgreSQL checkpoint tables...")
        logger.info("Setting up LangGraph PostgreSQL checkpoint tables...")
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            # Create a connection for PostgresSaver setup
            conn = psycopg.connect(
                db_config.sync_connection_string.replace(
                    "postgresql+psycopg://", "postgresql://"
                ),
                row_factory=psycopg.rows.dict_row,
                autocommit=True,
                connect_timeout=60,  # 60 second timeout for migration job
            )

            try:
                # Setup PostgresSaver with timeout to prevent hangs
                # PostgresSaver.setup() is idempotent and handles existing tables gracefully
                print("Running PostgresSaver.setup()...")
                logger.info("Running PostgresSaver.setup()...")
                postgres_saver = PostgresSaver(conn)

                # Add timeout to prevent hanging (60 seconds)
                setup_complete = threading.Event()
                setup_error: list[Optional[Exception]] = [None]

                def run_setup() -> None:
                    try:
                        postgres_saver.setup()
                        setup_complete.set()
                    except Exception as e:
                        setup_error[0] = e
                        setup_complete.set()

                setup_thread = threading.Thread(target=run_setup, daemon=True)
                setup_thread.start()
                setup_thread.join(timeout=60)

                if not setup_complete.is_set():
                    logger.error("PostgresSaver.setup() exceeded 60 second timeout")
                    raise TimeoutError(
                        "PostgresSaver.setup() exceeded 60 second timeout"
                    )

                if setup_error[0]:
                    raise setup_error[0]

                print(
                    "✅ LangGraph PostgreSQL checkpoint tables setup completed successfully"
                )
                logger.info(
                    "✅ LangGraph PostgreSQL checkpoint tables setup completed successfully"
                )
            except TimeoutError as timeout_err:
                # Timeout errors indicate a hang - fail the job so it can retry
                logger.error(
                    "PostgresSaver.setup() timed out - this may indicate a database issue. Job will fail and retry.",
                    error=str(timeout_err),
                    error_type=type(timeout_err).__name__,
                )
                # Re-raise to fail the job and trigger retry
                raise
            except psycopg.Error as db_error:
                logger.error(
                    "Database error during PostgresSaver setup",
                    error=str(db_error),
                    error_code=getattr(db_error, "pgcode", "unknown"),
                )
                raise
            except Exception as setup_error:
                logger.error(
                    "Unexpected error during PostgresSaver setup",
                    error=str(setup_error),
                    error_type=type(setup_error).__name__,
                )
                raise
            finally:
                try:
                    conn.close()
                    logger.debug("PostgresSaver connection closed successfully")
                except Exception as close_error:
                    logger.warning(
                        "Error closing PostgresSaver connection",
                        error=str(close_error),
                        error_type=type(close_error).__name__,
                    )

        except TimeoutError as timeout_err:
            # Timeout errors indicate a hang - fail the job so it can retry
            logger.error(
                "PostgresSaver.setup() timed out - this may indicate a database issue. Job will fail and retry.",
                error=str(timeout_err),
                error_type=type(timeout_err).__name__,
            )
            logger.exception("Full PostgresSaver setup timeout traceback:")
            # Re-raise to fail the job and trigger retry
            raise
        except Exception as e:
            # Checkpointing is REQUIRED for agent service functionality
            # If setup fails, the app cannot create ConversationSession instances
            logger.error(
                "Failed to setup LangGraph checkpoint tables - this is required for agent service functionality",
                error=str(e),
                error_type=type(e).__name__,
            )
            logger.exception("Full PostgresSaver setup error traceback:")
            # Fail the job so it can retry - checkpointing is required
            raise

        # Now run Alembic migrations after checkpoint tables are ready
        logger.info("Starting Alembic upgrade to head...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")

        # Restore original working directory
        os.chdir(original_cwd)
    except Exception as e:
        logger.error(
            "Migration failed",
            error=str(e),
            error_type=type(e).__name__,
        )
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
        logger.error(
            "Migration process failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        logger.exception("Full process error traceback:")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
