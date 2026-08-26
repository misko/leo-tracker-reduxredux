from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text

from leo.application.trusted_campaign_production import (
    TrustedCampaignProductionSettings,
    _require_authoritative_schema,
    open_trusted_campaign_service,
)

from .conftest import CatalogHarness


def test_authoritative_schema_gate_accepts_head_and_rejects_empty_schema(
    catalog_harness: CatalogHarness,
) -> None:
    with catalog_harness.engine.connect() as connection:
        _require_authoritative_schema(connection)

    empty_schema = f"leo_empty_{uuid.uuid4().hex}"
    with catalog_harness.engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{empty_schema}"'))

    with catalog_harness.engine.connect() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{empty_schema}"'))
        with pytest.raises(RuntimeError, match="schema is unavailable"):
            _require_authoritative_schema(connection)

    with catalog_harness.engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{empty_schema}" CASCADE'))


def test_authoritative_schema_gate_rejects_previous_alembic_head(
    catalog_harness: CatalogHarness,
) -> None:
    with catalog_harness.engine.begin() as connection:
        catalog_harness.alembic_config.attributes["connection"] = connection
        command.downgrade(catalog_harness.alembic_config, "b3e91d6f4a20")
        with pytest.raises(RuntimeError, match="authoritative schema head"):
            _require_authoritative_schema(connection)

        command.upgrade(catalog_harness.alembic_config, "head")
        _require_authoritative_schema(connection)
        command.check(catalog_harness.alembic_config)


def test_authoritative_schema_gate_rejects_disabled_authority_trigger(
    catalog_harness: CatalogHarness,
) -> None:
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE scientific_campaign DISABLE TRIGGER "
                "scientific_campaign_authority_version_fence"
            )
        )
        with pytest.raises(RuntimeError, match="authoritative schema head"):
            _require_authoritative_schema(connection)
        connection.execute(
            text(
                "ALTER TABLE scientific_campaign ENABLE TRIGGER "
                "scientific_campaign_authority_version_fence"
            )
        )

    with catalog_harness.engine.connect() as connection:
        _require_authoritative_schema(connection)


def test_factory_checks_deployed_release_before_opening_storage(
    catalog_harness: CatalogHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class MissingReleaseAdapter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def current_release(self) -> None:
            raise ValueError("deployed release is absent")

    class EngineView:
        def __init__(self) -> None:
            self.disposed = False

        def connect(self):  # noqa: ANN202
            return catalog_harness.engine.connect()

        def dispose(self) -> None:
            self.disposed = True

    engine = EngineView()
    monkeypatch.setattr(
        "leo.application.trusted_campaign_production.create_catalog_engine",
        lambda _url: engine,
    )
    monkeypatch.setattr(
        "leo.application.trusted_campaign_production.NativeReleaseCalibrationEvidenceAdapter",
        MissingReleaseAdapter,
    )
    settings = TrustedCampaignProductionSettings(
        database_url="postgresql+psycopg:///unused",
        bulk_root=tmp_path / "absent-bulk",
        qualification_root=tmp_path / "absent-qualification",
        capture_evidence_root=tmp_path / "absent-capture",
        legacy_evidence_root=tmp_path / "absent-legacy",
        pipeline_release_id="missing-release",
    )

    with pytest.raises(ValueError, match="deployed release is absent"):
        open_trusted_campaign_service(settings)

    assert engine.disposed
    assert not any(tmp_path.iterdir())
