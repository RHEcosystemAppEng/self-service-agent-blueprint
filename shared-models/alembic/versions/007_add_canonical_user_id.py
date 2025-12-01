"""Add canonical user_id architecture

This migration introduces a canonical User table with UUID-based user_id that all
integrations reference. This ensures consistent user identity across all integrations
and enables session continuity.

Revision ID: 007
Revises: 006
Create Date: 2025-11-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add canonical User table and update all user_id references."""

    # Step 1: Create users table
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

    # Step 2: Add user_id column to user_integration_mappings (nullable initially for migration)
    op.add_column(
        "user_integration_mappings",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=True),
    )

    # Step 3: Migrate existing data - create User records and link mappings
    # Group mappings by email to create one User per email
    op.execute(
        """
        INSERT INTO users (user_id, primary_email, created_at, updated_at)
        SELECT DISTINCT
            gen_random_uuid() as user_id,
            user_email as primary_email,
            MIN(created_at) as created_at,
            MAX(updated_at) as updated_at
        FROM user_integration_mappings
        GROUP BY user_email
    """
    )

    # Link mappings to users
    op.execute(
        """
        UPDATE user_integration_mappings uim
        SET user_id = u.user_id
        FROM users u
        WHERE uim.user_email = u.primary_email
    """
    )

    # Step 4: Make user_id non-nullable and add foreign key
    op.alter_column("user_integration_mappings", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_user_integration_mappings_user_id",
        "user_integration_mappings",
        "users",
        ["user_id"],
        ["user_id"],
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

    # Update unique constraint to use user_id instead of user_email
    op.drop_constraint(
        "uq_user_integration_mapping", "user_integration_mappings", type_="unique"
    )
    op.create_unique_constraint(
        "uq_user_integration_mapping",
        "user_integration_mappings",
        ["user_id", "integration_type"],
    )
    # Add unique constraint on integration_user_id + integration_type to prevent conflicts
    # This ensures the same Slack user ID (or other integration ID) can only map to one canonical user
    op.create_unique_constraint(
        "uq_integration_user_id_type",
        "user_integration_mappings",
        ["integration_user_id", "integration_type"],
    )

    # Step 5: Add user_id column to request_sessions (nullable initially)
    op.add_column(
        "request_sessions",
        sa.Column("canonical_user_id", postgresql.UUID(as_uuid=False), nullable=True),
    )

    # Migrate existing sessions - resolve user_id from email via mappings
    op.execute(
        """
        UPDATE request_sessions rs
        SET canonical_user_id = (
            SELECT uim.user_id
            FROM user_integration_mappings uim
            WHERE uim.user_email = rs.user_id
            AND uim.integration_type = rs.integration_type
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM user_integration_mappings uim
            WHERE uim.user_email = rs.user_id
            AND uim.integration_type = rs.integration_type
        )
    """
    )

    # For sessions without matching mappings, create User and link
    op.execute(
        """
        INSERT INTO users (user_id, primary_email, created_at, updated_at)
        SELECT DISTINCT
            gen_random_uuid() as user_id,
            rs.user_id as primary_email,
            MIN(rs.created_at) as created_at,
            MAX(rs.updated_at) as updated_at
        FROM request_sessions rs
        WHERE rs.canonical_user_id IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM users u WHERE u.primary_email = rs.user_id
        )
        GROUP BY rs.user_id
    """
    )

    op.execute(
        """
        UPDATE request_sessions rs
        SET canonical_user_id = u.user_id
        FROM users u
        WHERE rs.canonical_user_id IS NULL
        AND rs.user_id = u.primary_email
    """
    )

    # Make canonical_user_id non-nullable and add foreign key
    op.alter_column("request_sessions", "canonical_user_id", nullable=False)
    op.create_foreign_key(
        "fk_request_sessions_user_id",
        "request_sessions",
        "users",
        ["canonical_user_id"],
        ["user_id"],
    )
    op.create_index(
        "ix_request_sessions_canonical_user_id",
        "request_sessions",
        ["canonical_user_id"],
        unique=False,
    )

    # Drop old user_id column (after ensuring canonical_user_id is populated)
    # Try to drop the index if it exists (it might have a different name from op.f())
    op.execute(
        """
        DROP INDEX IF EXISTS ix_request_sessions_user_id;
        DROP INDEX IF EXISTS ix_user_id;
        """
    )
    op.drop_column("request_sessions", "user_id")
    # Rename canonical_user_id to user_id using raw SQL
    op.execute(
        "ALTER TABLE request_sessions RENAME COLUMN canonical_user_id TO user_id"
    )
    op.create_index("ix_request_sessions_user_id", "request_sessions", ["user_id"])

    # Step 6: Update user_integration_configs
    op.add_column(
        "user_integration_configs",
        sa.Column("canonical_user_id", postgresql.UUID(as_uuid=False), nullable=True),
    )

    # Migrate existing configs
    op.execute(
        """
        UPDATE user_integration_configs uic
        SET canonical_user_id = uim.user_id
        FROM user_integration_mappings uim
        WHERE uic.user_id = uim.user_email
        AND uic.integration_type = uim.integration_type
    """
    )

    # For configs without matching mappings, create User and link
    op.execute(
        """
        INSERT INTO users (user_id, primary_email, created_at, updated_at)
        SELECT DISTINCT
            gen_random_uuid() as user_id,
            uic.user_id as primary_email,
            MIN(uic.created_at) as created_at,
            MAX(uic.updated_at) as updated_at
        FROM user_integration_configs uic
        WHERE uic.canonical_user_id IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM users u WHERE u.primary_email = uic.user_id
        )
        GROUP BY uic.user_id
    """
    )

    op.execute(
        """
        UPDATE user_integration_configs uic
        SET canonical_user_id = u.user_id
        FROM users u
        WHERE uic.canonical_user_id IS NULL
        AND uic.user_id = u.primary_email
    """
    )

    op.alter_column("user_integration_configs", "canonical_user_id", nullable=False)
    op.create_foreign_key(
        "fk_user_integration_configs_user_id",
        "user_integration_configs",
        "users",
        ["canonical_user_id"],
        ["user_id"],
    )
    # Drop old index if it exists (might have different name from op.f())
    op.execute(
        """
        DROP INDEX IF EXISTS ix_user_integration_configs_user_id;
        DROP INDEX IF EXISTS ix_user_id;
        """
    )
    op.drop_column("user_integration_configs", "user_id")
    # Rename canonical_user_id to user_id using raw SQL
    op.execute(
        "ALTER TABLE user_integration_configs RENAME COLUMN canonical_user_id TO user_id"
    )
    op.create_index(
        "ix_user_integration_configs_user_id", "user_integration_configs", ["user_id"]
    )

    # Step 7: Update delivery_logs
    op.add_column(
        "delivery_logs",
        sa.Column("canonical_user_id", postgresql.UUID(as_uuid=False), nullable=True),
    )

    # Migrate existing delivery logs
    op.execute(
        """
        UPDATE delivery_logs dl
        SET canonical_user_id = rs.user_id
        FROM request_sessions rs
        WHERE dl.session_id = rs.session_id
    """
    )

    # For logs without matching sessions, try to resolve from user_id (old email-based)
    op.execute(
        """
        UPDATE delivery_logs dl
        SET canonical_user_id = (
            SELECT uim.user_id
            FROM user_integration_mappings uim
            WHERE uim.user_email = dl.user_id
            LIMIT 1
        )
        WHERE dl.canonical_user_id IS NULL
        AND EXISTS (
            SELECT 1
            FROM user_integration_mappings uim
            WHERE uim.user_email = dl.user_id
        )
    """
    )

    op.alter_column("delivery_logs", "canonical_user_id", nullable=False)
    op.create_foreign_key(
        "fk_delivery_logs_user_id",
        "delivery_logs",
        "users",
        ["canonical_user_id"],
        ["user_id"],
    )
    # Drop old index if it exists (might have different name from op.f())
    op.execute(
        """
        DROP INDEX IF EXISTS ix_delivery_logs_user_id;
        DROP INDEX IF EXISTS ix_user_id;
        """
    )
    op.drop_column("delivery_logs", "user_id")
    # Rename canonical_user_id to user_id using raw SQL
    op.execute("ALTER TABLE delivery_logs RENAME COLUMN canonical_user_id TO user_id")
    op.create_index("ix_delivery_logs_user_id", "delivery_logs", ["user_id"])


def downgrade() -> None:
    """Revert to email-based user_id."""

    # This is a complex downgrade - we'll need to extract email from User.primary_email
    # or from user_integration_mappings

    # For delivery_logs
    op.add_column(
        "delivery_logs",
        sa.Column("email_user_id", sa.String(length=255), nullable=True),
    )
    op.execute(
        """
        UPDATE delivery_logs dl
        SET email_user_id = u.primary_email
        FROM users u
        WHERE dl.user_id = u.user_id
    """
    )
    op.alter_column("delivery_logs", "email_user_id", nullable=False)
    op.drop_constraint("fk_delivery_logs_user_id", "delivery_logs", type_="foreignkey")
    op.drop_index("ix_delivery_logs_user_id", table_name="delivery_logs")
    op.drop_column("delivery_logs", "user_id")
    # Rename email_user_id to user_id using raw SQL
    op.execute("ALTER TABLE delivery_logs RENAME COLUMN email_user_id TO user_id")
    op.create_index("ix_delivery_logs_user_id", "delivery_logs", ["user_id"])

    # For user_integration_configs
    op.add_column(
        "user_integration_configs",
        sa.Column("email_user_id", sa.String(length=255), nullable=True),
    )
    op.execute(
        """
        UPDATE user_integration_configs uic
        SET email_user_id = u.primary_email
        FROM users u
        WHERE uic.user_id = u.user_id
    """
    )
    op.alter_column("user_integration_configs", "email_user_id", nullable=False)
    op.drop_constraint(
        "fk_user_integration_configs_user_id",
        "user_integration_configs",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_user_integration_configs_user_id", table_name="user_integration_configs"
    )
    op.drop_column("user_integration_configs", "user_id")
    # Rename email_user_id to user_id using raw SQL
    op.execute(
        "ALTER TABLE user_integration_configs RENAME COLUMN email_user_id TO user_id"
    )
    op.create_index(
        "ix_user_integration_configs_user_id", "user_integration_configs", ["user_id"]
    )

    # For request_sessions
    op.add_column(
        "request_sessions",
        sa.Column("email_user_id", sa.String(length=255), nullable=True),
    )
    op.execute(
        """
        UPDATE request_sessions rs
        SET email_user_id = u.primary_email
        FROM users u
        WHERE rs.user_id = u.user_id
    """
    )
    op.alter_column("request_sessions", "email_user_id", nullable=False)
    op.drop_constraint(
        "fk_request_sessions_user_id", "request_sessions", type_="foreignkey"
    )
    op.drop_index("ix_request_sessions_user_id", table_name="request_sessions")
    op.drop_column("request_sessions", "user_id")
    # Rename email_user_id to user_id using raw SQL
    op.execute("ALTER TABLE request_sessions RENAME COLUMN email_user_id TO user_id")
    op.create_index("ix_request_sessions_user_id", "request_sessions", ["user_id"])

    # For user_integration_mappings
    op.drop_constraint(
        "uq_integration_user_id_type", "user_integration_mappings", type_="unique"
    )
    op.drop_constraint(
        "uq_user_integration_mapping", "user_integration_mappings", type_="unique"
    )
    op.drop_index(
        "ix_user_integration_mapping_user_id", table_name="user_integration_mappings"
    )
    op.drop_index(
        "ix_user_integration_mapping_user_type", table_name="user_integration_mappings"
    )
    op.drop_index(
        "ix_user_integration_mapping_integration",
        table_name="user_integration_mappings",
    )
    op.drop_constraint(
        "fk_user_integration_mappings_user_id",
        "user_integration_mappings",
        type_="foreignkey",
    )
    op.drop_column("user_integration_mappings", "user_id")
    op.create_unique_constraint(
        "uq_user_integration_mapping",
        "user_integration_mappings",
        ["user_email", "integration_type"],
    )

    # Drop users table
    op.drop_table("users")
