from dataclasses import replace

import pytest

import leo.scanner.adaptive_hop_analysis as detector
from leo.application.adaptive_hop_analysis import HostAdaptiveAnalysisService
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.scanner.single_rx import SingleRxHopTimingV2
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.scanner_refinement_source import comparison_source
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from tests.scanner.adaptive_hop_fixtures import timing_fixture
from tests.scanner.host_adaptive_fixtures import host_receipt
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_host_adaptive_hop_store import block


@pytest.mark.parametrize("receiver", [0, 1])
def test_native_adaptive_refinement_and_tracking_use_actual_rx_and_clock(
    tmp_path, monkeypatch, receiver
):
    receipt = host_receipt(receiver=receiver, count=5)
    captures, products = AdaptiveHopIqStore(tmp_path), AdaptiveHopAnalysisStore(tmp_path)
    writer = captures.begin(receipt.session_id, receipt.plan)
    try:
        for i in range(receipt.complete_visit_count):
            writer.append(block(receipt, i))
        published = writer.finish(receipt, timing=timing_fixture(receipt, SingleRxHopTimingV2))
        with comparison_source(tmp_path, receipt.session_id) as source:
            assert source.sample_rate_hz == 10_000_000 and source.session_kind == "adaptive"
            assert source.input_manifest_sha256 == published.manifest_sha256
            assert len(source.probe_ids) == 4
            for key in source.probe_ids:
                probe = source.read_probe(key)
                event = receipt.events[probe.visit_index]
                assert probe.receiver_id == receiver and probe.target_index == event.target_index
                assert len(probe.samples) == 210_000
                assert probe.samples[1] == (probe.visit_index + 1) - 32768j
                assert (
                    probe.time_s
                    == (event.valid_start_counter - receipt.terminal.first_counter) / 10_000_000
                )
        monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
        result = HostAdaptiveAnalysisService(
            inputs=AdaptiveHopAnalysisInputStore(captures),
            products=products,
        ).analyze_session(receipt.session_id, probe_stride_ms=120, maximum_workers=4)
        assert result.state == "metrics_complete"
        reader = ScannerTrackingInputStore(tmp_path)
        try:
            source = reader.load(receipt.session_id)
            assert source.sample_rate_hz == 10_000_000 and source.capture_mode == "adaptive"
            assert len(source.probes) == 4
            assert not source.qualified  # Deliberately cancelled synthetic capture.
            for probe in source.probes:
                assert probe.receiver_id == receiver
                assert (
                    probe.valid_start_counter
                    == receipt.events[probe.visit_index].valid_start_counter
                )
            projected = project_scanner_candidates(replace(source, qualified=True))
            assert projected and all(c.receiver_id == receiver for c in projected)
        finally:
            reader.close()
    finally:
        writer.abort()
        captures.close()
        products.close()
