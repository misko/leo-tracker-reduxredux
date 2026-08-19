"""add durable scientific campaign catalog

Revision ID: c31f9d7a2e44
Revises: a8d4c2e91b70
Create Date: 2026-08-19 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c31f9d7a2e44"
down_revision: str | Sequence[str] | None = "a8d4c2e91b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scientific_campaign",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="in_progress", nullable=False),
        sa.Column("expected_stream_count", sa.SmallInteger(), server_default="40", nullable=False),
        sa.Column("capture_uri", sa.Text(), nullable=False),
        sa.Column("capture_digest", sa.String(length=71), nullable=False),
        sa.Column("scientific_uri", sa.Text(), nullable=True),
        sa.Column("scientific_digest", sa.String(length=71), nullable=True),
        sa.Column("presentation_uri", sa.Text(), nullable=True),
        sa.Column("presentation_digest", sa.String(length=71), nullable=True),
        sa.Column("result_status", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expected_stream_count = 40",
            name=op.f("ck_scientific_campaign_exact_stream_count"),
        ),
        sa.CheckConstraint(
            "result_status IS NULL OR result_status IN ('pass', 'fail', 'inconclusive')",
            name=op.f("ck_scientific_campaign_result_status_values"),
        ),
        sa.CheckConstraint(
            "(state = 'in_progress' AND sealed_at IS NULL "
            "AND scientific_uri IS NULL AND scientific_digest IS NULL "
            "AND presentation_uri IS NULL AND presentation_digest IS NULL "
            "AND result_status IS NULL) OR "
            "(state = 'sealed' AND sealed_at IS NOT NULL "
            "AND scientific_uri IS NOT NULL AND scientific_digest IS NOT NULL "
            "AND presentation_uri IS NOT NULL AND presentation_digest IS NOT NULL "
            "AND result_status IS NOT NULL)",
            name=op.f("ck_scientific_campaign_seal_coherent"),
        ),
        sa.CheckConstraint(
            "state IN ('in_progress', 'sealed')",
            name=op.f("ck_scientific_campaign_state_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scientific_campaign")),
    )
    op.create_table(
        "scientific_campaign_stream",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("stream_id", sa.String(length=128), nullable=False),
        sa.Column("analysis_run_id", sa.String(length=128), nullable=False),
        sa.Column("analysis_run_uri", sa.Text(), nullable=False),
        sa.Column("analysis_run_digest", sa.String(length=71), nullable=False),
        sa.Column("analysis_product_id", sa.BigInteger(), nullable=False),
        sa.Column("frequency_calibration_id", sa.BigInteger(), nullable=False),
        sa.Column("capture_uri", sa.Text(), nullable=False),
        sa.Column("capture_digest", sa.String(length=71), nullable=False),
        sa.Column("calibration_uri", sa.Text(), nullable=False),
        sa.Column("calibration_digest", sa.String(length=71), nullable=False),
        sa.Column("scientific_uri", sa.Text(), nullable=False),
        sa.Column("scientific_digest", sa.String(length=71), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "ordinal >= 0 AND ordinal < 40",
            name=op.f("ck_scientific_campaign_stream_ordinal_range"),
        ),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'inconclusive', 'insufficient')",
            name=op.f("ck_scientific_campaign_stream_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_product_id"],
            ["analysis_product.id"],
            name=op.f("fk_scientific_campaign_stream_analysis_product_id_analysis_product"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_run.id"],
            name=op.f("fk_scientific_campaign_stream_analysis_run_id_analysis_run"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["scientific_campaign.id"],
            name=op.f("fk_scientific_campaign_stream_campaign_id_scientific_campaign"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["frequency_calibration_id"],
            ["frequency_calibration.id"],
            name=op.f(
                "fk_scientific_campaign_stream_frequency_calibration_id_frequency_calibration"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["capture_session.id"],
            name=op.f("fk_scientific_campaign_stream_session_id_capture_session"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["stream_id"],
            ["radio_stream.id"],
            name=op.f("fk_scientific_campaign_stream_stream_id_radio_stream"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scientific_campaign_stream")),
        sa.UniqueConstraint(
            "campaign_id",
            "analysis_product_id",
            name=op.f("uq_scientific_campaign_stream_campaign_id_analysis_product_id"),
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "ordinal",
            name=op.f("uq_scientific_campaign_stream_campaign_id_ordinal"),
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "session_id",
            "stream_id",
            name=op.f("uq_scientific_campaign_stream_campaign_id_session_id_stream_id"),
        ),
    )
    for column in (
        "analysis_product_id",
        "analysis_run_id",
        "campaign_id",
        "frequency_calibration_id",
        "session_id",
        "stream_id",
    ):
        op.create_index(
            op.f(f"ix_scientific_campaign_stream_{column}"),
            "scientific_campaign_stream",
            [column],
            unique=False,
        )

    op.execute(
        """
        CREATE FUNCTION leo_scientific_campaign_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.state = 'sealed' THEN
                RAISE EXCEPTION 'sealed scientific campaign is immutable: %', OLD.id;
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER scientific_campaign_immutable
        BEFORE UPDATE OR DELETE ON scientific_campaign
        FOR EACH ROW EXECUTE FUNCTION leo_scientific_campaign_immutable()
        """
    )
    op.execute(
        """
        CREATE FUNCTION leo_scientific_campaign_stream_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE campaign_state text;
        BEGIN
            SELECT state INTO campaign_state FROM scientific_campaign
            WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.campaign_id ELSE NEW.campaign_id END;
            IF campaign_state = 'sealed' THEN
                RAISE EXCEPTION 'sealed scientific campaign members are immutable';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER scientific_campaign_stream_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON scientific_campaign_stream
        FOR EACH ROW EXECUTE FUNCTION leo_scientific_campaign_stream_immutable()
        """
    )


def downgrade() -> None:
    op.drop_table("scientific_campaign_stream")
    op.drop_table("scientific_campaign")
    op.execute("DROP FUNCTION leo_scientific_campaign_stream_immutable()")
    op.execute("DROP FUNCTION leo_scientific_campaign_immutable()")
