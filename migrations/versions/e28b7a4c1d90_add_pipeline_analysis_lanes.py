"""add independent Standard and Research analysis lanes

Revision ID: e28b7a4c1d90
Revises: d17c4a8b9e20
Create Date: 2026-08-20 18:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e28b7a4c1d90"
down_revision: str | Sequence[str] | None = "d17c4a8b9e20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE analysis_run ADD COLUMN pipeline_lane VARCHAR(16) NOT NULL DEFAULT 'standard'"
    )
    op.execute(
        "ALTER TABLE analysis_run ADD CONSTRAINT ck_analysis_run_pipeline_lane_values "
        "CHECK (pipeline_lane IN ('standard', 'research'))"
    )
    op.execute("DROP INDEX uq_analysis_run_active_session")
    op.execute(
        "CREATE UNIQUE INDEX uq_analysis_run_active_session_lane "
        "ON analysis_run (session_id, pipeline_lane) "
        "WHERE state IN ('pending', 'running')"
    )
    op.execute(
        "CREATE TABLE current_pipeline_analysis ("
        "session_id VARCHAR(128) NOT NULL, "
        "pipeline_lane VARCHAR(16) NOT NULL, "
        "run_id VARCHAR(128) NOT NULL, "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "CONSTRAINT pk_current_pipeline_analysis PRIMARY KEY (session_id, pipeline_lane), "
        "CONSTRAINT ck_current_pipeline_analysis_pipeline_lane_values "
        "CHECK (pipeline_lane IN ('standard', 'research')), "
        "CONSTRAINT uq_current_pipeline_analysis_run_id UNIQUE (run_id), "
        "CONSTRAINT fk_current_pipeline_analysis_session_id_capture_session "
        "FOREIGN KEY (session_id) REFERENCES capture_session(id) ON DELETE CASCADE, "
        "CONSTRAINT fk_current_pipeline_analysis_run_id_analysis_run "
        "FOREIGN KEY (run_id) REFERENCES analysis_run(id) ON DELETE RESTRICT)"
    )
    op.execute(
        "INSERT INTO current_pipeline_analysis "
        "(session_id, pipeline_lane, run_id, updated_at) "
        "SELECT session_id, 'standard', run_id, updated_at FROM current_analysis"
    )


def downgrade() -> None:
    connection = op.get_bind()
    research_count = connection.exec_driver_sql(
        "SELECT count(*) FROM analysis_run WHERE pipeline_lane <> 'standard'"
    ).scalar_one()
    if research_count:
        raise RuntimeError("cannot downgrade while Research analysis runs exist")
    op.execute("DROP TABLE current_pipeline_analysis")
    op.execute("DROP INDEX uq_analysis_run_active_session_lane")
    op.execute(
        "CREATE UNIQUE INDEX uq_analysis_run_active_session "
        "ON analysis_run (session_id) WHERE state IN ('pending', 'running')"
    )
    op.execute("ALTER TABLE analysis_run DROP CONSTRAINT ck_analysis_run_pipeline_lane_values")
    op.execute("ALTER TABLE analysis_run DROP COLUMN pipeline_lane")
