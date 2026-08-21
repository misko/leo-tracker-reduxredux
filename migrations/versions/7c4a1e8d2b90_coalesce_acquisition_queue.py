"""coalesce scheduled acquisition queue

Revision ID: 7c4a1e8d2b90
Revises: 63f8b6c1a902
Create Date: 2026-08-21 18:05:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7c4a1e8d2b90"
down_revision: str | Sequence[str] | None = "63f8b6c1a902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "WITH ranked AS ("
        "SELECT id, row_number() OVER ("
        "PARTITION BY kind ORDER BY scheduled_for DESC, id DESC"
        ") AS position "
        "FROM acquisition_operation "
        "WHERE state='pending' AND kind IN ('scheduled_recording','scanner_sweep')"
        ") "
        "UPDATE acquisition_operation AS operation SET "
        "state='cancelled', completed_at=now(), updated_at=now(), error=NULL, "
        "outcome='superseded while enabling bounded cadence queue' "
        "FROM ranked WHERE operation.id=ranked.id AND ranked.position > 1"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_acquisition_operation_one_pending_cadence_kind "
        "ON acquisition_operation (kind) "
        "WHERE state='pending' AND kind IN ('scheduled_recording','scanner_sweep')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_acquisition_operation_one_pending_cadence_kind")
