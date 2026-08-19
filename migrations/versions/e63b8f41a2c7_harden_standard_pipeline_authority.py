"""harden Standard pipeline topology, resources and derivation lineage

Revision ID: e63b8f41a2c7
Revises: d52a7f24c8e1
Create Date: 2026-08-20 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from leo.contracts.digests import canonical_digest

revision: str = "e63b8f41a2c7"
down_revision: str | Sequence[str] | None = "d52a7f24c8e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    for release_id, configuration in bind.execute(
        sa.text("SELECT id, configuration FROM pipeline_release")
    ):
        bind.execute(
            sa.text(
                "UPDATE pipeline_release SET configuration_digest=:digest WHERE id=:release_id"
            ),
            {"release_id": release_id, "digest": canonical_digest(configuration)},
        )
    op.alter_column("pipeline_release", "configuration_digest", server_default=None)
    op.alter_column("pipeline_release", "executable_digest", server_default=None)
    op.add_column(
        "pipeline_release",
        sa.Column("authority_version", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.alter_column("pipeline_release", "authority_version", server_default=None)

    op.add_column("radio_stream", sa.Column("manifest_ordinal", sa.SmallInteger()))
    op.create_check_constraint(
        op.f("ck_radio_stream_nonnegative_manifest_ordinal"),
        "radio_stream",
        "manifest_ordinal IS NULL OR manifest_ordinal >= 0",
    )
    op.create_unique_constraint(
        op.f("uq_radio_stream_session_id_manifest_ordinal"),
        "radio_stream",
        ("session_id", "manifest_ordinal"),
    )
    op.create_table(
        "capture_receiver_lineage",
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("stream_id", sa.String(128), nullable=False),
        sa.Column("receiver_id", sa.SmallInteger(), nullable=False),
        sa.Column("radio_id", sa.String(128), nullable=False),
        sa.Column("radio_serial", sa.String(128), nullable=False),
        sa.Column("manifest_digest", sa.String(71), nullable=False),
        sa.Column("stream_identity_digest", sa.String(71), nullable=False),
        sa.Column("lineage_status", sa.String(16), nullable=False),
        sa.Column("physical_receiver_id", sa.String(128)),
        sa.Column("hardware_epoch_external_id", sa.String(128)),
        sa.Column("receiver_path_id", sa.BigInteger()),
        sa.Column("hardware_epoch_id", sa.BigInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "receiver_id IN (0, 1)", name=op.f("ck_capture_receiver_lineage_receiver_values")
        ),
        sa.CheckConstraint(
            "(lineage_status = 'resolved' AND receiver_path_id IS NOT NULL "
            "AND hardware_epoch_id IS NOT NULL AND physical_receiver_id IS NOT NULL "
            "AND hardware_epoch_external_id IS NOT NULL) OR "
            "(lineage_status = 'unresolved' AND receiver_path_id IS NULL "
            "AND hardware_epoch_id IS NULL AND physical_receiver_id IS NULL "
            "AND hardware_epoch_external_id IS NULL)",
            name=op.f("ck_capture_receiver_lineage_resolution_shape"),
        ),
        sa.ForeignKeyConstraint(
            ("session_id", "stream_id"),
            ("radio_stream.session_id", "radio_stream.id"),
            ondelete="CASCADE",
            name=op.f("fk_capture_receiver_lineage_session_id_stream_id_radio_stream"),
        ),
        sa.ForeignKeyConstraint(
            ("radio_id",),
            ("radio.id",),
            ondelete="RESTRICT",
            name=op.f("fk_capture_receiver_lineage_radio_id_radio"),
        ),
        sa.ForeignKeyConstraint(
            ("receiver_path_id",),
            ("receiver_path.id",),
            ondelete="RESTRICT",
            name=op.f("fk_capture_receiver_lineage_receiver_path_id_receiver_path"),
        ),
        sa.ForeignKeyConstraint(
            ("hardware_epoch_id",),
            ("hardware_epoch.id",),
            ondelete="RESTRICT",
            name=op.f("fk_capture_receiver_lineage_hardware_epoch_id_hardware_epoch"),
        ),
        sa.PrimaryKeyConstraint(
            "session_id",
            "stream_id",
            "receiver_id",
            name=op.f("pk_capture_receiver_lineage"),
        ),
    )
    op.create_index(
        op.f("ix_capture_receiver_lineage_radio_id"),
        "capture_receiver_lineage",
        ("radio_id",),
    )

    op.add_column("stage_derivation_output", sa.Column("role", sa.String(16)))
    bind.execute(
        sa.text(
            "UPDATE stage_derivation_output output SET role=roles.role FROM "
            "(SELECT derivation_output_id, min(role) AS role FROM analysis_product "
            "WHERE derivation_output_id IS NOT NULL GROUP BY derivation_output_id "
            "HAVING min(role)=max(role)) roles WHERE output.id=roles.derivation_output_id"
        )
    )
    unresolved = bind.scalar(
        sa.text("SELECT count(*) FROM stage_derivation_output WHERE role IS NULL")
    )
    if unresolved:
        raise RuntimeError(
            "cannot infer authoritative roles for populated stage derivation outputs"
        )
    op.alter_column("stage_derivation_output", "role", nullable=False)
    op.create_check_constraint(
        op.f("ck_stage_derivation_output_role_values"),
        "stage_derivation_output",
        "role IN ('scientific', 'presentation')",
    )

    op.create_check_constraint(
        op.f("ck_processing_job_resource_class_values"),
        "processing_job",
        "resource_class IN ('streaming', 'cpu', 'memory', 'heavy')",
    )
    op.create_check_constraint(
        op.f("ck_processing_job_iq_access_values"),
        "processing_job",
        "iq_access IN ('legacy', 'none', 'receiver_path')",
    )
    op.create_table(
        "processing_resource_capacity",
        sa.Column("resource_class", sa.String(32), nullable=False),
        sa.Column("maximum_leases", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "resource_class IN ('streaming', 'cpu', 'memory', 'heavy')",
            name=op.f("ck_processing_resource_capacity_resource_values"),
        ),
        sa.CheckConstraint(
            "maximum_leases > 0",
            name=op.f("ck_processing_resource_capacity_positive_maximum"),
        ),
        sa.PrimaryKeyConstraint("resource_class", name=op.f("pk_processing_resource_capacity")),
    )
    op.bulk_insert(
        sa.table(
            "processing_resource_capacity",
            sa.column("resource_class", sa.String),
            sa.column("maximum_leases", sa.Integer),
        ),
        [
            {"resource_class": "streaming", "maximum_leases": 16},
            {"resource_class": "cpu", "maximum_leases": 8},
            {"resource_class": "memory", "maximum_leases": 4},
            {"resource_class": "heavy", "maximum_leases": 4},
        ],
    )
    op.execute(
        """
        CREATE FUNCTION leo_reject_foundation_identity_update() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'authoritative foundation identity is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER capture_receiver_lineage_immutable BEFORE UPDATE OR DELETE ON "
        "capture_receiver_lineage FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_foundation_identity_update()"
    )
    op.execute(
        "CREATE TRIGGER stage_derivation_output_identity_immutable BEFORE UPDATE OF "
        "derivation_id, kind, schema_version, role, status, media_type, logical_uri, digest, "
        "byte_size, summary OR DELETE ON stage_derivation_output FOR EACH ROW "
        "EXECUTE FUNCTION leo_reject_foundation_identity_update()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    typed = bind.scalar(
        sa.text(
            "SELECT (EXISTS (SELECT 1 FROM analysis_scope) OR "
            "EXISTS (SELECT 1 FROM processing_job WHERE node_id IS NOT NULL) OR "
            "EXISTS (SELECT 1 FROM raw_integrity_attestation) OR "
            "EXISTS (SELECT 1 FROM stage_derivation) OR "
            "EXISTS (SELECT 1 FROM capture_receiver_lineage))"
        )
    )
    if typed:
        raise RuntimeError("refusing to downgrade while authoritative typed rows exist")
    op.execute("DROP TRIGGER stage_derivation_output_identity_immutable ON stage_derivation_output")
    op.execute("DROP TRIGGER capture_receiver_lineage_immutable ON capture_receiver_lineage")
    op.execute("DROP FUNCTION leo_reject_foundation_identity_update()")
    op.drop_constraint(op.f("ck_processing_job_iq_access_values"), "processing_job", type_="check")
    op.drop_constraint(
        op.f("ck_processing_job_resource_class_values"), "processing_job", type_="check"
    )
    op.drop_table("processing_resource_capacity")
    op.drop_constraint(
        op.f("ck_stage_derivation_output_role_values"),
        "stage_derivation_output",
        type_="check",
    )
    op.drop_column("stage_derivation_output", "role")
    op.drop_index(
        op.f("ix_capture_receiver_lineage_radio_id"),
        table_name="capture_receiver_lineage",
    )
    op.drop_table("capture_receiver_lineage")
    op.drop_constraint(
        op.f("uq_radio_stream_session_id_manifest_ordinal"),
        "radio_stream",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_radio_stream_nonnegative_manifest_ordinal"),
        "radio_stream",
        type_="check",
    )
    op.drop_column("radio_stream", "manifest_ordinal")
    op.drop_column("pipeline_release", "authority_version")
    op.alter_column(
        "pipeline_release",
        "executable_digest",
        server_default="sha256:" + "0" * 64,
    )
    op.alter_column(
        "pipeline_release",
        "configuration_digest",
        server_default="sha256:" + "0" * 64,
    )
