"""add typed scopes, integrity prerequisites, release authority and derivations

Revision ID: d52a7f24c8e1
Revises: b91e2c4d7a10
Create Date: 2026-08-19 23:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d52a7f24c8e1"
down_revision: str | Sequence[str] | None = "b91e2c4d7a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ZERO_DIGEST = "sha256:" + "0" * 64


def upgrade() -> None:
    op.add_column(
        "pipeline_release",
        sa.Column(
            "configuration_digest", sa.String(71), nullable=False, server_default=ZERO_DIGEST
        ),
    )
    op.add_column(
        "pipeline_release",
        sa.Column("executable_digest", sa.String(71), nullable=False, server_default=ZERO_DIGEST),
    )

    op.create_table(
        "analysis_scope",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("canonical_digest", sa.String(71), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("stream_id", sa.String(128)),
        sa.Column("radio_id", sa.String(128)),
        sa.Column("receiver_id", sa.SmallInteger()),
        sa.Column("synchronization_inventory_digest", sa.String(71)),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('receiver_path', 'radio', 'paired')",
            name=op.f("ck_analysis_scope_kind_values"),
        ),
        sa.CheckConstraint(
            "(kind = 'receiver_path' AND stream_id IS NOT NULL AND receiver_id IS NOT NULL "
            "AND radio_id IS NULL AND synchronization_inventory_digest IS NULL) OR "
            "(kind = 'radio' AND stream_id IS NOT NULL AND receiver_id IS NULL "
            "AND radio_id IS NOT NULL AND synchronization_inventory_digest IS NULL) OR "
            "(kind = 'paired' AND stream_id IS NULL AND receiver_id IS NULL "
            "AND radio_id IS NULL AND synchronization_inventory_digest IS NOT NULL)",
            name=op.f("ck_analysis_scope_typed_shape"),
        ),
        sa.ForeignKeyConstraint(
            ("session_id",),
            ("capture_session.id",),
            ondelete="RESTRICT",
            name=op.f("fk_analysis_scope_session_id_capture_session"),
        ),
        sa.ForeignKeyConstraint(
            ("radio_id",),
            ("radio.id",),
            ondelete="RESTRICT",
            name=op.f("fk_analysis_scope_radio_id_radio"),
        ),
        sa.ForeignKeyConstraint(
            ("session_id", "stream_id"),
            ("radio_stream.session_id", "radio_stream.id"),
            ondelete="RESTRICT",
            name=op.f("fk_analysis_scope_session_id_stream_id_radio_stream"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_scope")),
        sa.UniqueConstraint("canonical_digest", name=op.f("uq_analysis_scope_canonical_digest")),
    )
    op.create_index(op.f("ix_analysis_scope_session_id"), "analysis_scope", ("session_id",))

    op.create_table(
        "raw_integrity_attestation",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("manifest_digest", sa.String(71), nullable=False),
        sa.Column("attestation_digest", sa.String(71), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ("session_id",),
            ("capture_session.id",),
            ondelete="RESTRICT",
            name=op.f("fk_raw_integrity_attestation_session_id_capture_session"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_integrity_attestation")),
        sa.UniqueConstraint(
            "attestation_digest", name=op.f("uq_raw_integrity_attestation_attestation_digest")
        ),
    )
    op.create_index(
        op.f("ix_raw_integrity_attestation_session_id"),
        "raw_integrity_attestation",
        ("session_id",),
    )

    op.create_table(
        "stage_derivation",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("derivation_key", sa.String(71), nullable=False),
        sa.Column("stage_key", sa.String(128), nullable=False),
        sa.Column("algorithm_version", sa.String(128), nullable=False),
        sa.Column("implementation_digest", sa.String(71), nullable=False),
        sa.Column("configuration_digest", sa.String(71), nullable=False),
        sa.Column("environment_digest", sa.String(71), nullable=False),
        sa.Column("scope_digest", sa.String(71), nullable=False),
        sa.Column("input_closure_digest", sa.String(71), nullable=False),
        sa.Column("key_document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("producing_release_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ("producing_release_id",),
            ("pipeline_release.id",),
            ondelete="RESTRICT",
            name=op.f("fk_stage_derivation_producing_release_id_pipeline_release"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stage_derivation")),
        sa.UniqueConstraint("derivation_key", name=op.f("uq_stage_derivation_derivation_key")),
    )
    op.create_table(
        "stage_derivation_output",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("derivation_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("logical_uri", sa.Text(), nullable=False),
        sa.Column("digest", sa.String(71), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "byte_size >= 0", name=op.f("ck_stage_derivation_output_nonnegative_byte_size")
        ),
        sa.CheckConstraint(
            "schema_version > 0", name=op.f("ck_stage_derivation_output_positive_schema_version")
        ),
        sa.ForeignKeyConstraint(
            ("derivation_id",),
            ("stage_derivation.id",),
            ondelete="RESTRICT",
            name=op.f("fk_stage_derivation_output_derivation_id_stage_derivation"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stage_derivation_output")),
        sa.UniqueConstraint(
            "derivation_id",
            "kind",
            "schema_version",
            name=op.f("uq_stage_derivation_output_derivation_id_kind_schema_version"),
        ),
    )
    op.create_index(
        op.f("ix_stage_derivation_output_derivation_id"),
        "stage_derivation_output",
        ("derivation_id",),
    )

    op.create_table(
        "worker_incompatibility_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("pipeline_release_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("worker_authority", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ("pipeline_release_id",),
            ("pipeline_release.id",),
            ondelete="RESTRICT",
            name=op.f("fk_worker_incompatibility_event_pipeline_release_id_pipeline_release"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_incompatibility_event")),
    )
    op.create_index(
        op.f("ix_worker_incompatibility_event_worker_id"),
        "worker_incompatibility_event",
        ("worker_id",),
    )
    op.create_index(
        op.f("ix_worker_incompatibility_event_pipeline_release_id"),
        "worker_incompatibility_event",
        ("pipeline_release_id",),
    )

    op.add_column("analysis_run", sa.Column("expanded_plan_digest", sa.String(71)))
    op.add_column("analysis_run", sa.Column("raw_integrity_attestation_id", sa.BigInteger()))
    op.create_foreign_key(
        op.f("fk_analysis_run_raw_integrity_attestation_id_raw_integrity_attestation"),
        "analysis_run",
        "raw_integrity_attestation",
        ("raw_integrity_attestation_id",),
        ("id",),
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        op.f("uq_analysis_run_raw_integrity_attestation_id"),
        "analysis_run",
        ("raw_integrity_attestation_id",),
    )

    op.add_column("processing_job", sa.Column("node_id", sa.String(128)))
    op.add_column(
        "processing_job",
        sa.Column("resource_class", sa.String(32), nullable=False, server_default="streaming"),
    )
    op.add_column(
        "processing_job",
        sa.Column("iq_access", sa.String(16), nullable=False, server_default="legacy"),
    )
    op.add_column("processing_job", sa.Column("scope_id", sa.BigInteger()))
    op.create_unique_constraint(
        op.f("uq_processing_job_run_id_node_id"),
        "processing_job",
        ("run_id", "node_id"),
    )
    op.create_foreign_key(
        op.f("fk_processing_job_scope_id_analysis_scope"),
        "processing_job",
        "analysis_scope",
        ("scope_id",),
        ("id",),
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_processing_job_scope_id"), "processing_job", ("scope_id",))
    op.add_column(
        "processing_job_dependency",
        sa.Column(
            "requires_product", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    op.add_column("analysis_product", sa.Column("scope_id", sa.BigInteger()))
    op.add_column("analysis_product", sa.Column("derivation_output_id", sa.BigInteger()))
    op.add_column(
        "analysis_product",
        sa.Column("derivation_mode", sa.String(16), nullable=False, server_default="legacy"),
    )
    op.add_column("analysis_product", sa.Column("reused_from_product_id", sa.BigInteger()))
    op.create_foreign_key(
        op.f("fk_analysis_product_scope_id_analysis_scope"),
        "analysis_product",
        "analysis_scope",
        ("scope_id",),
        ("id",),
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_analysis_product_derivation_output_id_stage_derivation_output"),
        "analysis_product",
        "stage_derivation_output",
        ("derivation_output_id",),
        ("id",),
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_analysis_product_reused_from_product_id_analysis_product"),
        "analysis_product",
        "analysis_product",
        ("reused_from_product_id",),
        ("id",),
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_analysis_product_scope_id"), "analysis_product", ("scope_id",))
    op.create_index(
        op.f("ix_analysis_product_derivation_output_id"),
        "analysis_product",
        ("derivation_output_id",),
    )
    op.create_index(
        op.f("ix_analysis_product_reused_from_product_id"),
        "analysis_product",
        ("reused_from_product_id",),
    )
    op.create_check_constraint(
        op.f("ck_analysis_product_derivation_mode_values"),
        "analysis_product",
        "derivation_mode IN ('legacy', 'computed', 'reused')",
    )
    op.create_check_constraint(
        op.f("ck_analysis_product_derivation_lineage_coherent"),
        "analysis_product",
        "(derivation_mode = 'legacy' AND derivation_output_id IS NULL "
        "AND reused_from_product_id IS NULL) OR "
        "(derivation_mode = 'computed' AND derivation_output_id IS NOT NULL "
        "AND reused_from_product_id IS NULL) OR "
        "(derivation_mode = 'reused' AND derivation_output_id IS NOT NULL "
        "AND reused_from_product_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_analysis_product_derivation_lineage_coherent"), "analysis_product", type_="check"
    )
    op.drop_constraint(
        op.f("ck_analysis_product_derivation_mode_values"), "analysis_product", type_="check"
    )
    op.drop_index(op.f("ix_analysis_product_reused_from_product_id"), table_name="analysis_product")
    op.drop_index(op.f("ix_analysis_product_derivation_output_id"), table_name="analysis_product")
    op.drop_index(op.f("ix_analysis_product_scope_id"), table_name="analysis_product")
    op.drop_constraint(
        op.f("fk_analysis_product_reused_from_product_id_analysis_product"),
        "analysis_product",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_analysis_product_derivation_output_id_stage_derivation_output"),
        "analysis_product",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_analysis_product_scope_id_analysis_scope"), "analysis_product", type_="foreignkey"
    )
    op.drop_column("analysis_product", "reused_from_product_id")
    op.drop_column("analysis_product", "derivation_mode")
    op.drop_column("analysis_product", "derivation_output_id")
    op.drop_column("analysis_product", "scope_id")
    op.drop_column("processing_job_dependency", "requires_product")
    op.drop_index(op.f("ix_processing_job_scope_id"), table_name="processing_job")
    op.drop_constraint(
        op.f("fk_processing_job_scope_id_analysis_scope"), "processing_job", type_="foreignkey"
    )
    op.drop_column("processing_job", "scope_id")
    op.drop_column("processing_job", "iq_access")
    op.drop_column("processing_job", "resource_class")
    op.drop_constraint(op.f("uq_processing_job_run_id_node_id"), "processing_job", type_="unique")
    op.drop_column("processing_job", "node_id")
    op.drop_constraint(
        op.f("uq_analysis_run_raw_integrity_attestation_id"), "analysis_run", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_analysis_run_raw_integrity_attestation_id_raw_integrity_attestation"),
        "analysis_run",
        type_="foreignkey",
    )
    op.drop_column("analysis_run", "raw_integrity_attestation_id")
    op.drop_column("analysis_run", "expanded_plan_digest")
    op.drop_index(
        op.f("ix_worker_incompatibility_event_pipeline_release_id"),
        table_name="worker_incompatibility_event",
    )
    op.drop_index(
        op.f("ix_worker_incompatibility_event_worker_id"), table_name="worker_incompatibility_event"
    )
    op.drop_table("worker_incompatibility_event")
    op.drop_index(
        op.f("ix_stage_derivation_output_derivation_id"), table_name="stage_derivation_output"
    )
    op.drop_table("stage_derivation_output")
    op.drop_table("stage_derivation")
    op.drop_index(
        op.f("ix_raw_integrity_attestation_session_id"), table_name="raw_integrity_attestation"
    )
    op.drop_table("raw_integrity_attestation")
    op.drop_index(op.f("ix_analysis_scope_session_id"), table_name="analysis_scope")
    op.drop_table("analysis_scope")
    op.drop_column("pipeline_release", "executable_digest")
    op.drop_column("pipeline_release", "configuration_digest")
