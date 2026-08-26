"""cap initial Standard-native heavy workers

Revision ID: 0f6a2b9c4d81
Revises: b3e91d6f4a20
Create Date: 2026-08-26 16:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0f6a2b9c4d81"
down_revision: str | Sequence[str] | None = "b3e91d6f4a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=2 WHERE resource_class='heavy'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE processing_resource_capacity SET maximum_leases=4 WHERE resource_class='heavy'"
    )
