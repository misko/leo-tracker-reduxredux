"""add authoritative calibration catalog

Revision ID: e4b17c8d93af
Revises: c31f9d7a2e44
Create Date: 2026-08-19 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4b17c8d93af"
down_revision: str | Sequence[str] | None = "c31f9d7a2e44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receiver_path", sa.Column("physical_receiver_id", sa.String(128)))
    op.drop_constraint(
        op.f("uq_receiver_path_radio_id_receiver_id"), "receiver_path", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_receiver_path_radio_id_receiver_id_physical_receiver_id"),
        "receiver_path",
        ["radio_id", "receiver_id", "physical_receiver_id"],
    )
    op.add_column("hardware_epoch", sa.Column("external_id", sa.String(128)))
    op.create_unique_constraint(
        op.f("uq_hardware_epoch_external_id"), "hardware_epoch", ["external_id"]
    )
    op.add_column("frequency_calibration", sa.Column("external_id", sa.String(128)))
    op.add_column("frequency_calibration", sa.Column("uncertainty_lower_hz", sa.Float()))
    op.add_column("frequency_calibration", sa.Column("uncertainty_upper_hz", sa.Float()))
    op.add_column("frequency_calibration", sa.Column("valid_from_utc_ns", sa.BigInteger()))
    op.add_column("frequency_calibration", sa.Column("valid_until_utc_ns", sa.BigInteger()))
    op.add_column("frequency_calibration", sa.Column("calibration_digest", sa.String(71)))
    op.add_column("frequency_calibration", sa.Column("method", sa.String(128)))
    op.add_column("frequency_calibration", sa.Column("created_utc_ns", sa.BigInteger()))
    op.add_column(
        "frequency_calibration",
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "frequency_calibration",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        op.f("uq_frequency_calibration_external_id"),
        "frequency_calibration",
        ["external_id"],
    )
    op.create_unique_constraint(
        op.f("uq_frequency_calibration_calibration_digest"),
        "frequency_calibration",
        ["calibration_digest"],
    )
    op.create_table(
        "frequency_calibration_set",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("digest", sa.String(71), nullable=False),
        sa.Column("evidence_uri", sa.Text(), nullable=False),
        sa.Column("evidence_digest", sa.String(71), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_frequency_calibration_set")),
        sa.UniqueConstraint("digest", name=op.f("uq_frequency_calibration_set_digest")),
    )
    op.create_table(
        "frequency_calibration_set_member",
        sa.Column("set_id", sa.String(128), nullable=False),
        sa.Column("calibration_id", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["calibration_id"],
            ["frequency_calibration.id"],
            name=op.f(
                "fk_frequency_calibration_set_member_calibration_id_frequency_calibration"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["set_id"],
            ["frequency_calibration_set.id"],
            name=op.f("fk_frequency_calibration_set_member_set_id_frequency_calibration_set"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "set_id", "calibration_id", name=op.f("pk_frequency_calibration_set_member")
        ),
        sa.UniqueConstraint(
            "set_id",
            "ordinal",
            name=op.f("uq_frequency_calibration_set_member_set_id_ordinal"),
        ),
    )
    op.execute(
        """
        CREATE FUNCTION leo_calibration_identity_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME = 'receiver_path'
                AND to_jsonb(OLD)->>'physical_receiver_id' IS NOT NULL THEN
                RAISE EXCEPTION 'authoritative receiver path is immutable';
            ELSIF TG_TABLE_NAME = 'hardware_epoch'
                AND to_jsonb(OLD)->>'external_id' IS NOT NULL THEN
                RAISE EXCEPTION 'authoritative hardware epoch is immutable';
            ELSIF TG_TABLE_NAME = 'frequency_calibration'
                AND (
                    to_jsonb(OLD)->>'external_id' IS NOT NULL
                    OR to_jsonb(OLD)->>'calibration_digest' IS NOT NULL
                ) THEN
                RAISE EXCEPTION 'authoritative frequency calibration is immutable';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END
        $$
        """
    )
    for table in ("receiver_path", "hardware_epoch", "frequency_calibration"):
        op.execute(
            f"CREATE TRIGGER {table}_authoritative_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION leo_calibration_identity_immutable()"
        )
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


def downgrade() -> None:
    op.drop_table("frequency_calibration_set_member")
    op.drop_table("frequency_calibration_set")
    op.execute("DROP FUNCTION leo_calibration_set_immutable()")
    for table in ("receiver_path", "hardware_epoch", "frequency_calibration"):
        op.execute(f"DROP TRIGGER {table}_authoritative_immutable ON {table}")
    op.execute("DROP FUNCTION leo_calibration_identity_immutable()")
    op.drop_constraint(
        op.f("uq_frequency_calibration_calibration_digest"),
        "frequency_calibration",
        type_="unique",
    )
    op.drop_constraint(
        op.f("uq_frequency_calibration_external_id"),
        "frequency_calibration",
        type_="unique",
    )
    for column in (
        "created_at",
        "created_utc_ns",
        "evidence",
        "method",
        "calibration_digest",
        "uncertainty_upper_hz",
        "uncertainty_lower_hz",
        "valid_until_utc_ns",
        "valid_from_utc_ns",
        "external_id",
    ):
        op.drop_column("frequency_calibration", column)
    op.drop_constraint(
        op.f("uq_hardware_epoch_external_id"), "hardware_epoch", type_="unique"
    )
    op.drop_column("hardware_epoch", "external_id")
    op.drop_constraint(
        op.f("uq_receiver_path_radio_id_receiver_id_physical_receiver_id"),
        "receiver_path",
        type_="unique",
    )
    op.drop_column("receiver_path", "physical_receiver_id")
    op.create_unique_constraint(
        op.f("uq_receiver_path_radio_id_receiver_id"),
        "receiver_path",
        ["radio_id", "receiver_id"],
    )
