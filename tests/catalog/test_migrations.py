from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text

from leo.catalog import CatalogNotFoundError
from leo.catalog.models import Base
from leo.contracts.digests import canonical_digest

from .conftest import CatalogHarness


def test_empty_schema_upgrades_to_single_head_without_model_drift(
    catalog_harness: CatalogHarness,
) -> None:
    inspector = inspect(catalog_harness.engine)

    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.check(catalog_harness.alembic_config)


def test_previous_head_upgrades_without_changing_existing_catalog_rows(
    catalog_harness: CatalogHarness,
) -> None:
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.downgrade(catalog_harness.alembic_config, "a8d4c2e91b70")
        connection.execute(
            text(
                "INSERT INTO pipeline_release "
                "(id, code_revision, environment_digest, graph_digest) "
                "VALUES ('pre-campaign', 'code', :digest, :digest)"
            ),
            {"digest": "sha256:" + "a" * 64},
        )
        command.upgrade(catalog_harness.alembic_config, "head")
        assert (
            connection.execute(
                text("SELECT code_revision FROM pipeline_release WHERE id = 'pre-campaign'")
            ).scalar_one()
            == "code"
        )
        command.check(catalog_harness.alembic_config)


def test_populated_previous_head_upgrades_legacy_jobs_and_products_safely(
    catalog_harness: CatalogHarness,
) -> None:
    digest = "sha256:" + "a" * 64
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.downgrade(catalog_harness.alembic_config, "b91e2c4d7a10")
        connection.execute(
            text(
                "INSERT INTO capture_session "
                "(id, source_type, state, bundle_uri, manifest_digest) VALUES "
                "('foundation-old', 'live', 'committed', "
                "'bulk://recordings/foundation-old', :digest)"
            ),
            {"digest": digest},
        )
        connection.execute(
            text(
                "INSERT INTO pipeline_release "
                "(id, code_revision, environment_digest, graph_digest) VALUES "
                "('foundation-old-release', 'old-code', :digest, :digest)"
            ),
            {"digest": digest},
        )
        connection.execute(
            text(
                "INSERT INTO analysis_run "
                "(id, session_id, pipeline_release_id, trigger, state, "
                "input_manifest_digest) VALUES "
                "('foundation-old-run', 'foundation-old', 'foundation-old-release', "
                "'automatic', 'running', :digest)"
            ),
            {"digest": digest},
        )
        connection.execute(
            text(
                "INSERT INTO processing_job "
                "(run_id, stage_key, scope_key, priority, state, attempt_count, max_attempts) "
                "VALUES ('foundation-old-run', 'quality', 'stream-0', 0, 'pending', 0, 3)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_product "
                "(run_id, stage_key, scope_key, kind, schema_version, role, status, "
                "media_type, logical_uri, digest, byte_size) VALUES "
                "('foundation-old-run', 'quality', 'stream-0', 'quality.summary', 1, "
                "'scientific', 'complete', 'application/json', 'bulk://old/product', "
                ":digest, 10)"
            ),
            {"digest": digest},
        )

        command.upgrade(catalog_harness.alembic_config, "head")
        assert connection.execute(
            text(
                "SELECT node_id, scope_id, resource_class, iq_access "
                "FROM processing_job WHERE run_id='foundation-old-run'"
            )
        ).one() == (None, None, "streaming", "legacy")
        assert connection.execute(
            text(
                "SELECT scope_id, derivation_output_id, derivation_mode "
                "FROM analysis_product WHERE run_id='foundation-old-run'"
            )
        ).one() == (None, None, "legacy")
        assert connection.scalar(
            text(
                "SELECT configuration_digest FROM pipeline_release "
                "WHERE id='foundation-old-release'"
            )
        ) == canonical_digest({})
        command.check(catalog_harness.alembic_config)


def test_standard_authority_downgrade_refuses_typed_rows(
    catalog_harness: CatalogHarness,
) -> None:
    digest = "sha256:" + "a" * 64
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO capture_session "
                "(id, source_type, state, bundle_uri, manifest_digest) VALUES "
                "('typed-downgrade', 'test', 'committed', "
                "'bulk://recordings/typed-downgrade', :digest)"
            ),
            {"digest": digest},
        )
        connection.execute(
            text(
                "INSERT INTO raw_integrity_attestation "
                "(session_id, manifest_digest, attestation_digest, document, verified_at) "
                "VALUES ('typed-downgrade', :digest, :digest_b, '{}'::jsonb, now())"
            ),
            {"digest": digest, "digest_b": "sha256:" + "b" * 64},
        )
        catalog_harness.alembic_config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="authoritative typed rows"):
            command.downgrade(catalog_harness.alembic_config, "d52a7f24c8e1")


def test_populated_immediate_previous_head_backfills_role_and_quarantines_release(
    catalog_harness: CatalogHarness,
) -> None:
    digest = "sha256:" + "a" * 64
    configuration = {"stages": {"stage": {"window": 64}}}
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.downgrade(catalog_harness.alembic_config, "d52a7f24c8e1")
        connection.execute(
            text(
                "INSERT INTO capture_session "
                "(id, source_type, state, bundle_uri, manifest_digest) VALUES "
                "('previous-head', 'test', 'committed', "
                "'bulk://recordings/previous-head', :digest)"
            ),
            {"digest": digest},
        )
        connection.execute(
            text(
                "INSERT INTO pipeline_release "
                "(id, code_revision, environment_digest, graph_digest, configuration) VALUES "
                "('previous-release', 'legacy-code', :digest, :digest, CAST(:config AS jsonb))"
            ),
            {"digest": digest, "config": '{"stages":{"stage":{"window":64}}}'},
        )
        connection.execute(
            text(
                "INSERT INTO analysis_run "
                "(id, session_id, pipeline_release_id, trigger, state, input_manifest_digest) "
                "VALUES ('previous-run', 'previous-head', 'previous-release', "
                "'reprocess', 'running', :digest)"
            ),
            {"digest": digest},
        )
        derivation_id = connection.scalar(
            text(
                "INSERT INTO stage_derivation "
                "(derivation_key, stage_key, algorithm_version, implementation_digest, "
                "configuration_digest, environment_digest, scope_digest, "
                "input_closure_digest, key_document, producing_release_id) VALUES "
                "(:digest, 'stage', '1', :digest, :digest, :digest, :digest, :digest, "
                "'{}'::jsonb, 'previous-release') RETURNING id"
            ),
            {"digest": digest},
        )
        output_id = connection.scalar(
            text(
                "INSERT INTO stage_derivation_output "
                "(derivation_id, kind, schema_version, status, media_type, logical_uri, "
                "digest, byte_size) VALUES (:derivation, 'stage.output', 1, 'complete', "
                "'application/json', 'bulk://previous/output', :digest, 10) RETURNING id"
            ),
            {"derivation": derivation_id, "digest": digest},
        )
        connection.execute(
            text(
                "INSERT INTO analysis_product "
                "(run_id, stage_key, scope_key, kind, schema_version, role, status, "
                "media_type, logical_uri, digest, byte_size, derivation_output_id, "
                "derivation_mode) VALUES ('previous-run', 'stage', 'legacy-scope', "
                "'stage.output', 1, 'scientific', 'complete', 'application/json', "
                "'bulk://previous/output', :digest, 10, :output, 'computed')"
            ),
            {"digest": digest, "output": output_id},
        )

        command.upgrade(catalog_harness.alembic_config, "head")

        assert connection.execute(
            text(
                "SELECT role FROM stage_derivation_output WHERE id=:output"
            ),
            {"output": output_id},
        ).scalar_one() == "scientific"
        assert connection.execute(
            text(
                "SELECT authority_version, configuration_digest FROM pipeline_release "
                "WHERE id='previous-release'"
            )
        ).one() == (0, canonical_digest(configuration))
        command.check(catalog_harness.alembic_config)


def test_legacy_campaign_is_quarantined_and_new_seal_requires_outer_authority(
    catalog_harness: CatalogHarness,
) -> None:
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.downgrade(catalog_harness.alembic_config, "f62a9d174be1")
        digest = "sha256:" + "a" * 64
        connection.execute(
            text(
                "INSERT INTO scientific_campaign "
                "(id, state, capture_uri, capture_digest, scientific_uri, "
                "scientific_digest, presentation_uri, presentation_digest, "
                "result_status, sealed_at) VALUES "
                "('legacy-sealed', 'sealed', 'bulk://legacy/capture', :digest, "
                "'bulk://legacy/science', :digest, 'bulk://legacy/presentation', "
                ":digest, 'pass', now())"
            ),
            {"digest": digest},
        )
        command.upgrade(catalog_harness.alembic_config, "head")
        assert connection.execute(
            text(
                "SELECT seal_authority_version, outer_seal_uri FROM scientific_campaign "
                "WHERE id = 'legacy-sealed'"
            )
        ).one() == (0, None)
        with (
            pytest.raises(Exception, match="reserved for migrated legacy rows"),
            connection.begin_nested(),
        ):
            connection.execute(
                text(
                    "INSERT INTO scientific_campaign "
                    "(id, capture_uri, capture_digest, seal_authority_version) "
                    "VALUES ('forged-legacy', 'bulk://forged/capture', :digest, 0)"
                ),
                {"digest": digest},
            )
        connection.execute(
            text(
                "INSERT INTO scientific_campaign (id, capture_uri, capture_digest) "
                "VALUES ('new-campaign', 'bulk://new/capture', :digest)"
            ),
            {"digest": digest},
        )
        with pytest.raises(Exception, match="outer_seal_authority"), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE scientific_campaign SET state='sealed', sealed_at=now(), "
                    "scientific_uri='bulk://new/science', scientific_digest=:digest, "
                    "presentation_uri='bulk://new/presentation', "
                    "presentation_digest=:digest, result_status='pass' "
                    "WHERE id='new-campaign'"
                ),
                {"digest": digest},
            )


def test_populated_authoritative_calibration_head_upgrades(
    catalog_harness: CatalogHarness,
) -> None:
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.downgrade(catalog_harness.alembic_config, "e4b17c8d93af")
        statements = (
            "INSERT INTO radio (id, serial, uri, transport) "
            "VALUES ('radio-upgrade', 'serial-upgrade', 'ip:test', 'ethernet')",
            "INSERT INTO receiver_path "
            "(radio_id, receiver_id, physical_receiver_id, attributes) "
            "VALUES ('radio-upgrade', 1, 'physical-upgrade', '{}'::jsonb)",
            "INSERT INTO hardware_epoch (external_id, radio_id, started_at) "
            "VALUES ('epoch-upgrade', 'radio-upgrade', "
            "'2026-08-19 00:00:00.123456+00')",
            "INSERT INTO frequency_calibration "
            "(external_id, receiver_path_id, hardware_epoch_id, center_offset_hz, "
            "valid_from, calibration_digest, evidence) "
            "SELECT 'cal-upgrade', receiver_path.id, hardware_epoch.id, 0, "
            "'2026-08-19 00:00:00.123456+00', :digest, '[]'::jsonb "
            "FROM receiver_path, hardware_epoch "
            "WHERE receiver_path.physical_receiver_id = 'physical-upgrade' "
            "AND hardware_epoch.external_id = 'epoch-upgrade'",
            "INSERT INTO frequency_calibration_set "
            "(id, digest, evidence_uri, evidence_digest) "
            "VALUES ('set-upgrade', :digest_b, 'bulk://upgrade/set', :digest_b)",
            "INSERT INTO frequency_calibration_set_member "
            "(set_id, calibration_id, ordinal) "
            "SELECT 'set-upgrade', id, 0 FROM frequency_calibration "
            "WHERE external_id = 'cal-upgrade'",
        )
        parameters = {
            "digest": "sha256:" + "a" * 64,
            "digest_b": "sha256:" + "b" * 64,
        }
        for statement in statements:
            connection.execute(text(statement), parameters)
        command.upgrade(catalog_harness.alembic_config, "head")
        row = connection.execute(
            text(
                "SELECT hardware_epoch.started_utc_ns, frequency_calibration_set.sealed_at, "
                "frequency_calibration_set.promotion_id, "
                "frequency_calibration_set.sealed_utc_ns "
                "FROM hardware_epoch CROSS JOIN frequency_calibration_set "
                "WHERE hardware_epoch.external_id = 'epoch-upgrade' "
                "AND frequency_calibration_set.id = 'set-upgrade'"
            )
        ).one()
        assert row.started_utc_ns == 1_787_097_600_123_456_000
        assert row.sealed_at is not None
        assert row.promotion_id is None
        assert row.sealed_utc_ns is None
        command.check(catalog_harness.alembic_config)
    with pytest.raises(CatalogNotFoundError, match="sealed calibration promotion is absent"):
        catalog_harness.repository.frequency_calibration_set_by_promotion_id("set-upgrade")


def test_populated_previous_head_scopes_stream_and_chunk_identity(
    catalog_harness: CatalogHarness,
) -> None:
    digest = "sha256:" + "a" * 64
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.downgrade(catalog_harness.alembic_config, "a73c4e19d2f0")
        connection.execute(
            text(
                "INSERT INTO radio (id, serial, uri, transport) "
                "VALUES ('migration-radio', 'migration-serial', 'ip:test', 'ethernet')"
            )
        )
        for session_id, stream_id in (("migration-a", "stream-0"), ("migration-b", "stream-1")):
            connection.execute(
                text(
                    "INSERT INTO capture_session "
                    "(id, source_type, state, bundle_uri, manifest_digest) "
                    "VALUES (:session, 'live', 'committed', :uri, :digest)"
                ),
                {"session": session_id, "uri": f"bulk://recordings/{session_id}", "digest": digest},
            )
            connection.execute(
                text(
                    "INSERT INTO radio_stream "
                    "(id, session_id, radio_id, state, receiver_ids, sample_rate_hz, "
                    "captured_sample_count) VALUES "
                    "(:stream, :session, 'migration-radio', 'complete', ARRAY[1], 2500000, 8)"
                ),
                {"stream": stream_id, "session": session_id},
            )
            connection.execute(
                text(
                    "INSERT INTO recording_chunk "
                    "(stream_id, chunk_index, sample_start, sample_count, logical_uri, "
                    "compressed_digest, uncompressed_digest, compressed_bytes, "
                    "uncompressed_bytes) VALUES "
                    "(:stream, 0, 0, 8, :uri, :digest, :digest, 10, 32)"
                ),
                {
                    "stream": stream_id,
                    "uri": f"bulk://recordings/{session_id}/0.zst",
                    "digest": digest,
                },
            )

        command.upgrade(catalog_harness.alembic_config, "head")
        assert connection.execute(
            text("SELECT session_id, stream_id FROM recording_chunk ORDER BY session_id")
        ).all() == [("migration-a", "stream-0"), ("migration-b", "stream-1")]
        connection.execute(
            text(
                "INSERT INTO capture_session "
                "(id, source_type, state, bundle_uri, manifest_digest) VALUES "
                "('migration-c', 'live', 'committed', 'bulk://recordings/migration-c', :digest)"
            ),
            {"digest": digest},
        )
        connection.execute(
            text(
                "INSERT INTO radio_stream "
                "(id, session_id, radio_id, state, receiver_ids, sample_rate_hz, "
                "captured_sample_count) VALUES "
                "('stream-0', 'migration-c', 'migration-radio', 'complete', ARRAY[1], 2500000, 8)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO recording_chunk "
                "(session_id, stream_id, chunk_index, sample_start, sample_count, logical_uri, "
                "compressed_digest, uncompressed_digest, compressed_bytes, uncompressed_bytes) "
                "VALUES ('migration-c', 'stream-0', 0, 0, 8, "
                "'bulk://recordings/migration-c/repeated.zst', :digest, :digest, 10, 32)"
            ),
            {"digest": digest},
        )
        command.check(catalog_harness.alembic_config)
