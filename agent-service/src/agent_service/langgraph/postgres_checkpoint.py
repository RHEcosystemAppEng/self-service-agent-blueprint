"""
PostgreSQL checkpoint implementation for LangGraph.

This module provides PostgreSQL-based checkpointing for LangGraph state machines.
The LangGraph tables are set up by the database migration job, so this module
just creates AsyncPostgresSaver instances with proper connection management.
"""

from typing import Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from shared_models import configure_logging
from shared_models.database import get_database_manager

logger = configure_logging("agent-service")

# Global checkpointer instance for connection reuse
_checkpointer: Optional[AsyncPostgresSaver] = None


async def get_postgres_checkpointer() -> AsyncPostgresSaver:
    """Get an AsyncPostgresSaver instance with proper connection management using shared configuration.

    Uses a singleton pattern to reuse the same checkpointer instance across the application,
    which improves performance by reusing the underlying database connection pool.

    If the connection is closed, recreates the checkpointer to allow the session to retry.
    """
    global _checkpointer

    if _checkpointer is None:
        try:
            # LangGraph tables should already be set up by the database migration job
            # Get an async connection from the pool for the checkpointer
            db_manager = get_database_manager()
            conn = await db_manager.get_async_connection()
            _checkpointer = AsyncPostgresSaver(conn)
            logger.debug(
                "Created AsyncPostgresSaver with shared configuration and connection pooling"
            )
        except Exception as e:
            logger.error(
                "Failed to create AsyncPostgresSaver",
                error=str(e),
                error_type=type(e).__name__,
            )
            _checkpointer = None
            raise
    else:
        logger.debug("Reusing existing AsyncPostgresSaver instance")

    return _checkpointer


def close_postgres_checkpointer() -> None:
    """Close the AsyncPostgresSaver instance and clean up resources."""
    global _checkpointer

    if _checkpointer is not None:
        try:
            # AsyncPostgresSaver doesn't have an explicit close method, but we can clear our reference
            # The underlying connection will be managed by the DatabaseManager
            _checkpointer = None
            logger.debug("AsyncPostgresSaver instance cleared")
        except Exception as e:
            logger.warning(
                "Error closing AsyncPostgresSaver",
                error=str(e),
                error_type=type(e).__name__,
            )
    else:
        logger.debug("No AsyncPostgresSaver instance to close")


def reset_postgres_checkpointer() -> None:
    """Reset the AsyncPostgresSaver instance to force recreation on next access.

    Use this when the connection is lost to allow a new connection to be created.
    """
    global _checkpointer

    if _checkpointer is not None:
        logger.warning("Resetting AsyncPostgresSaver instance due to connection issue")
        _checkpointer = None
    else:
        logger.debug("No AsyncPostgresSaver instance to reset")
