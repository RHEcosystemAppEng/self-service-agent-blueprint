"""Convert unique constraint to partial unique constraint for sentinel values

This migration converts the uq_integration_user_id_type unique constraint
to a partial unique constraint that excludes __NOT_FOUND__ sentinel values.
This allows multiple users to have __NOT_FOUND__ entries while still
preventing duplicate real integration user IDs.

Revision ID: 002
Revises: 001
Create Date: 2024-12-04 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert unique constraint to partial unique constraint."""
    # Drop the existing unique constraint
    op.drop_constraint(
        "uq_integration_user_id_type",
        "user_integration_mappings",
        type_="unique",
    )

    # Create a partial unique constraint that excludes __NOT_FOUND__ sentinel values
    # This allows multiple users to have __NOT_FOUND__ entries while still
    # preventing duplicate real integration user IDs
    # PostgreSQL requires using a unique index for partial unique constraints
    op.execute(
        """
        CREATE UNIQUE INDEX uq_integration_user_id_type
        ON user_integration_mappings (integration_user_id, integration_type)
        WHERE integration_user_id != '__NOT_FOUND__';
        """
    )


def downgrade() -> None:
    """Revert to regular unique constraint."""
    # Drop the partial unique index
    op.drop_index(
        "uq_integration_user_id_type",
        "user_integration_mappings",
    )

    # Recreate the original unique constraint (without WHERE clause)
    op.create_unique_constraint(
        "uq_integration_user_id_type",
        "user_integration_mappings",
        ["integration_user_id", "integration_type"],
    )
