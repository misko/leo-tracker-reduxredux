"""Checkpoint and publication integration for the default phase stage."""

from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
from leo.cli import adaptive_relative_phase as phase
from leo.scanner import adaptive_hop_analysis as detector
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_adaptive_hop_history import publish_capture


def test_phase_resumes_sealed_visits_and_publishes_both_artifacts(tmp_path, monkeypatch):
    capture = publish_capture(tmp_path, count=3)
    total = capture.manifest.receipt.complete_visit_count
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    captures = AdaptiveHopIqStore(tmp_path, read_only=True)
    products = AdaptiveHopAnalysisStore(tmp_path)
    AdaptiveHopAnalysisService(
        inputs=AdaptiveHopAnalysisInputStore(captures), products=products
    ).analyze_session(capture.session_id, probe_stride_ms=120)
    products.close()
    captures.close()
    monkeypatch.setattr(phase, "relative_phase_priority", lambda _: 1.0)
    monkeypatch.setattr(phase, "relative_phase_probes", lambda _: ())
    calls = []

    def extract(*_):
        calls.append(1)
        return {"supported": False, "pilot_held_rms_deg": None}

    monkeypatch.setattr(phase, "extract_relative_phase", extract)
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(phase.time, "monotonic", lambda: next(ticks))
    result = phase.run(tmp_path, capture.session_id, maximum_seconds=1)
    assert result["state"] == "partial" and len(calls) == 1
    monkeypatch.setattr(phase.time, "monotonic", lambda: 0)
    result = phase.run(tmp_path, capture.session_id)
    assert result["state"] == "complete" and len(calls) == total
    assert len(result["manifest"]["artifacts"]) == 2
    assert phase.run(tmp_path, capture.session_id)["state"] == "complete" and len(calls) == total
    status = AdaptiveHopAnalysisPresentationStore(tmp_path).relative_phase_status(
        capture.session_id
    )
    assert status.state == "insufficient_signal"
