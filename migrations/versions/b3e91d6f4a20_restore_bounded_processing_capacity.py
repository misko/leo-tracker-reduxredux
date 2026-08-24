"""restore bounded processing resource capacity

Revision ID: b3e91d6f4a20
Revises: 7c4a1e8d2b90
Create Date: 2026-08-24 22:45:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3e91d6f4a20"
down_revision: str | Sequence[str] | None = "7c4a1e8d2b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases = CASE resource_class "
        "WHEN 'streaming' THEN 16 WHEN 'cpu' THEN 8 "
        "WHEN 'memory' THEN 4 WHEN 'heavy' THEN 4 END "
        "WHERE resource_class IN ('streaming', 'cpu', 'memory', 'heavy')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=20 "
        "WHERE resource_class IN ('streaming', 'cpu', 'memory', 'heavy')"
    )
