"""raise bounded adaptive tracking heavy capacity.

Revision ID: c5f8a1d2e3b4
Revises: 4a8e2c7b1d43
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c5f8a1d2e3b4"
down_revision: str | Sequence[str] | None = "4a8e2c7b1d43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=4 WHERE resource_class='heavy'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=2 WHERE resource_class='heavy'"
    )
