from __future__ import annotations

import sys
from pathlib import Path

import pytest

from leo.api import production


def test_api_entrypoint_check_validates_settings_without_starting_server(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(sys, "argv", ["leo-api", "--check"])

    def unexpected_run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("entrypoint check must not start uvicorn")

    monkeypatch.setattr(production.uvicorn, "run", unexpected_run)
    production.main()

    assert capsys.readouterr().out.startswith("leo-api entrypoint ok:")


def test_production_composition_rejects_qnap_before_database_or_filesystem_writes(
    monkeypatch,
) -> None:
    def unexpected_engine(_url):
        raise AssertionError("QNAP rejection must precede database composition")

    monkeypatch.setattr(production, "create_catalog_engine", unexpected_engine)
    with pytest.raises(ValueError, match="absolute local storage"):
        production.create_production_app(
            production.ProductionSettings(
                database_url="postgresql+psycopg:///unused",
                bulk_root=Path("/mnt/qnap01/leo-api-forbidden"),
                qualification_root=Path("/mnt/qnap01/leo-api-forbidden/qualification"),
            )
        )


def test_production_adaptive_routes_discover_new_publications_without_database_or_restart(
    tmp_path,
    monkeypatch,
):
    from fastapi.testclient import TestClient
    from sqlalchemy import event

    from leo.storage.scanner_glrt import ScannerGlrtStore
    from tests.scanner.adaptive_glrt_publication_fixtures import publication_fixture
    from tests.storage.test_adaptive_hop_history import publish_capture

    original_engine = production.create_catalog_engine

    def disconnected_engine(url):
        engine = original_engine(url)

        @event.listens_for(engine, "do_connect")
        def refuse_connection(*args, **kwargs):
            raise AssertionError("adaptive history must not open PostgreSQL")

        return engine

    monkeypatch.setattr(production, "create_catalog_engine", disconnected_engine)
    (tmp_path / "qualification" / "trusted-campaigns").mkdir(parents=True)
    (tmp_path / "recordings").mkdir()
    static = tmp_path / "web"
    static.mkdir()
    app = production.create_production_app(
        production.ProductionSettings(
            database_url="postgresql+psycopg://unused@127.0.0.1:1/unused",
            bulk_root=tmp_path,
            static_directory=static,
            tle_root=tmp_path / "tle",
        )
    )
    with TestClient(app) as client:
        base = "/api/v1/scanner/adaptive-sessions"
        assert client.get(base).json()["total"] == 0
        assert not (tmp_path / "scanner-adaptive-recordings").exists()
        capture = publish_capture(tmp_path, count=3)
        publication = publication_fixture(capture.manifest.receipt, capture.manifest_sha256)
        ScannerGlrtStore(tmp_path).publish(publication)
        assert client.get(base).json()["total"] == 1
        assert client.get(f"{base}/{capture.session_id}").json()["capture"]["retained_visits"] == 2
        assert client.get(f"{base}/{capture.session_id}/glrt").json() == publication.model_dump(
            mode="json"
        )
