from contextlib import contextmanager

import pytest

import leo.application.adaptive_hop_analysis as application
import leo.scanner.adaptive_hop_analysis as detector
from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisSource
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tests.scanner.test_adaptive_hop_analysis import Reader
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_adaptive_hop_history import publish_capture


class Inputs:
    def __init__(self, reader=None):
        self.reader = reader or Reader(count=4)
        self.opened = self.closed = 0

    @contextmanager
    def source(self, session_id):
        self.opened += 1
        try:
            yield AdaptiveHopAnalysisSource(self.reader)
        finally:
            self.closed += 1


def service(monkeypatch, tmp_path, *, clock=lambda: 0):
    inputs = Inputs()
    products = AdaptiveHopAnalysisStore(tmp_path)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    return (
        inputs,
        products,
        AdaptiveHopAnalysisService(inputs=inputs, products=products, clock=clock),
    )


def test_budgeted_resume_reads_only_missing_visits_and_always_closes(monkeypatch, tmp_path):
    inputs, products, worker = service(monkeypatch, tmp_path)
    session_id = inputs.reader.session_id
    first = worker.analyze_session(session_id, maximum_visits=1)
    assert first.state == "partial" and first.stop_reason == "visit_budget"
    assert first.total_visits == 3 and first.completed_visits == first.newly_analyzed_visits == 1
    assert inputs.reader.calls == [0] and inputs.closed == inputs.opened == 1
    second = worker.analyze_session(session_id)
    assert second.state == "metrics_complete" and second.completed_visits == 3
    assert second.newly_analyzed_visits == 2 and inputs.reader.calls == [0, 1, 2]
    third = worker.analyze_session(session_id)
    assert third.newly_analyzed_visits == 0 and third.binding_sha256 == first.binding_sha256
    assert inputs.reader.calls == [0, 1, 2] and inputs.closed == inputs.opened == 3
    products.close()


def test_failure_preserves_completed_science_and_releases_worker(monkeypatch, tmp_path):
    inputs, products, worker = service(monkeypatch, tmp_path)
    real = application.analyze_adaptive_hop_visit

    def fail(source, index, *, configuration):
        if index == 1:
            raise RuntimeError("injected detector failure")
        return real(source, index, configuration=configuration)

    monkeypatch.setattr(application, "analyze_adaptive_hop_visit", fail)
    with pytest.raises(RuntimeError, match="injected"):
        worker.analyze_session(inputs.reader.session_id)
    assert inputs.reader.calls == [0] and inputs.closed == 1
    monkeypatch.setattr(application, "analyze_adaptive_hop_visit", real)
    result = worker.analyze_session(inputs.reader.session_id)
    assert result.newly_analyzed_visits == 2 and result.state == "metrics_complete"
    assert inputs.reader.calls == [0, 1, 2]
    products.close()


@pytest.mark.parametrize("reason", ["cancelled", "time_budget"])
def test_cancel_or_time_budget_never_truncates_or_reads_next_dwell(monkeypatch, tmp_path, reason):
    clock_values = iter([0, 0, 301])
    inputs, products, worker = service(
        monkeypatch,
        tmp_path,
        clock=(lambda: next(clock_values)) if reason == "time_budget" else lambda: 0,
    )
    result = worker.analyze_session(
        inputs.reader.session_id,
        cancelled=lambda: reason == "cancelled" and bool(inputs.reader.calls),
    )
    assert result.stop_reason == reason and result.state == "partial"
    assert result.newly_analyzed_visits == 1 and inputs.reader.calls == [0]
    products.close()


@pytest.mark.parametrize(
    "options",
    [
        {"maximum_visits": 0},
        {"maximum_visits": True},
        {"maximum_visits": 2501},
        {"maximum_seconds": float("nan")},
        {"maximum_seconds": True},
        {"maximum_seconds": 1801},
        {"probe_stride_ms": 9},
    ],
)
def test_invalid_budget_is_rejected_before_inputs_or_output(monkeypatch, tmp_path, options):
    inputs, products, worker = service(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        worker.analyze_session(inputs.reader.session_id, **options)
    assert not inputs.opened and list(tmp_path.iterdir()) == []
    products.close()


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_real_stored_synthetic_iq_to_checkpointed_dense_metrics(monkeypatch, tmp_path, rate, mode):
    capture = publish_capture(tmp_path, rate=rate, mode=mode, count=3)
    captures = AdaptiveHopIqStore(tmp_path, read_only=True)
    products = AdaptiveHopAnalysisStore(tmp_path)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    worker = AdaptiveHopAnalysisService(
        inputs=AdaptiveHopAnalysisInputStore(captures), products=products
    )
    first = worker.analyze_session(capture.session_id, maximum_visits=1)
    assert first.state == "partial"
    second = worker.analyze_session(capture.session_id)
    assert second.state == "metrics_complete" and second.newly_analyzed_visits == 1
    assert captures.verify(capture.session_id).manifest_sha256 == capture.manifest_sha256
    products.close()
    captures.close()
