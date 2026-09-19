"""double bounded adaptive tracking heavy capacity to sixteen.

Revision ID: e7a9c2d4f6b8
Revises: d6e9f2a3b4c5
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7a9c2d4f6b8"
down_revision: str | Sequence[str] | None = "d6e9f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=16 WHERE resource_class='heavy'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=8 WHERE resource_class='heavy'"
    )
