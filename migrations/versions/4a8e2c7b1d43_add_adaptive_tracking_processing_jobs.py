"""add adaptive tracking jobs to the shared processing queue.

Revision ID: 4a8e2c7b1d43
Revises: 3e7b8cd9a102
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a8e2c7b1d43"
down_revision: str | Sequence[str] | None = "3e7b8cd9a102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_processing_job_adaptive_binding", table_name="processing_job")
    op.drop_constraint("job_family_binding", "processing_job", type_="check")
    op.create_check_constraint(
        "job_family_binding",
        "processing_job",
        "(job_kind = 'pipeline_stage' AND run_id IS NOT NULL AND adaptive_session_id IS NULL) "
        "OR (job_kind IN ('adaptive_scan', 'adaptive_tracking') AND run_id IS NULL "
        "AND adaptive_session_id IS NOT NULL AND adaptive_input_manifest_digest IS NOT NULL "
        "AND adaptive_configuration_digest IS NOT NULL)",
    )
    op.create_index(
        "uq_processing_job_adaptive_binding",
        "processing_job",
        [
            "adaptive_session_id",
            "adaptive_input_manifest_digest",
            "adaptive_configuration_digest",
            "stage_key",
        ],
        unique=True,
        postgresql_where=sa.text("job_kind IN ('adaptive_scan', 'adaptive_tracking')"),
    )


def downgrade() -> None:
    op.drop_index("uq_processing_job_adaptive_binding", table_name="processing_job")
    op.drop_constraint("job_family_binding", "processing_job", type_="check")
    op.create_check_constraint(
        "job_family_binding",
        "processing_job",
        "(job_kind = 'pipeline_stage' AND run_id IS NOT NULL AND adaptive_session_id IS NULL) "
        "OR (job_kind = 'adaptive_scan' AND run_id IS NULL AND adaptive_session_id IS NOT NULL "
        "AND adaptive_input_manifest_digest IS NOT NULL "
        "AND adaptive_configuration_digest IS NOT NULL)",
    )
    op.create_index(
        "uq_processing_job_adaptive_binding",
        "processing_job",
        [
            "adaptive_session_id",
            "adaptive_input_manifest_digest",
            "adaptive_configuration_digest",
            "stage_key",
        ],
        unique=True,
        postgresql_where=sa.text("job_kind = 'adaptive_scan'"),
    )
