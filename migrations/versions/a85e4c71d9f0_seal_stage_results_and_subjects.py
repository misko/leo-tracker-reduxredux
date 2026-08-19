"""seal typed stage results and freeze run subject bindings

Revision ID: a85e4c71d9f0
Revises: f74c9d30b6e2
Create Date: 2026-08-20 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a85e4c71d9f0"
down_revision: str | Sequence[str] | None = "f74c9d30b6e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_product",
        sa.Column("lineage_sealed", sa.Boolean(), server_default=sa.false(), nullable=True),
    )
    op.execute("UPDATE analysis_product SET lineage_sealed=true")
    op.alter_column("analysis_product", "lineage_sealed", nullable=False)
    op.create_table(
        "run_subject_binding",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("scope_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("binding_digest", sa.String(length=71), nullable=False),
        sa.Column("snapshot_digest", sa.String(length=71), nullable=False),
        sa.Column("document", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('receiver_path', 'paired')",
            name=op.f("ck_run_subject_binding_kind_values"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["analysis_run.id"],
            name=op.f("fk_run_subject_binding_run_id_analysis_run"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scope_id"],
            ["analysis_scope.id"],
            name=op.f("fk_run_subject_binding_scope_id_analysis_scope"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_subject_binding")),
        sa.UniqueConstraint(
            "run_id",
            "scope_id",
            name=op.f("uq_run_subject_binding_run_id_scope_id"),
        ),
        sa.UniqueConstraint(
            "snapshot_digest",
            name=op.f("uq_run_subject_binding_snapshot_digest"),
        ),
    )
    op.create_index(
        op.f("ix_run_subject_binding_run_id"),
        "run_subject_binding",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_subject_binding_scope_id"),
        "run_subject_binding",
        ["scope_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION leo_guard_product_dependency_insert() RETURNS trigger AS $$
        DECLARE sealed boolean;
        BEGIN
          SELECT lineage_sealed INTO sealed FROM analysis_product
          WHERE id=NEW.product_id FOR UPDATE;
          IF sealed IS DISTINCT FROM false THEN
            RAISE EXCEPTION 'product dependency lineage is sealed';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION leo_require_product_lineage_sealed() RETURNS trigger AS $$
        DECLARE sealed boolean;
        BEGIN
          SELECT lineage_sealed INTO sealed FROM analysis_product WHERE id=NEW.id;
          IF sealed IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'analysis product cannot commit with unsealed lineage';
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER product_dependency_insert_guard BEFORE INSERT ON product_dependency "
        "FOR EACH ROW EXECUTE FUNCTION leo_guard_product_dependency_insert()"
    )
    op.execute(
        "CREATE TRIGGER product_dependency_mutation_immutable BEFORE UPDATE OR DELETE ON "
        "product_dependency FOR EACH ROW EXECUTE FUNCTION leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER analysis_product_lineage_reopen_immutable BEFORE UPDATE OF "
        "lineage_sealed ON analysis_product FOR EACH ROW "
        "WHEN (OLD.lineage_sealed OR NOT NEW.lineage_sealed) EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER analysis_product_lineage_must_seal AFTER INSERT OR UPDATE OF "
        "lineage_sealed ON analysis_product DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION leo_require_product_lineage_sealed()"
    )
    op.execute(
        "CREATE TRIGGER raw_integrity_attestation_immutable BEFORE UPDATE OR DELETE ON "
        "raw_integrity_attestation FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER run_subject_binding_immutable BEFORE UPDATE OR DELETE ON "
        "run_subject_binding FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    authoritative_rows = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM raw_integrity_attestation) OR "
            "EXISTS (SELECT 1 FROM run_subject_binding) OR "
            "EXISTS (SELECT 1 FROM analysis_product)"
        )
    )
    if authoritative_rows:
        raise RuntimeError(
            "cannot downgrade while attestations, subject snapshots, or sealed products exist"
        )
    op.execute("DROP TRIGGER run_subject_binding_immutable ON run_subject_binding")
    op.execute("DROP TRIGGER raw_integrity_attestation_immutable ON raw_integrity_attestation")
    op.execute("DROP TRIGGER analysis_product_lineage_must_seal ON analysis_product")
    op.execute("DROP TRIGGER analysis_product_lineage_reopen_immutable ON analysis_product")
    op.execute("DROP TRIGGER product_dependency_mutation_immutable ON product_dependency")
    op.execute("DROP TRIGGER product_dependency_insert_guard ON product_dependency")
    op.execute("DROP FUNCTION leo_require_product_lineage_sealed()")
    op.execute("DROP FUNCTION leo_guard_product_dependency_insert()")
    op.drop_index(op.f("ix_run_subject_binding_scope_id"), table_name="run_subject_binding")
    op.drop_index(op.f("ix_run_subject_binding_run_id"), table_name="run_subject_binding")
    op.drop_table("run_subject_binding")
    op.drop_column("analysis_product", "lineage_sealed")
