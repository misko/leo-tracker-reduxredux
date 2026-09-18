"""add adaptive scanner jobs to the shared processing queue.

Revision ID: 3e7b8cd9a102
Revises: 0f6a2b9c4d81
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e7b8cd9a102"
down_revision: str | Sequence[str] | None = "0f6a2b9c4d81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("processing_job", "run_id", existing_type=sa.String(128), nullable=True)
    op.add_column(
        "processing_job",
        sa.Column("job_kind", sa.String(32), nullable=False, server_default="pipeline_stage"),
    )
    op.add_column("processing_job", sa.Column("adaptive_session_id", sa.String(128)))
    op.add_column("processing_job", sa.Column("adaptive_input_manifest_digest", sa.String(71)))
    op.add_column("processing_job", sa.Column("adaptive_configuration_digest", sa.String(71)))
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


def downgrade() -> None:
    op.drop_index("uq_processing_job_adaptive_binding", table_name="processing_job")
    op.drop_constraint("job_family_binding", "processing_job", type_="check")
    op.drop_column("processing_job", "adaptive_configuration_digest")
    op.drop_column("processing_job", "adaptive_input_manifest_digest")
    op.drop_column("processing_job", "adaptive_session_id")
    op.drop_column("processing_job", "job_kind")
    op.alter_column("processing_job", "run_id", existing_type=sa.String(128), nullable=False)
