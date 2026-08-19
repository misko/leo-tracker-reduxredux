"""add campaign outer seal

Revision ID: a73c4e19d2f0
Revises: f62a9d174be1
Create Date: 2026-08-19 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a73c4e19d2f0"
down_revision: str | Sequence[str] | None = "f62a9d174be1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scientific_campaign", sa.Column("outer_seal_uri", sa.Text()))
    op.add_column("scientific_campaign", sa.Column("outer_seal_digest", sa.String(71)))
    op.add_column(
        "scientific_campaign",
        sa.Column(
            "seal_authority_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "scientific_campaign_outer_seal_authority",
        "scientific_campaign",
        "state <> 'sealed' OR seal_authority_version = 0 OR "
        "(outer_seal_uri IS NOT NULL AND outer_seal_digest IS NOT NULL)",
    )
    op.alter_column(
        "scientific_campaign",
        "seal_authority_version",
        server_default=sa.text("1"),
    )
    op.execute(
        """
        CREATE FUNCTION scientific_campaign_authority_version_fence()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'INSERT' AND NEW.seal_authority_version = 0 THEN
            RAISE EXCEPTION 'seal_authority_version=0 is reserved for migrated legacy rows';
          END IF;
          IF TG_OP = 'UPDATE' AND NEW.seal_authority_version <> OLD.seal_authority_version THEN
            RAISE EXCEPTION 'scientific campaign authority version is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER scientific_campaign_authority_version_fence
        BEFORE INSERT OR UPDATE ON scientific_campaign
        FOR EACH ROW EXECUTE FUNCTION scientific_campaign_authority_version_fence();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER scientific_campaign_authority_version_fence ON scientific_campaign")
    op.execute("DROP FUNCTION scientific_campaign_authority_version_fence()")
    op.drop_constraint(
        "scientific_campaign_outer_seal_authority",
        "scientific_campaign",
        type_="check",
    )
    op.drop_column("scientific_campaign", "seal_authority_version")
    op.drop_column("scientific_campaign", "outer_seal_digest")
    op.drop_column("scientific_campaign", "outer_seal_uri")
