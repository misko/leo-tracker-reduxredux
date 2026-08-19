"""harden calibration publication

Revision ID: f62a9d174be1
Revises: e4b17c8d93af
Create Date: 2026-08-19 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f62a9d174be1"
down_revision: str | Sequence[str] | None = "e4b17c8d93af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hardware_epoch", sa.Column("started_utc_ns", sa.BigInteger()))
    op.add_column("hardware_epoch", sa.Column("ended_utc_ns", sa.BigInteger()))
    op.add_column(
        "frequency_calibration_set",
        sa.Column("sealed_at", sa.DateTime(timezone=True)),
    )
    op.add_column("frequency_calibration_set", sa.Column("promotion_id", sa.String(128)))
    op.add_column("frequency_calibration_set", sa.Column("sealed_utc_ns", sa.BigInteger()))

    op.execute("DROP TRIGGER hardware_epoch_authoritative_immutable ON hardware_epoch")
    for table in ("frequency_calibration_set", "frequency_calibration_set_member"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
    op.execute("DROP FUNCTION leo_calibration_set_immutable()")

    op.execute(
        "UPDATE hardware_epoch SET started_utc_ns = "
        "(extract(epoch FROM started_at) * 1000000000)::bigint, "
        "ended_utc_ns = CASE WHEN ended_at IS NULL THEN NULL ELSE "
        "(extract(epoch FROM ended_at) * 1000000000)::bigint END"
    )
    op.execute(
        "UPDATE frequency_calibration_set SET sealed_at = created_at"
    )
    op.create_unique_constraint(
        op.f("uq_frequency_calibration_set_promotion_id"),
        "frequency_calibration_set",
        ["promotion_id"],
    )

    op.execute(
        "CREATE TRIGGER hardware_epoch_authoritative_immutable "
        "BEFORE UPDATE OR DELETE ON hardware_epoch FOR EACH ROW "
        "EXECUTE FUNCTION leo_calibration_identity_immutable()"
    )
    op.execute(
        """
        CREATE FUNCTION leo_calibration_set_seal_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' OR OLD.sealed_at IS NOT NULL THEN
                RAISE EXCEPTION 'calibration set is immutable';
            END IF;
            IF NEW.sealed_at IS NULL
                OR NEW.id IS DISTINCT FROM OLD.id
                OR NEW.digest IS DISTINCT FROM OLD.digest
                OR NEW.evidence_uri IS DISTINCT FROM OLD.evidence_uri
                OR NEW.evidence_digest IS DISTINCT FROM OLD.evidence_digest
                OR NEW.promotion_id IS DISTINCT FROM OLD.promotion_id
                OR NEW.sealed_utc_ns IS DISTINCT FROM OLD.sealed_utc_ns
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'only atomic calibration-set sealing is permitted';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM frequency_calibration_set_member WHERE set_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'empty calibration set cannot be sealed';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER frequency_calibration_set_immutable "
        "BEFORE UPDATE OR DELETE ON frequency_calibration_set FOR EACH ROW "
        "EXECUTE FUNCTION leo_calibration_set_seal_immutable()"
    )
    op.execute(
        """
        CREATE FUNCTION leo_calibration_set_member_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            target_set_id text;
            target_sealed_at timestamptz;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'calibration set membership is immutable';
            END IF;
            target_set_id := NEW.set_id;
            SELECT sealed_at INTO target_sealed_at
            FROM frequency_calibration_set
            WHERE id = target_set_id
            FOR UPDATE;
            IF NOT FOUND OR target_sealed_at IS NOT NULL THEN
                RAISE EXCEPTION 'calibration set membership is closed';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER frequency_calibration_set_member_immutable "
        "BEFORE INSERT OR UPDATE OR DELETE ON frequency_calibration_set_member FOR EACH ROW "
        "EXECUTE FUNCTION leo_calibration_set_member_immutable()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER frequency_calibration_set_member_immutable "
        "ON frequency_calibration_set_member"
    )
    op.execute("DROP FUNCTION leo_calibration_set_member_immutable()")
    op.execute(
        "DROP TRIGGER frequency_calibration_set_immutable ON frequency_calibration_set"
    )
    op.execute("DROP FUNCTION leo_calibration_set_seal_immutable()")
    op.execute(
        """
        CREATE FUNCTION leo_calibration_set_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'authoritative calibration set is immutable';
        END
        $$
        """
    )
    for table in ("frequency_calibration_set", "frequency_calibration_set_member"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION leo_calibration_set_immutable()"
        )
    op.drop_constraint(
        op.f("uq_frequency_calibration_set_promotion_id"),
        "frequency_calibration_set",
        type_="unique",
    )
    op.drop_column("frequency_calibration_set", "sealed_utc_ns")
    op.drop_column("frequency_calibration_set", "promotion_id")
    op.drop_column("frequency_calibration_set", "sealed_at")
    op.drop_column("hardware_epoch", "ended_utc_ns")
    op.drop_column("hardware_epoch", "started_utc_ns")
