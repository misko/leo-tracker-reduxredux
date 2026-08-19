from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect, text

from leo.catalog import CatalogNotFoundError
from leo.catalog.models import Base

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
