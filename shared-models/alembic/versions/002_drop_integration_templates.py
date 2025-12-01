"""Drop integration_templates table

This migration removes the integration_templates table which was never used.
The TemplateEngine now uses only hardcoded default formatting.

Revision ID: 002
Revises: 001
Create Date: 2025-01-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop integration_templates table."""
    op.drop_table("integration_templates")


def downgrade() -> None:
    """Recreate integration_templates table if needed."""
    # Recreate the table if we need to roll back
    op.create_table(
        "integration_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("integration_type", sa.String(), nullable=False),
        sa.Column("template_name", sa.String(length=100), nullable=False),
        sa.Column("subject_template", sa.Text(), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column(
            "required_variables", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "optional_variables", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_templates")),
        sa.UniqueConstraint(
            "integration_type",
            "template_name",
            name="uq_integration_template",
        ),
    )
