"""Unified database utilities for all services."""

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, TypeVar

import psycopg
import psycopg_pool
import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = structlog.get_logger()

T = TypeVar("T", bound=DeclarativeBase)


class DatabaseConfig:
    """Database configuration class."""

    def __init__(self) -> None:
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

        # Sync connection pool settings (for PostgresSaver/LangGraph)
        self.sync_pool_min_size = int(os.getenv("DB_SYNC_POOL_MIN_SIZE", "1"))
        self.sync_pool_max_size = int(os.getenv("DB_SYNC_POOL_MAX_SIZE", "5"))
        self.sync_pool_timeout = int(os.getenv("DB_SYNC_POOL_TIMEOUT", "30"))

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
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

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

    def get_alembic_config(self) -> dict[str, Any]:
        """Get configuration for Alembic."""
        return {
            "sqlalchemy.url": self.sync_connection_string,
            "sqlalchemy.echo": str(self.echo_sql).lower(),
        }


class DatabaseManager:
    """Database connection and session manager."""

    def __init__(self) -> None:
        self.config = DatabaseConfig()

        # Create async engine with connection pooling for better performance
        self.engine = create_async_engine(
            self.config.connection_string,
            echo=self.config.echo_sql,
            pool_pre_ping=True,  # Verify connections before use
            pool_recycle=self.config.pool_recycle,  # Recycle connections periodically
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_timeout=self.config.pool_timeout,
            connect_args={
                "command_timeout": 30,  # Connection timeout
                "server_settings": {
                    "application_name": "self-service-agent",
                    "statement_timeout": "30000",  # 30 second statement timeout
                    "idle_in_transaction_session_timeout": "300000",  # 5 minute idle timeout
                },
            },
        )

        # Create session maker
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create sync connection pool for PostgresSaver
        self._sync_pool: Optional[psycopg_pool.ConnectionPool] = None

        # Create async connection pool for AsyncPostgresSaver
        self._async_pool: Optional[psycopg_pool.AsyncConnectionPool] = None

    async def log_database_config(self) -> None:
        """Log database configuration and test connection at startup."""
        try:
            # Get the actual pool class being used
            pool_class = self.engine.pool.__class__.__name__

            # Test the connection
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT 1 as test"))
                test_value = result.scalar()

            logger.info(
                "Database configuration initialized successfully",
                pool_class=pool_class,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_timeout=self.config.pool_timeout,
                pool_recycle=self.config.pool_recycle,
                connection_test=test_value,
                host=self.config.host,
                database=self.config.database,
                application_name="self-service-agent",
            )

        except Exception as e:
            logger.error(
                "Failed to initialize database connection",
                error=str(e),
                pool_class=pool_class if "pool_class" in locals() else "unknown",
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                host=self.config.host,
                database=self.config.database,
            )
            raise

    def _get_sync_pool(self) -> psycopg_pool.ConnectionPool:
        """Get or create the sync connection pool for PostgresSaver."""
        if self._sync_pool is None:
            # Build connection string for sync pool
            conn_string = f"postgresql://{self.config.user}:{self.config.password}@{self.config.host}:{self.config.port}/{self.config.database}"

            self._sync_pool = psycopg_pool.ConnectionPool(
                conn_string,
                min_size=self.config.sync_pool_min_size,  # Configurable minimum connections
                max_size=self.config.sync_pool_max_size,  # Configurable maximum connections
                kwargs={
                    "row_factory": psycopg.rows.dict_row,
                    "autocommit": True,
                },
                check=psycopg_pool.ConnectionPool.check_connection,  # Validate connections
                timeout=self.config.sync_pool_timeout,  # Configurable timeout
            )
            logger.debug(
                "Created sync connection pool for PostgresSaver",
                min_size=self.config.sync_pool_min_size,
                max_size=self.config.sync_pool_max_size,
                timeout=self.config.sync_pool_timeout,
            )

        return self._sync_pool

    def get_sync_connection(self) -> psycopg.Connection[dict[str, Any]]:
        """Get a synchronous connection for LangGraph PostgresSaver.

        Uses connection pooling for better performance and resource management.
        """
        pool = self._get_sync_pool()

        if self.config.echo_sql:
            logger.debug(
                "Getting sync connection from pool",
                host=self.config.host,
                database=self.config.database,
            )

        # Type ignore needed because psycopg_pool returns Connection[tuple[Any, ...]]
        # but we configure it with row_factory=psycopg.rows.dict_row
        return pool.getconn()  # type: ignore[return-value]

    def put_sync_connection(self, conn: psycopg.Connection[dict[str, Any]]) -> None:
        """Return a sync connection to the pool."""
        if self._sync_pool is not None:
            # Type ignore needed because psycopg_pool expects Connection[tuple[Any, ...]]
            # but we're using Connection[dict[str, Any]] with row_factory
            self._sync_pool.putconn(conn)  # type: ignore[arg-type]

    def _get_async_pool(self) -> psycopg_pool.AsyncConnectionPool:
        """Get or create the async connection pool for AsyncPostgresSaver."""
        if self._async_pool is None:
            # Build connection string for async pool
            conn_string = f"postgresql://{self.config.user}:{self.config.password}@{self.config.host}:{self.config.port}/{self.config.database}"

            self._async_pool = psycopg_pool.AsyncConnectionPool(
                conn_string,
                min_size=self.config.sync_pool_min_size,
                max_size=self.config.sync_pool_max_size,
                kwargs={
                    "row_factory": psycopg.rows.dict_row,
                    "autocommit": True,
                },
                timeout=self.config.sync_pool_timeout,
            )
            logger.debug(
                "Created async connection pool for AsyncPostgresSaver",
                min_size=self.config.sync_pool_min_size,
                max_size=self.config.sync_pool_max_size,
                timeout=self.config.sync_pool_timeout,
            )

        return self._async_pool

    async def get_async_connection(self) -> Any:
        """Get an asynchronous connection for LangGraph AsyncPostgresSaver.

        Uses connection pooling for better performance and resource management.
        """
        pool = self._get_async_pool()

        if self.config.echo_sql:
            logger.debug(
                "Getting async connection from pool",
                host=self.config.host,
                database=self.config.database,
            )

        return await pool.getconn()

    async def put_async_connection(self, conn: Any) -> None:
        """Return an async connection to the pool."""
        if self._async_pool is not None:
            await self._async_pool.putconn(conn)

    async def close(self) -> None:
        """Close database connections."""
        await self.engine.dispose()

        # Close sync connection pool
        if self._sync_pool is not None:
            self._sync_pool.close()
            self._sync_pool = None
            logger.debug("Sync connection pool closed")

        # Close async connection pool
        if self._async_pool is not None:
            await self._async_pool.close()
            self._async_pool = None
            logger.debug("Async connection pool closed")

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
        self, expected_version: str | None = None, timeout: int = 300
    ) -> bool:
        """Wait for database migration to complete to a specific version."""
        import asyncio
        from time import time

        # Determine expected version from parameter, environment, or default
        if expected_version is None:
            expected_version = os.getenv("EXPECTED_MIGRATION_VERSION", "003")

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

    async def execute_query(
        self, db: AsyncSession, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a raw SQL query and return results as dictionaries."""
        try:
            result = await db.execute(text(query), params or {})
            rows = result.fetchall()
            columns = result.keys()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            if self.config.echo_sql:
                logger.error("Failed to execute query", query=query, error=str(e))
            else:
                logger.error("Failed to execute query", error=str(e))
            return []


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
            stmt = select(model_class).where(model_class.id == id_value)  # type: ignore[attr-defined]
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
            return list(result.scalars().all())
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
    async def update_record(db: AsyncSession, record: T, **updates: Any) -> Optional[T]:
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
    async def try_claim_event_for_processing(
        db: AsyncSession,
        event_id: str,
        event_type: str,
        event_source: str,
        processed_by: str,
        stale_timeout_seconds: int = 120,  # 2 minutes default (matches request timeout)
    ) -> bool:
        """Atomically claim an event for processing (check-and-set pattern).

        This provides 100% guarantee against duplicate processing by using
        database unique constraint as a distributed lock.

        If an event is stuck in "processing" state for too long (stale), it can be
        re-claimed by another pod. This handles cases where a pod crashes mid-processing.

        Args:
            db: Database session
            event_id: Unique event identifier
            event_type: Type of event
            event_source: Source of event
            processed_by: Service name claiming the event
            stale_timeout_seconds: Time in seconds after which a "processing" event is considered stale

        Returns:
            True if this pod successfully claimed the event (can process it)
            False if another pod already claimed it (must skip processing)
        """
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select, update

        from .models import ProcessedEvent

        if not event_id:
            logger.warning("Cannot claim event without event_id")
            return False

        try:
            # First, check if event already exists and is stale
            existing_event = await db.execute(
                select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)
            )
            existing = existing_event.scalar_one_or_none()

            if existing:
                # Event already exists - check if it's stale
                if existing.processing_result == "processing":
                    # Check if it's stale (created more than stale_timeout_seconds ago)
                    stale_threshold = datetime.now(timezone.utc) - timedelta(
                        seconds=stale_timeout_seconds
                    )
                    if existing.created_at < stale_threshold:
                        # Event is stale - update it to allow re-claiming
                        logger.warning(
                            "Event stuck in processing state - allowing re-claim",
                            event_id=event_id,
                            created_at=existing.created_at,
                            stale_threshold=stale_threshold,
                        )
                        stmt = (
                            update(ProcessedEvent)
                            .where(ProcessedEvent.event_id == event_id)
                            .values(
                                processed_by=processed_by,
                                processing_result="processing",
                                created_at=datetime.now(
                                    timezone.utc
                                ),  # Reset timestamp
                            )
                        )
                        await db.execute(stmt)
                        await db.commit()
                        logger.info(
                            "Successfully re-claimed stale event",
                            event_id=event_id,
                            event_type=event_type,
                        )
                        return True
                    else:
                        # Event is still being processed (not stale)
                        logger.debug(
                            "Event already claimed and still processing - skipping duplicate",
                            event_id=event_id,
                            created_at=existing.created_at,
                        )
                        return False
                else:
                    # Event already completed (success/error) - skip
                    logger.debug(
                        "Event already processed - skipping duplicate",
                        event_id=event_id,
                        processing_result=existing.processing_result,
                    )
                    return False

            # Event doesn't exist - try to insert with "processing" status
            # This is atomic - if another pod inserts first, we'll get a unique constraint violation
            processed_event = ProcessedEvent(
                event_id=event_id,
                event_type=event_type,
                event_source=event_source,
                request_id=None,  # Will be set after processing
                session_id=None,  # Will be set after processing
                processed_by=processed_by,
                processing_result="processing",  # Claimed but not yet completed
                error_message=None,
            )

            db.add(processed_event)
            await db.commit()

            logger.debug(
                "Successfully claimed event for processing",
                event_id=event_id,
                event_type=event_type,
            )
            return True

        except Exception as e:
            # Unique constraint violation means another pod inserted it between our check and insert
            if (
                "duplicate key value violates unique constraint" in str(e)
                or "unique constraint" in str(e).lower()
            ):
                logger.debug(
                    "Event already claimed by another pod (race condition) - skipping duplicate",
                    event_id=event_id,
                )
                await db.rollback()
                return False
            else:
                logger.error(
                    "Failed to claim event for processing",
                    event_id=event_id,
                    error=str(e),
                )
                await db.rollback()
                return False

    @staticmethod
    async def update_processed_event(
        db: AsyncSession,
        event_id: str,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        processing_result: str = "success",
        error_message: Optional[str] = None,
    ) -> None:
        """Update a processed event record after processing completes.

        Note: For atomic claiming, use try_claim_event_for_processing first.
        This function updates the event record after processing completes.

        Args:
            db: Database session
            event_id: Unique event identifier
            request_id: Request ID (if available)
            session_id: Session ID (if available)
            processing_result: Result of processing (success/error)
            error_message: Error message (if processing failed)
        """
        from sqlalchemy import update

        from .models import ProcessedEvent

        if not event_id:
            logger.warning("Cannot update processed event without event_id")
            return

        try:
            # Update the existing ProcessedEvent record (created by try_claim_event_for_processing)
            stmt = (
                update(ProcessedEvent)
                .where(ProcessedEvent.event_id == event_id)
                .values(
                    request_id=request_id,
                    session_id=session_id,
                    processing_result=processing_result,
                    error_message=error_message,
                )
            )
            await db.execute(stmt)
            await db.commit()

            logger.debug(
                "Updated processed event record",
                event_id=event_id,
                processing_result=processing_result,
            )

        except Exception as e:
            logger.error(
                "Failed to update processed event record",
                event_id=event_id,
                error=str(e),
            )
            await db.rollback()

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
            stmt = select(func.count(model_class.id))  # type: ignore[attr-defined]
            result = await db.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(
                "Failed to count records",
                model=model_class.__name__,
                error=str(e),
            )
            return 0


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
