"""add atomic processing cutover fence evidence

Revision ID: 9b7e31a4c2d8
Revises: e28b7a4c1d90
Create Date: 2026-08-20 23:55:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9b7e31a4c2d8"
down_revision: str | Sequence[str] | None = "e28b7a4c1d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE processing_fence_event ("
        "operation_id VARCHAR(128) NOT NULL, "
        "pipeline_release_id VARCHAR(128) NOT NULL, "
        "operator_id VARCHAR(128) NOT NULL, "
        "reason TEXT NOT NULL, "
        "run_ids VARCHAR(128)[] NOT NULL, "
        "cancelled_run_count INTEGER NOT NULL, "
        "cancelled_job_count INTEGER NOT NULL, "
        "expired_attempt_count INTEGER NOT NULL, "
        "preserved_succeeded_job_count INTEGER NOT NULL, "
        "preserved_product_count INTEGER NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "CONSTRAINT pk_processing_fence_event PRIMARY KEY (operation_id), "
        "CONSTRAINT fk_processing_fence_event_pipeline_release_id_pipeline_release "
        "FOREIGN KEY (pipeline_release_id) REFERENCES pipeline_release(id) ON DELETE RESTRICT)"
    )
    op.execute(
        "CREATE INDEX ix_processing_fence_event_pipeline_release_id "
        "ON processing_fence_event (pipeline_release_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE processing_fence_event")
