"""Alembic environment configuration."""

from logging.config import fileConfig

from alembic import context

# Import the shared database configuration
from shared_models.database import get_db_config
from shared_models.models import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the database URL from our configuration
db_config = get_db_config()
config.set_main_option("sqlalchemy.url", db_config.sync_connection_string)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with database connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    import logging

    logger = logging.getLogger("alembic.env")

    logger.info("Starting online migrations")

    # Use sync engine for migrations to avoid async issues
    db_config = get_db_config()

    logger.debug(f"Database config: {db_config.sync_connection_string}")

    # Create sync engine directly
    from sqlalchemy import create_engine

    logger.debug("Creating database engine...")
    engine = create_engine(
        db_config.sync_connection_string,
        poolclass=pool.NullPool,
        echo=True,  # Enable SQL logging
    )

    logger.debug("Connecting to database...")
    with engine.connect() as connection:
        logger.debug("Configuring Alembic context...")
        # Configure Alembic with proper schema validation and transactions
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,
        )

        logger.debug("Running migrations with proper transaction context...")
        with context.begin_transaction():
            context.run_migrations()
        logger.debug("Migrations completed")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
