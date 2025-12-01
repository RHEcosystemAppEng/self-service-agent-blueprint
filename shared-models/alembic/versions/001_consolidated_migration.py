"""Initial database schema for self-service agent system

Creates all required tables for the self-service agent system including:
- Users table with canonical UUID-based user_id
- Request sessions and logging with token tracking
- User integration configurations and smart defaults
- Integration credentials
- Delivery logs and processed events
- User integration mappings
- PostgreSQL advisory lock function

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Create enums using raw SQL to avoid SQLAlchemy auto-management issues
    connection = op.get_bind()

    # Create enums if they don't exist - values must match the model enums exactly
    enums_to_create = [
        (
            "integrationtype",
            [
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
            ],
        ),
        ("sessionstatus", ["ACTIVE", "INACTIVE", "EXPIRED", "ARCHIVED"]),
        ("deliverystatus", ["PENDING", "DELIVERED", "FAILED", "RETRYING", "EXPIRED"]),
    ]

    # Create enums using DO blocks to handle IF NOT EXISTS logic
    try:
        for enum_name, enum_values in enums_to_create:
            values_str = "', '".join(enum_values)
            connection.execute(
                sa.text(
                    f"""
                    DO $$ BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
                            CREATE TYPE {enum_name} AS ENUM ('{values_str}');
                        END IF;
                    END $$;
                """
                )
            )

    except Exception:
        import traceback

        traceback.print_exc()
        raise

    # Use PostgreSQL ENUM type that references existing enums without creating them
    from sqlalchemy.dialects.postgresql import ENUM

    # These reference the enums we created above - no values needed since they exist
    integration_type_enum = ENUM(name="integrationtype", create_type=False)
    session_status_enum = ENUM(name="sessionstatus", create_type=False)
    delivery_status_enum = ENUM(name="deliverystatus", create_type=False)

    # Create users table
    op.create_table(
        "users",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("primary_email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_users_primary_email", "users", ["primary_email"], unique=True)

    # Create request_sessions table
    op.create_table(
        "request_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column("integration_type", integration_type_enum, nullable=False),
        sa.Column("status", session_status_enum, nullable=False),
        sa.Column("channel_id", sa.String(length=255), nullable=True),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("integration_metadata", sa.JSON(), nullable=True),
        sa.Column("total_requests", sa.Integer(), nullable=False),
        sa.Column(
            "last_request_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # Additional fields
        sa.Column("external_session_id", sa.String(length=255), nullable=True),
        sa.Column("current_agent_id", sa.String(length=255), nullable=True),
        sa.Column("conversation_thread_id", sa.String(length=255), nullable=True),
        sa.Column("user_context", sa.JSON(), nullable=True),
        sa.Column("conversation_context", sa.JSON(), nullable=True),
        sa.Column("last_request_id", sa.String(length=36), nullable=True),
        # Token tracking fields
        sa.Column(
            "total_input_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_output_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "max_input_tokens_per_call",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_output_tokens_per_call",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_total_tokens_per_call",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_sessions")),
        sa.UniqueConstraint("session_id", name=op.f("uq_request_sessions_session_id")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_request_sessions_user_id"),
        ),
    )
    op.create_index(
        op.f("ix_session_id"), "request_sessions", ["session_id"], unique=False
    )
    op.create_index(
        "ix_request_sessions_user_id", "request_sessions", ["user_id"], unique=False
    )

    # Create request_logs table
    op.create_table(
        "request_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("request_type", sa.String(length=50), nullable=False),
        sa.Column("request_content", sa.Text(), nullable=False),
        sa.Column("normalized_request", sa.JSON(), nullable=True),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("response_content", sa.Text(), nullable=True),
        sa.Column("response_metadata", sa.JSON(), nullable=True),
        sa.Column("cloudevent_id", sa.String(length=36), nullable=True),
        sa.Column("cloudevent_type", sa.String(length=100), nullable=True),
        sa.Column("pod_name", sa.String(255), nullable=True),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["request_sessions.session_id"],
            name=op.f("fk_request_logs_session_id_request_sessions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_logs")),
        sa.UniqueConstraint("request_id", name=op.f("uq_request_logs_request_id")),
    )
    op.create_index(op.f("ix_request_id"), "request_logs", ["request_id"], unique=False)
    op.create_index(
        op.f("ix_request_logs_session_id"), "request_logs", ["session_id"], unique=False
    )
    op.create_index(
        op.f("ix_request_logs_agent_id"), "request_logs", ["agent_id"], unique=False
    )
    op.create_index(
        "ix_request_logs_pod_name", "request_logs", ["pod_name"], unique=False
    )

    # Create user_integration_configs table
    op.create_table(
        "user_integration_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column("integration_type", integration_type_enum, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_integration_configs")),
        sa.UniqueConstraint("user_id", "integration_type", name="uq_user_integration"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_user_integration_configs_user_id"),
        ),
    )
    op.create_index(
        "ix_user_integration_configs_user_id",
        "user_integration_configs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_integration_configs_integration_type",
        "user_integration_configs",
        ["integration_type"],
        unique=False,
    )

    # Create integration_credentials table
    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("integration_type", integration_type_enum, nullable=False),
        sa.Column("credential_name", sa.String(length=100), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_credentials")),
        sa.UniqueConstraint(
            "integration_type", "credential_name", name="uq_integration_credential"
        ),
    )

    # Create delivery_logs table
    op.create_table(
        "delivery_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column(
            "integration_config_id", sa.Integer(), nullable=True
        ),  # Allow null for smart defaults
        sa.Column("integration_type", integration_type_enum, nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", delivery_status_enum, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "first_attempt_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "last_attempt_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column("delivered_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.Column("integration_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["integration_config_id"],
            ["user_integration_configs.id"],
            name=op.f(
                "fk_delivery_logs_integration_config_id_user_integration_configs"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_delivery_logs_user_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_logs")),
    )
    op.create_index(
        "ix_delivery_logs_request_id", "delivery_logs", ["request_id"], unique=False
    )
    op.create_index(
        "ix_delivery_logs_session_id", "delivery_logs", ["session_id"], unique=False
    )
    op.create_index(
        "ix_delivery_logs_user_id", "delivery_logs", ["user_id"], unique=False
    )

    # Create processed_events table
    op.create_table(
        "processed_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("event_source", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("processed_by", sa.String(length=100), nullable=False),
        sa.Column("processing_result", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )

    # Create indexes for processed_events table
    op.create_index(
        "ix_processed_events_event_id", "processed_events", ["event_id"], unique=False
    )
    op.create_index(
        "ix_processed_events_request_id",
        "processed_events",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_processed_events_created_at",
        "processed_events",
        ["created_at"],
        unique=False,
    )

    # Create integration_default_configs table
    op.create_table(
        "integration_default_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("integration_type", integration_type_enum, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_default_configs")),
        sa.UniqueConstraint("integration_type", name="uq_integration_default_type"),
    )

    # Create user_integration_mappings table
    op.create_table(
        "user_integration_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=False),
        sa.Column(
            "integration_type",
            postgresql.ENUM(name="integrationtype", create_type=False),
            nullable=False,
        ),
        sa.Column("integration_user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column("last_validated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("validation_attempts", sa.Integer(), nullable=False, default=0),
        sa.Column("last_validation_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True, default="system"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_user_integration_mappings_user_id"),
        ),
    )

    # Create indexes for user_integration_mappings
    op.create_index(
        "ix_user_integration_mapping_email_type",
        "user_integration_mappings",
        ["user_email", "integration_type"],
    )
    op.create_index(
        "ix_user_integration_mappings_user_email",
        "user_integration_mappings",
        ["user_email"],
    )
    op.create_index(
        "ix_user_integration_mapping_user_id",
        "user_integration_mappings",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_integration_mapping_user_type",
        "user_integration_mappings",
        ["user_id", "integration_type"],
        unique=False,
    )
    op.create_index(
        "ix_user_integration_mapping_integration",
        "user_integration_mappings",
        ["integration_user_id", "integration_type"],
        unique=False,
    )

    # Create unique constraints for user_integration_mappings
    op.create_unique_constraint(
        "uq_user_integration_mapping",
        "user_integration_mappings",
        ["user_id", "integration_type"],
    )
    op.create_unique_constraint(
        "uq_integration_user_id_type",
        "user_integration_mappings",
        ["integration_user_id", "integration_type"],
    )

    # Create pg_advisory_lock_held function
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pg_advisory_lock_held(key BIGINT)
        RETURNS BOOLEAN
        LANGUAGE plpgsql
        AS $$
        DECLARE
            lock_count INTEGER;
        BEGIN
            -- Check if the current session holds the advisory lock
            -- For single-argument pg_try_advisory_lock(bigint), objid matches the key
            SELECT COUNT(*)
            INTO lock_count
            FROM pg_locks
            WHERE locktype = 'advisory'
              AND objid = key::BIGINT
              AND pid = pg_backend_pid()
              AND granted = TRUE;

            RETURN lock_count > 0;
        END;
        $$;
    """
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop function
    op.execute("DROP FUNCTION IF EXISTS pg_advisory_lock_held(BIGINT);")

    # Drop tables in reverse order
    op.drop_table("user_integration_mappings")
    op.drop_table("integration_default_configs")
    op.drop_table("processed_events")
    op.drop_table("delivery_logs")
    op.drop_table("integration_credentials")
    op.drop_table("user_integration_configs")
    op.drop_table("request_logs")
    op.drop_table("request_sessions")
    op.drop_table("users")

    # Drop enums using raw SQL
    connection = op.get_bind()

    for enum_name in ["deliverystatus", "sessionstatus", "integrationtype"]:
        result = connection.execute(
            sa.text(f"SELECT 1 FROM pg_type WHERE typname = '{enum_name}'")
        )
        if result.fetchone():
            connection.execute(sa.text(f"DROP TYPE {enum_name}"))
