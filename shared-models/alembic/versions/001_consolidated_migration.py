"""Consolidated migration with all tables and schema changes

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
    # Using uppercase values as per migration 002
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
                "TEST",  # Added in migration 005
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

    # Create request_sessions table with all fields from migrations 001 and 003
    try:
        op.create_table(
            "request_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("integration_type", integration_type_enum, nullable=False),
            sa.Column("status", session_status_enum, nullable=False),
            sa.Column("channel_id", sa.String(length=255), nullable=True),
            sa.Column("thread_id", sa.String(length=255), nullable=True),
            sa.Column("integration_metadata", sa.JSON(), nullable=True),
            sa.Column("total_requests", sa.Integer(), nullable=False),
            sa.Column(
                "last_request_at", postgresql.TIMESTAMP(timezone=True), nullable=True
            ),  # Timezone-aware from migration 004
            sa.Column(
                "expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True
            ),  # Timezone-aware from migration 004
            sa.Column(
                "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False
            ),  # Timezone-aware from migration 004
            sa.Column(
                "updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False
            ),  # Timezone-aware from migration 004
            # Additional fields from migration 003
            sa.Column("external_session_id", sa.String(length=255), nullable=True),
            sa.Column("current_agent_id", sa.String(length=255), nullable=True),
            sa.Column("llama_stack_session_id", sa.String(length=255), nullable=True),
            sa.Column("user_context", sa.JSON(), nullable=True),
            sa.Column("conversation_context", sa.JSON(), nullable=True),
            sa.Column("last_request_id", sa.String(length=36), nullable=True),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_request_sessions")),
            sa.UniqueConstraint(
                "session_id", name=op.f("uq_request_sessions_session_id")
            ),
        )
        op.create_index(
            op.f("ix_session_id"), "request_sessions", ["session_id"], unique=False
        )
        op.create_index(
            op.f("ix_user_id"), "request_sessions", ["user_id"], unique=False
        )

    except Exception:
        import traceback

        traceback.print_exc()
        raise

    # Create request_logs table with timezone-aware timestamps
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
        sa.Column(
            "completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),  # Timezone-aware from migration 004
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False
        ),  # Timezone-aware from migration 004
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False
        ),  # Timezone-aware from migration 004
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["request_sessions.session_id"],
            name=op.f("fk_request_logs_session_id_request_sessions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_logs")),
        sa.UniqueConstraint("request_id", name=op.f("uq_request_logs_request_id")),
    )
    op.create_index(op.f("ix_request_id"), "request_logs", ["request_id"], unique=False)

    # Add a small delay and explicit commit attempt to see if it helps
    import time

    time.sleep(0.1)

    # Create user_integration_configs table with timezone-aware timestamps
    try:
        op.create_table(
            "user_integration_configs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("integration_type", integration_type_enum, nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("retry_count", sa.Integer(), nullable=False),
            sa.Column("retry_delay_seconds", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column(
                "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False
            ),  # Timezone-aware from migration 004
            sa.Column(
                "updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False
            ),  # Timezone-aware from migration 004
            sa.PrimaryKeyConstraint("id", name=op.f("pk_user_integration_configs")),
            sa.UniqueConstraint(
                "user_id", "integration_type", name="uq_user_integration"
            ),
        )
        op.create_index(
            "ix_user_integration_configs_user_id",
            "user_integration_configs",
            ["user_id"],
            unique=False,
        )
    except Exception:
        import traceback

        traceback.print_exc()
        raise

    # Create integration_templates table with timezone-aware timestamps
    op.create_table(
        "integration_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("integration_type", integration_type_enum, nullable=False),
        sa.Column("template_name", sa.String(length=100), nullable=False),
        sa.Column("subject_template", sa.Text(), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("required_variables", sa.JSON(), nullable=True),
        sa.Column("optional_variables", sa.JSON(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False
        ),  # Timezone-aware from migration 004
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False
        ),  # Timezone-aware from migration 004
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_templates")),
        sa.UniqueConstraint(
            "integration_type", "template_name", name="uq_integration_template"
        ),
    )

    # Create integration_credentials table with timezone-aware timestamps
    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("integration_type", integration_type_enum, nullable=False),
        sa.Column("credential_name", sa.String(length=100), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False
        ),  # Timezone-aware from migration 004
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False
        ),  # Timezone-aware from migration 004
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_credentials")),
        sa.UniqueConstraint(
            "integration_type", "credential_name", name="uq_integration_credential"
        ),
    )

    # Create delivery_logs table with timezone-aware timestamps and CASCADE DELETE (from migration 006)
    op.create_table(
        "delivery_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("integration_config_id", sa.Integer(), nullable=False),
        sa.Column("integration_type", integration_type_enum, nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("template_used", sa.String(length=100), nullable=True),
        sa.Column("status", delivery_status_enum, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "first_attempt_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),  # Timezone-aware from migration 004
        sa.Column(
            "last_attempt_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),  # Timezone-aware from migration 004
        sa.Column(
            "delivered_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),  # Timezone-aware from migration 004
        sa.Column(
            "expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),  # Timezone-aware from migration 004
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.Column("integration_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False
        ),  # Timezone-aware from migration 004
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False
        ),  # Timezone-aware from migration 004
        sa.ForeignKeyConstraint(
            ["integration_config_id"],
            ["user_integration_configs.id"],
            name=op.f(
                "fk_delivery_logs_integration_config_id_user_integration_configs"
            ),
            ondelete="CASCADE",  # CASCADE DELETE from migration 006
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

    # Create processed_events table from migration 007
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

    # Create integration_default_configs table (from migration 002)
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


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop tables in reverse order
    op.drop_table("integration_default_configs")
    op.drop_table("processed_events")
    op.drop_table("delivery_logs")
    op.drop_table("integration_credentials")
    op.drop_table("integration_templates")
    op.drop_table("user_integration_configs")
    op.drop_table("request_logs")
    op.drop_table("request_sessions")

    # Drop enums using raw SQL
    connection = op.get_bind()

    for enum_name in ["deliverystatus", "sessionstatus", "integrationtype"]:
        result = connection.execute(
            sa.text(f"SELECT 1 FROM pg_type WHERE typname = '{enum_name}'")
        )
        if result.fetchone():
            connection.execute(sa.text(f"DROP TYPE {enum_name}"))
