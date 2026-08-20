"""raise processing worker capacity

Revision ID: d17c4a8b9e20
Revises: c96f1a42e7d3
Create Date: 2026-08-20 03:50:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d17c4a8b9e20"
down_revision: str | Sequence[str] | None = "c96f1a42e7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=20 "
        "WHERE resource_class IN ('streaming', 'cpu', 'memory', 'heavy')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases = CASE resource_class "
        "WHEN 'streaming' THEN 16 WHEN 'cpu' THEN 8 "
        "WHEN 'memory' THEN 4 WHEN 'heavy' THEN 4 END "
        "WHERE resource_class IN ('streaming', 'cpu', 'memory', 'heavy')"
    )
