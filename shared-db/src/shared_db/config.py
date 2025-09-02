"""Database configuration and connection management."""

import os
from typing import Optional

import structlog

logger = structlog.get_logger()


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


# Global configuration instance
_config: Optional[DatabaseConfig] = None


def get_db_config() -> DatabaseConfig:
    """Get the global database configuration."""
    global _config
    if _config is None:
        _config = DatabaseConfig()
        if not _config.validate():
            raise ValueError("Invalid database configuration")
    return _config
