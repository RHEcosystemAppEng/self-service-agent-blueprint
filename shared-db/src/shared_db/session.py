"""Database session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .config import get_db_config

logger = structlog.get_logger()


class DatabaseManager:
    """Database connection and session manager."""

    def __init__(self):
        self.config = get_db_config()

        # Create async engine
        self.engine = create_async_engine(
            self.config.connection_string,
            poolclass=NullPool,  # Use NullPool for serverless/Knative
            echo=self.config.echo_sql,
            pool_pre_ping=True,  # Validate connections before use
        )

        # Create session maker
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info(
            "Database manager initialized",
            host=self.config.host,
            database=self.config.database,
            user=self.config.user,
        )

    async def create_tables(self) -> None:
        """Create all database tables."""
        # NOTE: Table creation is now handled by Alembic migrations
        # This method is kept for backward compatibility but does nothing
        logger.info(
            "Database tables managed by Alembic migrations - skipping create_all"
        )

    async def close(self) -> None:
        """Close database connections."""
        await self.engine.dispose()
        logger.info("Database connections closed")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        async with self.async_session() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.get_session() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False

    async def wait_for_migration(
        self, expected_version: str = None, timeout: int = 300
    ) -> bool:
        """Wait for database migration to complete to a specific version.

        Args:
            expected_version: The Alembic revision ID to wait for. If None, uses
                             EXPECTED_MIGRATION_VERSION env var or defaults to "001"
            timeout: Maximum time to wait in seconds (default: 300)

        Returns:
            True if migration completed successfully, False if timeout
        """
        import asyncio
        import os
        from time import time

        # Determine expected version from parameter, environment, or default
        if expected_version is None:
            expected_version = os.getenv("EXPECTED_MIGRATION_VERSION", "001")

        start_time = time()
        logger.info(
            "Waiting for database migration to complete",
            expected_version=expected_version,
        )

        while (time() - start_time) < timeout:
            try:
                async with self.get_session() as session:
                    # Check if alembic_version table exists and has the expected version
                    result = await session.execute(
                        text(
                            "SELECT version_num FROM alembic_version WHERE version_num = :version"
                        ),
                        {"version": expected_version},
                    )
                    version_row = result.fetchone()

                    if not version_row:
                        logger.debug(
                            "Migration version not ready",
                            expected=expected_version,
                            current="not found or different",
                        )
                        await asyncio.sleep(5)
                        continue

                    # Verify that key tables from this migration exist and are accessible
                    await session.execute(
                        text("SELECT 1 FROM request_sessions LIMIT 1")
                    )
                    await session.execute(text("SELECT 1 FROM request_logs LIMIT 1"))
                    await session.execute(
                        text("SELECT 1 FROM user_integration_configs LIMIT 1")
                    )
                    await session.execute(
                        text("SELECT 1 FROM integration_templates LIMIT 1")
                    )
                    await session.execute(
                        text("SELECT 1 FROM integration_credentials LIMIT 1")
                    )
                    await session.execute(text("SELECT 1 FROM delivery_logs LIMIT 1"))

                    logger.info(
                        "Database migration completed successfully",
                        version=expected_version,
                        elapsed_seconds=int(time() - start_time),
                    )
                    return True

            except Exception as e:
                logger.debug(
                    "Migration not ready yet",
                    expected_version=expected_version,
                    error=str(e),
                )
                await asyncio.sleep(5)

        logger.error(
            "Timeout waiting for database migration",
            expected_version=expected_version,
            timeout=timeout,
        )
        return False


# Global database manager instance
_db_manager = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to get a database session."""
    db_manager = get_database_manager()
    async with db_manager.get_session() as session:
        yield session
