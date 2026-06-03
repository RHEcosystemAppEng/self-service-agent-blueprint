"""Zammad ticketing: enum value, ticket-scoped sessions, customer anchor table.

Revision ID: 002
Revises: 001

Consolidates former incremental revisions (ZAMMAD enum; partial unique index + wide
session_id; zammad_ticket_customer_anchors table).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) IntegrationType: ZAMMAD (PostgreSQL enum add; idempotent)
    # PostgreSQL forbids using a newly added enum literal in the same transaction as ADD VALUE
    # ("unsafe use of new value"). Commit the enum change before index DDL below.
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = 'integrationtype' AND e.enumlabel = 'ZAMMAD'
                ) THEN
                    ALTER TYPE integrationtype ADD VALUE 'ZAMMAD';
                END IF;
            END $$;
            """
        )

    # 2) Multiple active ZAMMAD sessions per user (interim); 003 replaces index with
    #    snapshot session_scope <> PER_TICKET. Widen session_id for ticket-scoped ids.
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

    op.alter_column(
        "request_sessions",
        "session_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "request_logs",
        "session_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "delivery_logs",
        "session_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    # 3) Anchor first-seen customer email per Zammad ticket
    op.create_table(
        "zammad_ticket_customer_anchors",
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("zammad_customer_id", sa.BigInteger(), nullable=True),
        sa.Column("email_normalized", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("ticket_id"),
    )


def downgrade() -> None:
    op.drop_table("zammad_ticket_customer_anchors")

    op.execute("DROP INDEX IF EXISTS idx_one_active_session_per_user_integration")
    op.execute(
        """
        CREATE UNIQUE INDEX idx_one_active_session_per_user_integration
        ON request_sessions (user_id, integration_type)
        WHERE status = 'ACTIVE'
        """
    )

    op.alter_column(
        "delivery_logs",
        "session_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
    op.alter_column(
        "request_logs",
        "session_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
    op.alter_column(
        "request_sessions",
        "session_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=36),
        existing_nullable=False,
    )

    # Enum: PostgreSQL cannot drop enum values safely if in use — no-op
    pass
