"""raise reviewed heavy capacity for the 3-by-8 worker profile

Revision ID: 4e8c1b7a2d90
Revises: 0f6a2b9c4d81
Create Date: 2026-08-30 01:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "4e8c1b7a2d90"
down_revision: str | Sequence[str] | None = "0f6a2b9c4d81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=3 WHERE resource_class='heavy'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=2 WHERE resource_class='heavy'"
    )
