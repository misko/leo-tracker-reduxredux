"""double bounded adaptive tracking heavy capacity.

Revision ID: d6e9f2a3b4c5
Revises: c5f8a1d2e3b4
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d6e9f2a3b4c5"
down_revision: str | Sequence[str] | None = "c5f8a1d2e3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=8 WHERE resource_class='heavy'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=4 WHERE resource_class='heavy'"
    )
