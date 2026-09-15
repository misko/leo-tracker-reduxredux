import pytest

import leo.scanner.adaptive_hop_analysis as detector
from leo.application.adaptive_hop_analysis import HostAdaptiveAnalysisService
from leo.application.adaptive_hop_overview import AdaptiveHopOverviewService
from leo.presentation.adaptive_hop_analysis import render_host_adaptive_hop_overview
from leo.storage.adaptive_hop import AdaptiveHopIqReader, AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisJob, AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.adaptive_hop_history import AdaptiveHopPresentationStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from tests.api.test_adaptive_hop_history_api import client_for
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_host_adaptive_history import publish_native


@pytest.mark.parametrize("receiver", [0, 1])
def test_native_api_history_analysis_and_all_bound_pngs(tmp_path, monkeypatch, receiver):
    capture = publish_native(tmp_path, receiver=receiver)
    history = AdaptiveHopPresentationStore(tmp_path)
    client = client_for(
        tmp_path,
        adaptive_hop_sessions=history,
        adaptive_hop_sessions_v2=history,
        adaptive_hop_analysis=AdaptiveHopAnalysisPresentationStore(tmp_path),
    )
    base = "/api/v2/scanner/adaptive-sessions"
    route = f"{base}/{capture.session_id}"
    assert client.get(base).json() == history.page_v2(cursor=0, limit=20).model_dump(mode="json")
    assert client.get(base.replace("v2", "v3")).json() == client.get(base).json()
    detail = client.get(route)
    assert detail.status_code == 200 and detail.json()["capture"]["physical_receiver"] == receiver
    assert detail.json()["host_decisions"][0]["feedback_disposition"] == "accepted"
    assert client.get(route.replace("v2", "v1")).status_code == 404
    assert client.get(route + "/analysis").json()["state"] == "not_started"
    assert client.get(route.replace("v2", "v1") + "/analysis").status_code == 404
    captures, products = (
        AdaptiveHopIqStore(tmp_path, read_only=True),
        AdaptiveHopAnalysisStore(tmp_path),
    )
    inputs = AdaptiveHopAnalysisInputStore(captures)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    try:
        HostAdaptiveAnalysisService(inputs=inputs, products=products).analyze_session(
            capture.session_id
        )
        AdaptiveHopOverviewService(
            inputs=inputs, products=products, renderer=render_host_adaptive_hop_overview
        ).render_session(capture.session_id)
        monkeypatch.setattr(
            AdaptiveHopIqReader, "read_visit_ci16", lambda *a: pytest.fail("API read IQ")
        )
        monkeypatch.setattr(
            AdaptiveHopAnalysisJob, "_read_visit", lambda *a: pytest.fail("API decoded metrics")
        )
        status = client.get(route + "/analysis")
        assert status.status_code == 200 and status.headers["cache-control"] == "no-store"
        payload = status.json()
        assert payload["schema_version"] == 2 and payload["state"] == "figures_ready"
        assert payload["configuration"]["receiver_ids"] == [receiver]
        for artifact in payload["overview"]["artifacts"]:
            url = route + f"/analysis/{artifact['name']}.png"
            query = {
                "binding_sha256": payload["binding_sha256"],
                "artifact_sha256": artifact["sha256"],
            }
            image = client.get(url, params=query)
            assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
            assert client.head(url, params=query).status_code == 200
            query["artifact_sha256"] = "sha256:" + "0" * 64
            assert client.get(url, params=query).status_code == 409
        for url in (base, route, route + "/analysis"):
            assert client.head(url).status_code == 200 and client.head(url).content == b""
            assert client.post(url).status_code == 405
    finally:
        products.close()
        captures.close()
