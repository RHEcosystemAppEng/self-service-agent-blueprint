"""Channel behavior schema: VARCHAR integration_type, default config rows, session index.

- Cast ``integration_type`` from Postgres ``integrationtype`` enum to ``VARCHAR(32)`` on all
  tables; drop enum type (new labels need code + registry only, not ``ALTER TYPE``).
- Idempotent ``integration_default_configs`` rows for delivery bootstrap (empty ``config``;
  channel policy lives in ``CHANNEL_REGISTRY``, not DB JSON).
- Partial unique index on active sessions using snapshot ``session_scope`` (not hardcoded ZAMMAD).
- Strip legacy ``config.channel_behavior`` keys if present.

Revision ID: 003
Revises: 002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INTEGRATION_TYPE_VARCHAR_LEN = 32

_TABLES_WITH_INTEGRATION_TYPE = (
    "request_sessions",
    "user_integration_configs",
    "integration_credentials",
    "delivery_logs",
    "integration_default_configs",
    "user_integration_mappings",
)

_ENUM_LABELS = (
    "SLACK",
    "WEB",
    "CLI",
    "TOOL",
    "EMAIL",
    "SMS",
    "WEBHOOK",
    "TEAMS",
    "DISCORD",
    "TEST",
    "ZAMMAD",
)

_PER_USER_TYPES = (
    "SLACK",
    "WEB",
    "EMAIL",
    "CLI",
    "TOOL",
    "SMS",
    "WEBHOOK",
    "TEST",
    "TEAMS",
    "DISCORD",
)

_ROW_PRIORITY: dict[str, int] = {
    "SLACK": 1,
    "EMAIL": 2,
    "WEBHOOK": 3,
    "SMS": 4,
    "TEST": 5,
    "ZAMMAD": 6,
}


def _drop_indexes_using_integrationtype_enum() -> None:
    """002's partial unique index compares to 'ZAMMAD'::integrationtype; drop before VARCHAR cast."""
    op.execute("DROP INDEX IF EXISTS idx_one_active_session_per_user_integration")


def _integration_type_columns_to_varchar() -> None:
    for table in _TABLES_WITH_INTEGRATION_TYPE:
        op.execute(
            f"""
            ALTER TABLE {table}
            ALTER COLUMN integration_type TYPE VARCHAR({_INTEGRATION_TYPE_VARCHAR_LEN})
            USING integration_type::text
            """
        )


def _integration_type_columns_to_enum() -> None:
    for table in _TABLES_WITH_INTEGRATION_TYPE:
        op.execute(
            sa.text(
                f"""
                ALTER TABLE {table}
                ALTER COLUMN integration_type TYPE integrationtype
                USING integration_type::integrationtype
                """
            )
        )


def _drop_integrationtype_enum() -> None:
    op.execute("DROP TYPE IF EXISTS integrationtype")


def _create_integrationtype_enum() -> None:
    labels = "', '".join(_ENUM_LABELS)
    op.execute(
        sa.text(
            f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'integrationtype') THEN
                    CREATE TYPE integrationtype AS ENUM ('{labels}');
                END IF;
            END $$;
            """
        )
    )


def _strip_channel_behavior_from_default_configs() -> None:
    op.execute(
        """
        UPDATE integration_default_configs
        SET config = (config::jsonb - 'channel_behavior')::json,
            updated_at = CURRENT_TIMESTAMP
        WHERE config::jsonb ? 'channel_behavior'
        """
    )


def _ensure_default_config_row(integration_type: str) -> None:
    priority = _ROW_PRIORITY.get(integration_type, 10)
    op.execute(
        sa.text(
            """
            INSERT INTO integration_default_configs (
                integration_type,
                enabled,
                config,
                priority,
                retry_count,
                retry_delay_seconds
            )
            VALUES (
                :it,
                false,
                '{}'::json,
                :priority,
                3,
                60
            )
            ON CONFLICT (integration_type) DO NOTHING
            """
        ).bindparams(it=integration_type, priority=priority)
    )


def _recreate_per_user_active_session_index() -> None:
    """One active session per user+integration unless snapshot scope is PER_TICKET."""
    op.execute("DROP INDEX IF EXISTS idx_one_active_session_per_user_integration")
    op.execute(
        """
        CREATE UNIQUE INDEX idx_one_active_session_per_user_integration
        ON request_sessions (user_id, integration_type)
        WHERE status = 'ACTIVE'
          AND integration_type IS NOT NULL
          AND COALESCE(
                integration_metadata->'_channel_behavior'->>'session_scope',
                ''
              ) <> 'PER_TICKET'
        """
    )


def _recreate_zammad_exclusion_index() -> None:
    """Unique active session index excluding ZAMMAD (downgrade path)."""
    op.execute("DROP INDEX IF EXISTS idx_one_active_session_per_user_integration")
    op.execute(
        """
        CREATE UNIQUE INDEX idx_one_active_session_per_user_integration
        ON request_sessions (user_id, integration_type)
        WHERE status = 'ACTIVE'
          AND integration_type IS NOT NULL
          AND integration_type <> 'ZAMMAD'::integrationtype
        """
    )


def upgrade() -> None:
    _drop_indexes_using_integrationtype_enum()
    _integration_type_columns_to_varchar()
    _drop_integrationtype_enum()

    all_types = ("ZAMMAD",) + _PER_USER_TYPES
    for it in all_types:
        _ensure_default_config_row(it)

    _strip_channel_behavior_from_default_configs()
    _recreate_per_user_active_session_index()


def downgrade() -> None:
    _create_integrationtype_enum()
    _integration_type_columns_to_enum()
    _recreate_zammad_exclusion_index()
