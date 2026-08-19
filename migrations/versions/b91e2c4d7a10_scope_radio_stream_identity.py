"""scope radio stream identity to its capture session

Revision ID: b91e2c4d7a10
Revises: a73c4e19d2f0
Create Date: 2026-08-19 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b91e2c4d7a10"
down_revision: str | Sequence[str] | None = "a73c4e19d2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recording_chunk", sa.Column("session_id", sa.String(128)))
    op.execute(
        "UPDATE recording_chunk chunk SET session_id = stream.session_id "
        "FROM radio_stream stream WHERE stream.id = chunk.stream_id"
    )
    op.alter_column("recording_chunk", "session_id", nullable=False)

    op.drop_constraint(
        "fk_recording_chunk_stream_id_radio_stream", "recording_chunk", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_scientific_campaign_stream_stream_id_radio_stream",
        "scientific_campaign_stream",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_recording_chunk_stream_id_chunk_index", "recording_chunk", type_="unique"
    )
    op.drop_constraint("pk_radio_stream", "radio_stream", type_="primary")
    op.create_primary_key("pk_radio_stream", "radio_stream", ("session_id", "id"))
    op.create_foreign_key(
        "fk_recording_chunk_session_id_stream_id_radio_stream",
        "recording_chunk",
        "radio_stream",
        ("session_id", "stream_id"),
        ("session_id", "id"),
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_scientific_campaign_stream_session_id_stream_id_radio_stream",
        "scientific_campaign_stream",
        "radio_stream",
        ("session_id", "stream_id"),
        ("session_id", "id"),
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_recording_chunk_session_id_stream_id_chunk_index",
        "recording_chunk",
        ("session_id", "stream_id", "chunk_index"),
    )
    op.create_index(
        "ix_recording_chunk_session_id_stream_id",
        "recording_chunk",
        ("session_id", "stream_id"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.exec_driver_sql(
        "SELECT id FROM radio_stream GROUP BY id HAVING count(*) > 1 LIMIT 1"
    ).first()
    if duplicate is not None:
        raise RuntimeError("cannot downgrade radio stream identity with repeated stream ids")
    op.drop_index("ix_recording_chunk_session_id_stream_id", table_name="recording_chunk")
    op.drop_constraint(
        "uq_recording_chunk_session_id_stream_id_chunk_index",
        "recording_chunk",
        type_="unique",
    )
    op.drop_constraint(
        "fk_scientific_campaign_stream_session_id_stream_id_radio_stream",
        "scientific_campaign_stream",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_recording_chunk_session_id_stream_id_radio_stream",
        "recording_chunk",
        type_="foreignkey",
    )
    op.drop_constraint("pk_radio_stream", "radio_stream", type_="primary")
    op.create_primary_key("pk_radio_stream", "radio_stream", ("id",))
    op.create_foreign_key(
        "fk_scientific_campaign_stream_stream_id_radio_stream",
        "scientific_campaign_stream",
        "radio_stream",
        ("stream_id",),
        ("id",),
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_recording_chunk_stream_id_radio_stream",
        "recording_chunk",
        "radio_stream",
        ("stream_id",),
        ("id",),
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_recording_chunk_stream_id_chunk_index",
        "recording_chunk",
        ("stream_id", "chunk_index"),
    )
    op.drop_column("recording_chunk", "session_id")
