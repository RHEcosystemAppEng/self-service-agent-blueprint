"""Unified database utilities for all services."""

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, TypeVar

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

logger = structlog.get_logger()

T = TypeVar("T", bound=DeclarativeBase)


class DatabaseConfig:
    """Database configuration class."""

    def __init__(self):
        # PostgreSQL connection parameters
        self.host = os.getenv("POSTGRES_HOST", "pgvector")
        self.port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.database = os.getenv("POSTGRES_DB", "llama_agents")
        self.user = os.getenv("POSTGRES_USER", "pgvector")
        self.password = os.getenv("POSTGRES_PASSWORD", "pgvector")

        # Connection pool settings
        self.pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
        self.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
        self.pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))

        # Debug settings
        self.echo_sql = os.getenv("SQL_DEBUG", "false").lower() == "true"

        # Connection string
        self._connection_string = self._build_connection_string()

    def _build_connection_string(self) -> str:
        """Build PostgreSQL connection string."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def connection_string(self) -> str:
        """Get the database connection string."""
        return self._connection_string

    @property
    def sync_connection_string(self) -> str:
        """Get the synchronous database connection string (for Alembic)."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    def validate(self) -> bool:
        """Validate database configuration."""
        required_fields = [self.host, self.database, self.user]

        if not all(required_fields):
            logger.error(
                "Database configuration incomplete",
                host=self.host,
                database=self.database,
                user=self.user,
                password_set=bool(self.password),
            )
            return False

        return True

    def get_alembic_config(self) -> dict:
        """Get configuration for Alembic."""
        return {
            "sqlalchemy.url": self.sync_connection_string,
            "sqlalchemy.echo": str(self.echo_sql).lower(),
        }


class DatabaseManager:
    """Database connection and session manager."""

    def __init__(self):
        self.config = DatabaseConfig()

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
        """Wait for database migration to complete to a specific version."""
        import asyncio
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


class DatabaseUtils:
    """Shared database utility functions."""

    @staticmethod
    async def test_connection(db: AsyncSession) -> bool:
        """Test database connection."""
        try:
            await db.execute(text("SELECT 1"))
            logger.debug("Database connection test successful")
            return True
        except Exception as e:
            logger.error("Database connection test failed", error=str(e))
            return False

    @staticmethod
    async def get_by_id(
        db: AsyncSession, model_class: Type[T], id_value: Any
    ) -> Optional[T]:
        """Get a record by ID."""
        try:
            stmt = select(model_class).where(model_class.id == id_value)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                "Failed to get record by ID",
                model=model_class.__name__,
                id=id_value,
                error=str(e),
            )
            return None

    @staticmethod
    async def get_by_field(
        db: AsyncSession, model_class: Type[T], field_name: str, field_value: Any
    ) -> Optional[T]:
        """Get a record by a specific field."""
        try:
            field = getattr(model_class, field_name)
            stmt = select(model_class).where(field == field_value)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                "Failed to get record by field",
                model=model_class.__name__,
                field=field_name,
                value=field_value,
                error=str(e),
            )
            return None

    @staticmethod
    async def get_all(
        db: AsyncSession, model_class: Type[T], limit: int = 100, offset: int = 0
    ) -> List[T]:
        """Get all records with pagination."""
        try:
            stmt = select(model_class).limit(limit).offset(offset)
            result = await db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(
                "Failed to get all records",
                model=model_class.__name__,
                error=str(e),
            )
            return []

    @staticmethod
    async def create_record(db: AsyncSession, record: T) -> Optional[T]:
        """Create a new record."""
        try:
            db.add(record)
            await db.commit()
            await db.refresh(record)
            logger.debug("Record created successfully", model=record.__class__.__name__)
            return record
        except Exception as e:
            logger.error(
                "Failed to create record",
                model=record.__class__.__name__,
                error=str(e),
            )
            await db.rollback()
            return None

    @staticmethod
    async def update_record(db: AsyncSession, record: T, **updates) -> Optional[T]:
        """Update a record with provided fields."""
        try:
            for field, value in updates.items():
                if hasattr(record, field):
                    setattr(record, field, value)

            await db.commit()
            await db.refresh(record)
            logger.debug("Record updated successfully", model=record.__class__.__name__)
            return record
        except Exception as e:
            logger.error(
                "Failed to update record",
                model=record.__class__.__name__,
                error=str(e),
            )
            await db.rollback()
            return None

    @staticmethod
    async def delete_record(db: AsyncSession, record: T) -> bool:
        """Delete a record."""
        try:
            await db.delete(record)
            await db.commit()
            logger.debug("Record deleted successfully", model=record.__class__.__name__)
            return True
        except Exception as e:
            logger.error(
                "Failed to delete record",
                model=record.__class__.__name__,
                error=str(e),
            )
            await db.rollback()
            return False

    @staticmethod
    async def count_records(db: AsyncSession, model_class: Type[T]) -> int:
        """Count total records in a table."""
        try:
            stmt = select(func.count(model_class.id))
            result = await db.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(
                "Failed to count records",
                model=model_class.__name__,
                error=str(e),
            )
            return 0

    @staticmethod
    async def execute_query(
        db: AsyncSession, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a raw SQL query and return results as dictionaries."""
        try:
            result = await db.execute(text(query), params or {})
            rows = result.fetchall()
            columns = result.keys()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error("Failed to execute query", query=query, error=str(e))
            return []


class DatabaseHealthChecker:
    """Database-specific health checking utilities."""

    @staticmethod
    async def check_connection(db: AsyncSession) -> Dict[str, Any]:
        """Check database connection health."""
        try:
            # Test basic connectivity
            await db.execute(text("SELECT 1"))

            # Test transaction capability
            await db.begin()
            await db.rollback()

            return {
                "status": "healthy",
                "connection": True,
                "transactions": True,
            }
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "connection": False,
                "transactions": False,
                "error": str(e),
            }

    @staticmethod
    async def check_table_access(db: AsyncSession, table_name: str) -> Dict[str, Any]:
        """Check if a specific table is accessible."""
        try:
            await db.execute(text(f"SELECT COUNT(*) FROM {table_name} LIMIT 1"))
            return {
                "status": "healthy",
                "table": table_name,
                "accessible": True,
            }
        except Exception as e:
            logger.error("Table access check failed", table=table_name, error=str(e))
            return {
                "status": "unhealthy",
                "table": table_name,
                "accessible": False,
                "error": str(e),
            }


# Global database manager instance
_db_manager = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_db_config() -> DatabaseConfig:
    """Get the global database configuration."""
    return get_database_manager().config


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions with automatic cleanup."""
    db_manager = get_database_manager()
    async with db_manager.get_session() as session:
        try:
            yield session
        except Exception as e:
            logger.error("Database session error", error=str(e))
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    db_manager = get_database_manager()
    async with db_manager.get_session() as session:
        try:
            yield session
        except Exception as e:
            logger.error("Database session error", error=str(e))
            await session.rollback()
            raise
        finally:
            await session.close()
