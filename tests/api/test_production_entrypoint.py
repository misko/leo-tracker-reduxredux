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

    import leo.scanner.adaptive_hop_analysis as detector
    from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
    from leo.application.adaptive_hop_overview import AdaptiveHopOverviewService
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
    from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
    from leo.storage.scanner_glrt import ScannerGlrtStore
    from tests.presentation.adaptive_overview_fixtures import rendered_fixture
    from tests.scanner.adaptive_glrt_publication_fixtures import publication_fixture
    from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
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
        route = f"{base}/{capture.session_id}/analysis"
        assert client.get(route).json()["state"] == "not_started"
        captures = AdaptiveHopIqStore(tmp_path, read_only=True)
        products = AdaptiveHopAnalysisStore(tmp_path)
        inputs = AdaptiveHopAnalysisInputStore(captures)
        monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
        try:
            AdaptiveHopAnalysisService(inputs=inputs, products=products).analyze_session(
                capture.session_id
            )
            assert client.get(route).json()["state"] == "metrics_complete"
            AdaptiveHopOverviewService(
                inputs=inputs, products=products, renderer=lambda *args: rendered_fixture()
            ).render_session(capture.session_id)
        finally:
            products.close()
            captures.close()
        current = client.get(route).json()
        assert current["state"] == "figures_ready"
        figure = current["overview"]["artifacts"][0]
        response = client.get(
            route + "/coverage.png",
            params={
                "binding_sha256": current["binding_sha256"],
                "artifact_sha256": figure["sha256"],
            },
        )
        assert (
            response.status_code == 200
            and response.content == rendered_fixture().artifacts["coverage"]
        )
        # Original history contract is unchanged; analysis is a new independent port.
        assert (
            client.get(f"{base}/{capture.session_id}").json()["capture"]["analysis_state"]
            == "not_integrated"
        )
