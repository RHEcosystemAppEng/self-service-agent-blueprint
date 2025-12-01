"""Add pg_advisory_lock_held function

This migration adds a PostgreSQL function to check if an advisory lock is held.
This is useful for leader election patterns where we need to verify lock ownership.

Revision ID: 005
Revises: 004
Create Date: 2025-11-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pg_advisory_lock_held function."""
    # Create function to check if an advisory lock is held by the current session
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
    """Remove pg_advisory_lock_held function."""
    op.execute("DROP FUNCTION IF EXISTS pg_advisory_lock_held(BIGINT);")
