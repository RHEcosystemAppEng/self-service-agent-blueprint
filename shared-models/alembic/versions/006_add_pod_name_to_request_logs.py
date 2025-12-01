"""Add pod_name to request_logs

This migration adds a pod_name column to the request_logs table to track which pod
initiated each request. This enables efficient per-pod polling for responses in
scaled deployments.

Revision ID: 006
Revises: 005
Create Date: 2025-01-XX 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pod_name column to request_logs table."""
    op.add_column(
        "request_logs",
        sa.Column("pod_name", sa.String(255), nullable=True),
    )
    # Create index for efficient queries
    op.create_index(
        "ix_request_logs_pod_name",
        "request_logs",
        ["pod_name"],
    )


def downgrade() -> None:
    """Remove pod_name column from request_logs table."""
    op.drop_index("ix_request_logs_pod_name", table_name="request_logs")
    op.drop_column("request_logs", "pod_name")
