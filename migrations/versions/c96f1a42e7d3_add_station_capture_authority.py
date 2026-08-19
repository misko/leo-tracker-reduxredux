"""add immutable station and capture path authority

Revision ID: c96f1a42e7d3
Revises: a85e4c71d9f0
Create Date: 2026-08-20 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c96f1a42e7d3"
down_revision: str | Sequence[str] | None = "a85e4c71d9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Earlier releases inferred resolved paths from mutable calibration tables.
    # Those rows cannot prove which station document authorized the capture.
    op.execute("DROP TRIGGER capture_receiver_lineage_immutable ON capture_receiver_lineage")
    op.drop_constraint(
        op.f("ck_capture_receiver_lineage_resolution_shape"),
        "capture_receiver_lineage",
        type_="check",
    )
    op.execute(
        "UPDATE capture_receiver_lineage SET lineage_status='unresolved', "
        "physical_receiver_id=NULL, hardware_epoch_external_id=NULL, "
        "receiver_path_id=NULL, hardware_epoch_id=NULL"
    )

    op.create_table(
        "station_topology",
        sa.Column("topology_digest", sa.String(length=71), nullable=False),
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("topology_revision", sa.String(length=128), nullable=False),
        sa.Column("valid_from_utc_ns", sa.BigInteger(), nullable=False),
        sa.Column("valid_until_utc_ns", sa.BigInteger(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assignment_sealed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "valid_from_utc_ns >= 0 AND valid_until_utc_ns > valid_from_utc_ns",
            name=op.f("ck_station_topology_valid_interval"),
        ),
        sa.PrimaryKeyConstraint("topology_digest", name=op.f("pk_station_topology")),
        sa.UniqueConstraint(
            "station_id",
            "topology_revision",
            name=op.f("uq_station_topology_station_id_topology_revision"),
        ),
    )
    op.create_table(
        "station_receiver_assignment",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("topology_digest", sa.String(length=71), nullable=False),
        sa.Column("radio_id", sa.String(length=128), nullable=False),
        sa.Column("radio_serial", sa.String(length=128), nullable=False),
        sa.Column("radio_transport", sa.String(length=32), nullable=False),
        sa.Column("radio_endpoint", sa.Text(), nullable=False),
        sa.Column("endpoint_evidence_uri", sa.Text(), nullable=False),
        sa.Column("endpoint_evidence_digest", sa.String(length=71), nullable=False),
        sa.Column("receiver_id", sa.SmallInteger(), nullable=False),
        sa.Column("physical_receiver_id", sa.String(length=128), nullable=False),
        sa.Column("hardware_epoch_external_id", sa.String(length=128), nullable=False),
        sa.Column("valid_from_utc_ns", sa.BigInteger(), nullable=False),
        sa.Column("valid_until_utc_ns", sa.BigInteger(), nullable=False),
        sa.Column("receiver_path_id", sa.BigInteger(), nullable=False),
        sa.Column("hardware_epoch_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "receiver_id IN (0, 1)",
            name=op.f("ck_station_receiver_assignment_receiver_values"),
        ),
        sa.CheckConstraint(
            "valid_from_utc_ns >= 0 AND valid_until_utc_ns > valid_from_utc_ns",
            name=op.f("ck_station_receiver_assignment_valid_interval"),
        ),
        sa.ForeignKeyConstraint(
            ["topology_digest"],
            ["station_topology.topology_digest"],
            name=op.f("fk_station_receiver_assignment_topology_digest_station_topology"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["radio_id"],
            ["radio.id"],
            name=op.f("fk_station_receiver_assignment_radio_id_radio"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receiver_path_id"],
            ["receiver_path.id"],
            name=op.f("fk_station_receiver_assignment_receiver_path_id_receiver_path"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hardware_epoch_id"],
            ["hardware_epoch.id"],
            name=op.f("fk_station_receiver_assignment_hardware_epoch_id_hardware_epoch"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_station_receiver_assignment")),
        sa.UniqueConstraint(
            "topology_digest",
            "radio_id",
            "receiver_id",
            "valid_from_utc_ns",
            "valid_until_utc_ns",
            name="exact_interval",
        ),
    )
    op.create_index(
        op.f("ix_station_receiver_assignment_topology_digest"),
        "station_receiver_assignment",
        ["topology_digest"],
    )
    op.create_table(
        "capture_path_authority",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("manifest_digest", sa.String(length=71), nullable=False),
        sa.Column("manifest_snapshot_digest", sa.String(length=71), nullable=False),
        sa.Column("authority_kind", sa.String(length=32), nullable=False),
        sa.Column("authority_digest", sa.String(length=71), nullable=False),
        sa.Column("topology_digest", sa.String(length=71)),
        sa.Column("evidence_only", sa.Boolean(), nullable=False),
        sa.Column("current_analysis_eligible", sa.Boolean(), nullable=False),
        sa.Column("physical_association_permitted", sa.Boolean(), nullable=False),
        sa.Column("calibration_association_permitted", sa.Boolean(), nullable=False),
        sa.Column("promotion_permitted", sa.Boolean(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(authority_kind='station' AND topology_digest IS NOT NULL "
            "AND NOT evidence_only AND current_analysis_eligible "
            "AND physical_association_permitted AND calibration_association_permitted "
            "AND promotion_permitted) OR "
            "(authority_kind='protected_test_fixture' AND topology_digest IS NULL "
            "AND evidence_only AND NOT current_analysis_eligible "
            "AND NOT physical_association_permitted "
            "AND NOT calibration_association_permitted AND NOT promotion_permitted)",
            name=op.f("ck_capture_path_authority_kind_capabilities"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["capture_session.id"],
            name=op.f("fk_capture_path_authority_session_id_capture_session"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["topology_digest"],
            ["station_topology.topology_digest"],
            name=op.f("fk_capture_path_authority_topology_digest_station_topology"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_capture_path_authority")),
        sa.UniqueConstraint(
            "authority_digest", name=op.f("uq_capture_path_authority_authority_digest")
        ),
    )
    op.add_column(
        "capture_receiver_lineage",
        sa.Column("capture_authority_session_id", sa.String(length=128)),
    )
    op.add_column(
        "capture_receiver_lineage",
        sa.Column("station_assignment_id", sa.BigInteger()),
    )
    op.create_foreign_key(
        op.f("fk_capture_receiver_lineage_capture_authority_session_id_capture_path_authority"),
        "capture_receiver_lineage",
        "capture_path_authority",
        ["capture_authority_session_id"],
        ["session_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_capture_receiver_lineage_station_assignment_id_station_receiver_assignment"),
        "capture_receiver_lineage",
        "station_receiver_assignment",
        ["station_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_capture_receiver_lineage_resolution_shape"),
        "capture_receiver_lineage",
        "(lineage_status = 'resolved' AND receiver_path_id IS NOT NULL "
        "AND hardware_epoch_id IS NOT NULL AND physical_receiver_id IS NOT NULL "
        "AND hardware_epoch_external_id IS NOT NULL "
        "AND capture_authority_session_id IS NOT NULL AND station_assignment_id IS NOT NULL) "
        "OR (lineage_status = 'unresolved' AND receiver_path_id IS NULL "
        "AND hardware_epoch_id IS NULL AND physical_receiver_id IS NULL "
        "AND hardware_epoch_external_id IS NULL AND station_assignment_id IS NULL)",
    )

    op.execute(
        """
        CREATE FUNCTION leo_guard_station_assignment_insert() RETURNS trigger AS $$
        DECLARE sealed boolean;
        BEGIN
          SELECT assignment_sealed INTO sealed FROM station_topology
          WHERE topology_digest=NEW.topology_digest FOR UPDATE;
          IF sealed IS DISTINCT FROM false THEN
            RAISE EXCEPTION 'station topology assignment inventory is sealed';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION leo_require_station_topology_sealed() RETURNS trigger AS $$
        DECLARE sealed boolean;
        BEGIN
          SELECT assignment_sealed INTO sealed FROM station_topology
          WHERE topology_digest=NEW.topology_digest;
          IF sealed IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'station topology cannot commit with unsealed assignments';
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER station_assignment_insert_guard BEFORE INSERT ON "
        "station_receiver_assignment FOR EACH ROW EXECUTE FUNCTION "
        "leo_guard_station_assignment_insert()"
    )
    op.execute(
        "CREATE TRIGGER station_assignment_immutable BEFORE UPDATE OR DELETE ON "
        "station_receiver_assignment FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER station_topology_identity_immutable BEFORE UPDATE OF "
        "topology_digest, station_id, topology_revision, valid_from_utc_ns, "
        "valid_until_utc_ns, document ON station_topology FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER station_topology_seal_immutable BEFORE UPDATE OF assignment_sealed "
        "ON station_topology FOR EACH ROW WHEN "
        "(OLD.assignment_sealed OR NOT NEW.assignment_sealed) "
        "EXECUTE FUNCTION leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER station_topology_delete_immutable BEFORE DELETE ON station_topology "
        "FOR EACH ROW EXECUTE FUNCTION leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER station_topology_must_seal AFTER INSERT OR UPDATE OF "
        "assignment_sealed ON station_topology DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION leo_require_station_topology_sealed()"
    )
    op.execute(
        "CREATE TRIGGER capture_path_authority_immutable BEFORE UPDATE OR DELETE ON "
        "capture_path_authority FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER capture_receiver_lineage_immutable BEFORE UPDATE OR DELETE ON "
        "capture_receiver_lineage FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_foundation_identity_update()"
    )
    op.execute(
        """
        CREATE FUNCTION leo_guard_test_fixture_promotion() RETURNS trigger AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM capture_path_authority authority
            WHERE authority.session_id=NEW.session_id
              AND authority.authority_kind='protected_test_fixture'
          ) AND NEW.promotion_policy <> 'evidence_only' THEN
            RAISE EXCEPTION 'protected TEST authority requires evidence-only analysis';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER analysis_run_test_fixture_evidence_only BEFORE INSERT OR UPDATE OF "
        "session_id, promotion_policy ON analysis_run FOR EACH ROW EXECUTE FUNCTION "
        "leo_guard_test_fixture_promotion()"
    )
    op.execute(
        """
        CREATE FUNCTION leo_guard_test_fixture_current() RETURNS trigger AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM capture_path_authority authority
            WHERE authority.session_id=NEW.session_id
              AND authority.authority_kind='protected_test_fixture'
          ) THEN
            RAISE EXCEPTION 'protected TEST authority cannot become current analysis';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER current_analysis_test_fixture_forbidden BEFORE INSERT OR UPDATE ON "
        "current_analysis FOR EACH ROW EXECUTE FUNCTION leo_guard_test_fixture_current()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    authoritative_rows = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM station_topology) OR "
            "EXISTS (SELECT 1 FROM capture_path_authority) OR "
            "EXISTS (SELECT 1 FROM capture_receiver_lineage)"
        )
    )
    if authoritative_rows:
        raise RuntimeError(
            "cannot downgrade after station migration changed capture lineage authority"
        )
    op.execute("DROP TRIGGER current_analysis_test_fixture_forbidden ON current_analysis")
    op.execute("DROP FUNCTION leo_guard_test_fixture_current()")
    op.execute("DROP TRIGGER analysis_run_test_fixture_evidence_only ON analysis_run")
    op.execute("DROP FUNCTION leo_guard_test_fixture_promotion()")
    op.execute("DROP TRIGGER capture_receiver_lineage_immutable ON capture_receiver_lineage")
    op.drop_constraint(
        op.f("ck_capture_receiver_lineage_resolution_shape"),
        "capture_receiver_lineage",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_capture_receiver_lineage_station_assignment_id_station_receiver_assignment"),
        "capture_receiver_lineage",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_capture_receiver_lineage_capture_authority_session_id_capture_path_authority"),
        "capture_receiver_lineage",
        type_="foreignkey",
    )
    op.drop_column("capture_receiver_lineage", "station_assignment_id")
    op.drop_column("capture_receiver_lineage", "capture_authority_session_id")
    op.create_check_constraint(
        op.f("ck_capture_receiver_lineage_resolution_shape"),
        "capture_receiver_lineage",
        "(lineage_status = 'resolved' AND receiver_path_id IS NOT NULL "
        "AND hardware_epoch_id IS NOT NULL AND physical_receiver_id IS NOT NULL "
        "AND hardware_epoch_external_id IS NOT NULL) OR "
        "(lineage_status = 'unresolved' AND receiver_path_id IS NULL "
        "AND hardware_epoch_id IS NULL AND physical_receiver_id IS NULL "
        "AND hardware_epoch_external_id IS NULL)",
    )
    op.execute(
        "CREATE TRIGGER capture_receiver_lineage_immutable BEFORE UPDATE OR DELETE ON "
        "capture_receiver_lineage FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_foundation_identity_update()"
    )
    op.execute("DROP TRIGGER capture_path_authority_immutable ON capture_path_authority")
    op.execute("DROP TRIGGER station_topology_must_seal ON station_topology")
    op.execute("DROP TRIGGER station_topology_delete_immutable ON station_topology")
    op.execute("DROP TRIGGER station_topology_seal_immutable ON station_topology")
    op.execute("DROP TRIGGER station_topology_identity_immutable ON station_topology")
    op.execute("DROP TRIGGER station_assignment_immutable ON station_receiver_assignment")
    op.execute("DROP TRIGGER station_assignment_insert_guard ON station_receiver_assignment")
    op.execute("DROP FUNCTION leo_require_station_topology_sealed()")
    op.execute("DROP FUNCTION leo_guard_station_assignment_insert()")
    op.drop_table("capture_path_authority")
    op.drop_index(
        op.f("ix_station_receiver_assignment_topology_digest"),
        table_name="station_receiver_assignment",
    )
    op.drop_table("station_receiver_assignment")
    op.drop_table("station_topology")
