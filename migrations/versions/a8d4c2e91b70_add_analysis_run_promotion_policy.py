"""add analysis-run promotion policy

Revision ID: a8d4c2e91b70
Revises: f47b536afe98
Create Date: 2026-08-19 07:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8d4c2e91b70"
down_revision: str | Sequence[str] | None = "f47b536afe98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_run",
        sa.Column(
            "promotion_policy",
            sa.String(length=16),
            server_default="current",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_analysis_run_promotion_policy_values"),
        "analysis_run",
        "promotion_policy IN ('current', 'evidence_only')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_analysis_run_promotion_policy_values"),
        "analysis_run",
        type_="check",
    )
    op.drop_column("analysis_run", "promotion_policy")
