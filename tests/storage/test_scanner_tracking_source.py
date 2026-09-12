from dataclasses import replace
from types import SimpleNamespace

import pytest

import leo.scanner.adaptive_hop_analysis as detector
from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
from leo.application.persistent_hop_trajectory import (
    PersistentHopTrajectoryProjectionConfig,
    project_fractional_persistent_hop_candidates,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from tests.application.test_persistent_hop_trajectory import _chunk, _one_visit_manifest
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_adaptive_hop_history import publish_capture


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_fixed_adapter_retains_legacy_numerical_projection(tmp_path, rate):
    capture = _one_visit_manifest(tmp_path, rate=rate)
    chunk = _chunk(capture)
    reader = ScannerTrackingInputStore(tmp_path)
    reader.fixed_analysis = SimpleNamespace(
        inspect=lambda _: SimpleNamespace(
            manifest=SimpleNamespace(input_manifest_sha256=capture.manifest_sha256),
            manifest_sha256=capture.manifest_sha256,
        ),
        published_chunks=lambda _: (chunk,),
    )
    source = reader.load(capture.session_id)
    assert source.sample_rate_hz == rate and source.capture_mode == "fixed"
    assert (
        not source.qualified
    )  # This deliberately cancelled fixture remains ineligible in production.
    actual = project_scanner_candidates(replace(source, qualified=True))
    expected = project_fractional_persistent_hop_candidates(
        capture.manifest,
        (chunk,),
        input_manifest_sha256=capture.manifest_sha256,
        config=PersistentHopTrajectoryProjectionConfig(require_complete_capture=False),
    ).candidates
    assert len(actual) == len(expected)
    for a, b in zip(actual, expected, strict=True):
        assert a.measured_cfo_hz == b.measured_cfo_hz
        assert a.factorial_support_moments_s == b.factorial_support_moments_s
        assert a.support_center_utc_ns == b.support_center_utc_ns
        assert a.source_sample_start == b.source_sample_start
        assert a.source_sample_end == b.source_sample_end
    reader.close()


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_adaptive_adapter_reads_verified_metrics_and_actual_counters(tmp_path, monkeypatch, rate):
    capture = publish_capture(tmp_path, rate=rate, count=4)
    captures = AdaptiveHopIqStore(tmp_path, read_only=True)
    products = AdaptiveHopAnalysisStore(tmp_path)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    result = AdaptiveHopAnalysisService(
        inputs=AdaptiveHopAnalysisInputStore(captures), products=products
    ).analyze_session(capture.session_id, probe_stride_ms=120)
    assert result.state == "metrics_complete"
    reader = ScannerTrackingInputStore(tmp_path)
    source = reader.load(capture.session_id)
    assert source.sample_rate_hz == rate and source.capture_mode == "adaptive"
    assert len(source.probes) == capture.manifest.receipt.complete_visit_count * 2
    for probe in source.probes:
        event = capture.manifest.receipt.events[probe.visit_index]
        assert probe.valid_start_counter == event.valid_start_counter
        assert probe.actual_rf_hz == event.target.rf_center_hz - event.actual_if_offset_hz
    reader.close()
    products.close()
    captures.close()
