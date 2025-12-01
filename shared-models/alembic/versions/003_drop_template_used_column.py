"""Drop template_used column from delivery_logs

This migration removes the template_used column which is no longer used.
The column was always set to an empty string after IntegrationTemplate was removed.

Revision ID: 003
Revises: 002
Create Date: 2025-01-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop template_used column from delivery_logs table."""
    op.drop_column("delivery_logs", "template_used")


def downgrade() -> None:
    """Re-add template_used column if needed."""
    op.add_column(
        "delivery_logs",
        sa.Column("template_used", sa.String(length=100), nullable=True),
    )
