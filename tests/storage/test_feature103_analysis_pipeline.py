from pathlib import Path

import numpy as np
import pytest

from leo.scanner.adaptive_hop import AdaptiveHopPlanV4, AdaptiveHopPolicyV2, AdaptiveHopReceiptV4
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
from leo.scanner.dual_rx import compile_dual_rx_adaptive_10m_hop_plan
from leo.scanner.persistent_hop import Feature103DualRxTimingV3
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_history import AdaptiveHopPresentationStore
from tests.scanner.adaptive_hop_fixtures import receipt_fixture, timing_fixture
from tests.scanner.test_dual_rx_profile import make_10m_intent


def publish_feature103(root: Path):
    from leo.station.geometry import AdaptiveReceiverGeometryBindingV1, StationReceiverGeometryV1

    geometry_path = (
        Path(__file__).parents[2] / "deploy/station/gauss-r21-lt3d-001a-20260920-v1.json"
    )
    station = StationReceiverGeometryV1.model_validate_json(geometry_path.read_bytes())
    binding = AdaptiveReceiverGeometryBindingV1.create(
        station, radio_id="radio_pluto_19f2", radio_serial="10400056f695001322002d0010ad1719f2"
    )
    geometry = compile_dual_rx_adaptive_10m_hop_plan(make_10m_intent()).model_dump()
    geometry.update(schema_version=3, transition_guard_samples=0)
    plan = AdaptiveHopPlanV4.model_validate(
        dict(
            geometry=geometry,
            policy=AdaptiveHopPolicyV2(mode="adaptive", generation=71, allowed_target_mask=15),
        )
    )

    def receipt_model(**values):
        values["events"] = [e.model_dump() | {"schema_version": 2} for e in values["events"]]
        return AdaptiveHopReceiptV4(**values)

    from leo.scanner.adaptive_hop import AdaptiveHopEventV2

    def zero_gap_event(**values):
        values["transition_before_counter"] = values["invalid_start_counter"]
        return AdaptiveHopEventV2(**values)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("tests.scanner.adaptive_hop_fixtures.AdaptiveHopEventV1", zero_gap_event)
        receipt = receipt_fixture(
            plan=plan,
            count=3,
            transition_samples=0,
            receipt_factory=receipt_model,
            radio_id=binding.radio.radio_id,
            radio_serial=binding.radio.radio_serial,
        )
    store = AdaptiveHopIqStore(root)
    try:
        writer = store.begin(receipt.session_id, plan, receiver_geometry=binding)
        for i in range(receipt.complete_visit_count):
            visit = receipt.visits[i]
            samples = np.ones((visit.valid_sample_count, 2), np.complex64)
            writer.append(AdaptiveHopVisitBlock(samples, (0, 1), visit))
        return writer.finish(receipt, timing=timing_fixture(receipt, Feature103DualRxTimingV3))
    finally:
        store.close()


def test_zero_gap_10m_history_metrics_resume_overview_and_api(tmp_path, monkeypatch):
    import leo.scanner.adaptive_hop_analysis as detector
    from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
    from leo.application.adaptive_hop_overview import AdaptiveHopOverviewService
    from leo.cli.adaptive_hop_analysis import _render_overview
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
    from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
    from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
    from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell

    capture = publish_feature103(tmp_path)
    history = AdaptiveHopPresentationStore(tmp_path)
    page = history.page_v2(cursor=0, limit=5)
    assert page.schema_version == 5 and page.items[0].schema_version == 6
    detail = history.detail_v2(capture.session_id)
    assert detail.capture.sample_rate_hz == 10_000_000
    assert detail.visits[0].invalid_start_seconds == detail.visits[0].valid_start_seconds
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    captures = AdaptiveHopIqStore(tmp_path, read_only=True)
    products = AdaptiveHopAnalysisStore(tmp_path)
    try:
        inputs = AdaptiveHopAnalysisInputStore(captures)
        service = AdaptiveHopAnalysisService(inputs=inputs, products=products)
        result = service.analyze_session(
            capture.session_id, maximum_visits=1, maximum_seconds=30, probe_stride_ms=120
        )
        assert result.state == "partial"
        result = service.analyze_session(
            capture.session_id, maximum_visits=3, maximum_seconds=30, probe_stride_ms=120
        )
        assert result.state == "metrics_complete"
        overview = AdaptiveHopOverviewService(
            inputs=inputs, products=products, renderer=_render_overview
        ).render_session(capture.session_id, probe_stride_ms=120)
        assert overview.schema_version == 6
    finally:
        products.close()
        captures.close()
    status = AdaptiveHopAnalysisPresentationStore(tmp_path).status(
        capture.session_id, probe_stride_ms=120
    )
    assert status.schema_version == 6 and status.configuration.schema_version == 3
    assert status.state == "figures_ready"
    from leo.cli.adaptive_relative_phase import run

    phase = run(tmp_path, capture.session_id, maximum_seconds=30)
    assert phase["state"] == "complete"
    assert phase["manifest"]["receiver_geometry_digest"] is not None
    from tests.api.test_adaptive_hop_history_api import client_for

    client = client_for(
        tmp_path,
        adaptive_hop_sessions_v2=history,
        adaptive_hop_analysis=AdaptiveHopAnalysisPresentationStore(tmp_path),
    )
    base = f"/api/v3/scanner/adaptive-sessions/{capture.session_id}"
    assert client.get("/api/v3/scanner/adaptive-sessions?limit=5").status_code == 200
    assert client.get(base).json()["schema_version"] == 6
    response = client.get(base + "/analysis?probe_stride_ms=120")
    assert response.status_code == 200
    assert response.json()["configuration"]["schema_version"] == 3
    route = f"/api/v1/scanner/adaptive-sessions/{capture.session_id}/analysis/relative-phase"
    manifest = client.get(route).json()["manifest"]
    for artifact in manifest["artifacts"]:
        response = client.get(
            route + "/" + artifact["name"] + ".png",
            params=dict(
                binding_sha256=manifest["binding_sha256"], artifact_sha256=artifact["sha256"]
            ),
        )
        assert response.status_code == 200 and response.content.startswith(b"\x89PNG\r\n\x1a\n")
