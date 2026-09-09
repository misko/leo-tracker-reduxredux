import pytest

import leo.scanner.adaptive_hop_analysis as detector
from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
from leo.application.adaptive_hop_overview import AdaptiveHopOverviewService
from leo.storage.adaptive_hop import AdaptiveHopIqReader, AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisJob, AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from tests.api.test_adaptive_hop_history_api import client_for
from tests.presentation.adaptive_overview_fixtures import rendered_fixture
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_adaptive_hop_history import publish_capture


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_additive_status_progress_and_digest_bound_pngs_without_read_side_analysis(
    monkeypatch, tmp_path, rate, mode
):
    capture = publish_capture(tmp_path, rate=rate, mode=mode, count=3)
    inputs_store = AdaptiveHopIqStore(tmp_path, read_only=True)
    products = AdaptiveHopAnalysisStore(tmp_path)
    inputs = AdaptiveHopAnalysisInputStore(inputs_store)
    client = client_for(
        tmp_path, adaptive_hop_analysis=AdaptiveHopAnalysisPresentationStore(tmp_path)
    )
    route = f"/api/v1/scanner/adaptive-sessions/{capture.session_id}/analysis"
    assert client.get(route).json()["state"] == "not_started"
    assert not (tmp_path / "scanner-adaptive-analysis").exists()
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    service = AdaptiveHopAnalysisService(inputs=inputs, products=products)
    service.analyze_session(capture.session_id, maximum_visits=1)
    response = client.get(route)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["state"] == "partial" and response.json()["checkpoint_visits"] == 1
    service.analyze_session(capture.session_id)
    assert client.get(route).json()["state"] == "metrics_complete"
    AdaptiveHopOverviewService(
        inputs=inputs, products=products, renderer=lambda *args: rendered_fixture()
    ).render_session(capture.session_id)
    monkeypatch.setattr(
        AdaptiveHopIqReader, "read_visit_ci16", lambda *args: pytest.fail("API cannot read IQ")
    )
    monkeypatch.setattr(
        AdaptiveHopAnalysisJob,
        "_read_visit",
        lambda *args: pytest.fail("API cannot decode metrics"),
    )
    monkeypatch.setattr(
        detector, "analyze_glrt64_dwell", lambda *args: pytest.fail("API cannot analyze")
    )
    payload = client.get(route).json()
    assert payload["state"] == "figures_ready" and payload["worker_activity"] == "not_observed"
    for figure in payload["overview"]["artifacts"]:
        url = f"{route}/{figure['name']}.png"
        query = {"binding_sha256": payload["binding_sha256"], "artifact_sha256": figure["sha256"]}
        result = client.get(url, params=query)
        assert (
            result.status_code == 200
            and result.content == rendered_fixture().artifacts[figure["name"]]
        )
        assert result.headers["content-type"] == "image/png"
        assert result.headers["etag"] == f'"{figure["sha256"]}"'
        assert client.head(url, params=query).content == b""
        assert client.post(url, params=query).status_code == 405
        assert (
            client.get(url, params={**query, "binding_sha256": "sha256:" + "9" * 64}).status_code
            == 409
        )
        assert (
            client.get(url, params={**query, "artifact_sha256": "sha256:" + "9" * 64}).status_code
            == 409
        )
    assert client.head(route).content == b"" and client.post(route).status_code == 405
    assert client.get(route, params={"probe_stride_ms": 120}).json()["state"] == "not_started"
    assert client.get(route, params={"probe_stride_ms": 9}).status_code == 422
    assert client.get(route, params={"probe_stride_ms": 121}).status_code == 422
    assert client.get(route.replace(capture.session_id, "bad%20id")).status_code == 422
    assert client.get(route.replace(capture.session_id, "missing")).status_code == 404
    products.close()
    inputs_store.close()


def test_unsupported_and_broken_analysis_are_distinct_and_sanitized(tmp_path):
    route = "/api/v1/scanner/adaptive-sessions/test/analysis"
    assert client_for(tmp_path).get(route).status_code == 404

    class Broken:
        def status(self, *args, **kwargs):
            raise ValueError("private filename and credentials")

        def artifact(self, *args, **kwargs):
            raise ValueError("private filename and credentials")

    client = client_for(tmp_path, adaptive_hop_analysis=Broken())
    query = {"binding_sha256": "sha256:" + "1" * 64, "artifact_sha256": "sha256:" + "2" * 64}
    for url in (route, route + "/coverage.png"):
        response = client.get(url, params=query)
        assert response.status_code == 409 and "private" not in response.text
    assert client.get(route + "/unknown.png", params=query).status_code == 422
