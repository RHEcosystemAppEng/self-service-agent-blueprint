"""Rename llama_stack_session_id to conversation_thread_id

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    """Rename llama_stack_session_id to conversation_thread_id."""
    # Add the new column
    op.add_column(
        "request_sessions",
        sa.Column("conversation_thread_id", sa.String(length=255), nullable=True),
    )

    # Copy data from old column to new column
    op.execute(
        """
        UPDATE request_sessions
        SET conversation_thread_id = llama_stack_session_id
        WHERE llama_stack_session_id IS NOT NULL
    """
    )

    # Drop the old column
    op.drop_column("request_sessions", "llama_stack_session_id")


def downgrade():
    """Revert conversation_thread_id back to llama_stack_session_id."""
    # Add the old column back
    op.add_column(
        "request_sessions",
        sa.Column("llama_stack_session_id", sa.String(length=255), nullable=True),
    )

    # Copy data from new column to old column
    op.execute(
        """
        UPDATE request_sessions
        SET llama_stack_session_id = conversation_thread_id
        WHERE conversation_thread_id IS NOT NULL
    """
    )

    # Drop the new column
    op.drop_column("request_sessions", "conversation_thread_id")
