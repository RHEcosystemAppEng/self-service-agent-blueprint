"""Add token tracking fields to request_sessions

This migration adds token usage tracking fields to the request_sessions table
to enable persistent token counting across request manager restarts and
support for multiple request manager instances.

Revision ID: 004
Revises: 003
Create Date: 2025-01-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add token tracking columns to request_sessions table."""
    op.add_column(
        "request_sessions",
        sa.Column(
            "total_input_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "request_sessions",
        sa.Column(
            "total_output_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "request_sessions",
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "request_sessions",
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "request_sessions",
        sa.Column(
            "max_input_tokens_per_call",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "request_sessions",
        sa.Column(
            "max_output_tokens_per_call",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "request_sessions",
        sa.Column(
            "max_total_tokens_per_call",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Remove token tracking columns from request_sessions table."""
    op.drop_column("request_sessions", "max_total_tokens_per_call")
    op.drop_column("request_sessions", "max_output_tokens_per_call")
    op.drop_column("request_sessions", "max_input_tokens_per_call")
    op.drop_column("request_sessions", "llm_call_count")
    op.drop_column("request_sessions", "total_tokens")
    op.drop_column("request_sessions", "total_output_tokens")
    op.drop_column("request_sessions", "total_input_tokens")
