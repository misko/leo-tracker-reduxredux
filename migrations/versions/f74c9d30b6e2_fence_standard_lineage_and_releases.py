"""fence Standard derivation lineage and backfill unresolved capture paths

Revision ID: f74c9d30b6e2
Revises: e63b8f41a2c7
Create Date: 2026-08-20 04:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from leo.contracts.digests import canonical_digest

revision: str = "f74c9d30b6e2"
down_revision: str | Sequence[str] | None = "e63b8f41a2c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    streams = bind.execute(
        sa.text(
            "SELECT stream.session_id, stream.id, stream.radio_id, stream.manifest_ordinal, "
            "stream.receiver_ids, stream.sample_rate_hz, stream.captured_sample_count, "
            "stream.state, stream.attributes, radio.serial, radio.uri, radio.transport, "
            "capture.manifest_digest FROM radio_stream stream "
            "JOIN radio ON radio.id=stream.radio_id "
            "JOIN capture_session capture ON capture.id=stream.session_id "
            "ORDER BY stream.session_id, stream.id, stream.radio_id"
        )
    ).mappings()
    for stream in streams:
        manifest_digest = stream["manifest_digest"]
        if manifest_digest is None:
            raise RuntimeError("cannot backfill capture lineage without a manifest digest")
        document = {
            "ordinal": stream["manifest_ordinal"],
            "stream_id": stream["id"],
            "radio": {
                "radio_id": stream["radio_id"],
                "serial": stream["serial"],
                "uri": stream["uri"],
                "transport": stream["transport"],
            },
            "receiver_ids": list(stream["receiver_ids"]),
            "sample_rate_hz": stream["sample_rate_hz"],
            "captured_sample_count": stream["captured_sample_count"],
            "timing": (stream["attributes"] or {}).get("timing"),
            "state": stream["state"],
        }
        for receiver_id in stream["receiver_ids"]:
            bind.execute(
                sa.text(
                    "INSERT INTO capture_receiver_lineage "
                    "(session_id, stream_id, receiver_id, radio_id, radio_serial, "
                    "manifest_digest, stream_identity_digest, lineage_status) VALUES "
                    "(:session_id, :stream_id, :receiver_id, :radio_id, :radio_serial, "
                    ":manifest_digest, :stream_identity_digest, 'unresolved') "
                    "ON CONFLICT (session_id, stream_id, receiver_id) DO NOTHING"
                ),
                {
                    "session_id": stream["session_id"],
                    "stream_id": stream["id"],
                    "receiver_id": receiver_id,
                    "radio_id": stream["radio_id"],
                    "radio_serial": stream["serial"],
                    "manifest_digest": manifest_digest,
                    "stream_identity_digest": canonical_digest(document),
                },
            )

    op.execute(
        """
        CREATE FUNCTION leo_reject_standard_identity_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'authoritative Standard identity is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER stage_derivation_immutable BEFORE UPDATE OR DELETE ON "
        "stage_derivation FOR EACH ROW EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER derivation_product_membership_update_immutable BEFORE UPDATE OF "
        "run_id, stage_key, scope_key, scope_id, kind, schema_version, role, status, "
        "media_type, logical_uri, digest, byte_size, summary, derivation_output_id, "
        "derivation_mode, reused_from_product_id ON analysis_product "
        "FOR EACH ROW WHEN (OLD.derivation_output_id IS NOT NULL OR "
        "NEW.derivation_output_id IS NOT NULL) EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER derivation_product_membership_delete_immutable BEFORE DELETE ON "
        "analysis_product FOR EACH ROW WHEN (OLD.derivation_output_id IS NOT NULL) "
        "EXECUTE FUNCTION leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER authoritative_pipeline_release_update_immutable BEFORE UPDATE OF "
        "id, code_revision, environment_digest, graph_digest, configuration_digest, "
        "executable_digest, authority_version, configuration ON pipeline_release "
        "FOR EACH ROW WHEN (OLD.authority_version = 1 OR NEW.authority_version = 1) "
        "EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )
    op.execute(
        "CREATE TRIGGER authoritative_pipeline_release_delete_immutable BEFORE DELETE ON "
        "pipeline_release FOR EACH ROW WHEN (OLD.authority_version = 1) EXECUTE FUNCTION "
        "leo_reject_standard_identity_mutation()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    authoritative_rows = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM raw_integrity_attestation) OR "
            "EXISTS (SELECT 1 FROM capture_receiver_lineage "
            "WHERE lineage_status='resolved') OR "
            "EXISTS (SELECT 1 FROM stage_derivation) OR "
            "EXISTS (SELECT 1 FROM analysis_product "
            "WHERE derivation_output_id IS NOT NULL) OR "
            "EXISTS (SELECT 1 FROM pipeline_release WHERE authority_version=1)"
        )
    )
    if authoritative_rows:
        raise RuntimeError(
            "cannot downgrade while authoritative typed rows depend on identity fences"
        )
    op.execute("DROP TRIGGER authoritative_pipeline_release_delete_immutable ON pipeline_release")
    op.execute("DROP TRIGGER authoritative_pipeline_release_update_immutable ON pipeline_release")
    op.execute("DROP TRIGGER derivation_product_membership_delete_immutable ON analysis_product")
    op.execute("DROP TRIGGER derivation_product_membership_update_immutable ON analysis_product")
    op.execute("DROP TRIGGER stage_derivation_immutable ON stage_derivation")
    op.execute("DROP FUNCTION leo_reject_standard_identity_mutation()")
