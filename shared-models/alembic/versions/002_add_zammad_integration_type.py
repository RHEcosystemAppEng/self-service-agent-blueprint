"""Add ZAMMAD to IntegrationType enum

Revision ID: 002
Revises: 001
Create Date: 2025-03-13 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ZAMMAD value to integrationtype enum."""
    # PostgreSQL: Add new enum value; safe if already exists (idempotent via DO block)
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


def downgrade() -> None:
    """Remove ZAMMAD from integrationtype enum.

    Note: PostgreSQL does not support removing enum values easily when they may be in use.
    This migration's downgrade is a no-op; a full downgrade would require data migration.
    """
    pass
