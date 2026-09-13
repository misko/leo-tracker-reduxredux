from contextlib import contextmanager

import pytest

import leo.scanner.adaptive_hop_analysis as detector
from leo.application.adaptive_hop_analysis import (
    AdaptiveHopAnalysisService,
    HostAdaptiveAnalysisService,
)
from leo.scanner.host_adaptive_analysis import (
    HostAdaptiveAnalysisConfigurationV2,
    HostAdaptiveAnalysisSource,
)
from leo.scanner.host_adaptive_presentation import HostAdaptiveAnalysisStatusV2
from leo.scanner.host_adaptive_products import (
    HostAdaptiveAnalysisBindingV2,
    HostAdaptiveMetricsManifestV2,
)
from leo.scanner.single_rx import SingleRxHopTimingV2
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tests.scanner.adaptive_hop_fixtures import timing_fixture
from tests.scanner.host_adaptive_fixtures import host_receipt
from tests.scanner.test_host_adaptive_analysis import Reader
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_host_adaptive_hop_store import block


class Inputs:
    def __init__(self, receiver=0):
        self.reader = Reader(receiver=receiver, count=7)
        self.opens = self.closes = 0

    @contextmanager
    def source(self, session_id):
        assert session_id == self.reader.session_id
        self.opens += 1
        try:
            yield HostAdaptiveAnalysisSource(self.reader)
        finally:
            self.closes += 1


@pytest.mark.parametrize("receiver", [0, 1])
def test_native_checkpoint_resume_and_four_workers_preserve_all_visits(
    tmp_path, monkeypatch, receiver
):
    inputs = Inputs(receiver)
    products = AdaptiveHopAnalysisStore(tmp_path)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    service = HostAdaptiveAnalysisService(inputs=inputs, products=products)
    try:
        first = service.analyze_session(
            inputs.reader.session_id, maximum_visits=3, maximum_workers=4
        )
        assert first.state == "partial" and first.completed_visits == 3
        assert inputs.reader.calls == [0, 1, 2]
        second = service.analyze_session(inputs.reader.session_id, maximum_workers=4)
        assert second.state == "metrics_complete" and second.newly_analyzed_visits == 3
        assert inputs.reader.calls == list(range(6))
        third = service.analyze_session(inputs.reader.session_id, maximum_workers=4)
        assert third.newly_analyzed_visits == 0
        assert inputs.opens == inputs.closes == 3
        binding = HostAdaptiveAnalysisBindingV2(
            receipt=inputs.reader.receipt,
            input_manifest_sha256=inputs.reader.input_manifest_sha256,
            configuration=HostAdaptiveAnalysisConfigurationV2(receiver_ids=(receiver,)),
        )
        with products.job(binding) as job:
            metrics = job.verify()
            assert isinstance(metrics, HostAdaptiveMetricsManifestV2)
            assert len(metrics.visits) == 6
            assert all(
                v.relative_path.endswith(".v2.json.zst") and v.probe_count == 11
                for v in metrics.visits
            )
            assert [v.visit_index for v in job.published_visits()] == list(range(6))
            status = job.status()
            assert isinstance(status, HostAdaptiveAnalysisStatusV2)
            assert status.state == "metrics_complete" and status.overview is None
            assert status.configuration.receiver_ids == (receiver,)
            assert status.worker_activity == "not_observed"
    finally:
        products.close()


@pytest.mark.parametrize("receiver", [0, 1])
def test_real_native_iq_manifest_to_checkpointed_metrics(tmp_path, monkeypatch, receiver):
    receipt = host_receipt(receiver=receiver, count=3)
    store, products = AdaptiveHopIqStore(tmp_path), AdaptiveHopAnalysisStore(tmp_path)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    writer = store.begin(receipt.session_id, receipt.plan)
    try:
        for i in range(receipt.complete_visit_count):
            writer.append(block(receipt, i))
        writer.finish(receipt, timing=timing_fixture(receipt, SingleRxHopTimingV2))
        inputs = AdaptiveHopAnalysisInputStore(store)
        with inputs.source(receipt.session_id) as source:
            assert isinstance(source, HostAdaptiveAnalysisSource)
            assert source.read_visit(0).shape == (1_200_000, 1)
        service = HostAdaptiveAnalysisService(inputs=inputs, products=products)
        result = service.analyze_session(receipt.session_id, maximum_workers=4)
        assert result.state == "metrics_complete" and result.completed_visits == 2
        with pytest.raises(ValueError, match="source major"):
            AdaptiveHopAnalysisService(inputs=inputs, products=products).analyze_session(
                receipt.session_id
            )
    finally:
        writer.abort()
        store.close()
        products.close()


@pytest.mark.parametrize("maximum_workers", [0, True, 5])
def test_invalid_native_worker_count_rejects_before_source(tmp_path, maximum_workers):
    inputs = Inputs()
    products = AdaptiveHopAnalysisStore(tmp_path)
    try:
        with pytest.raises(ValueError, match="1..4"):
            HostAdaptiveAnalysisService(inputs=inputs, products=products).analyze_session(
                inputs.reader.session_id,
                maximum_workers=maximum_workers,
            )
        assert inputs.opens == 0
    finally:
        products.close()


def test_failed_later_native_visit_preserves_earlier_checkpoint(tmp_path, monkeypatch):
    inputs, products = Inputs(), AdaptiveHopAnalysisStore(tmp_path)
    original = detector.analyze_glrt64_dwell

    def fail(samples, cfg, *, edge):
        if samples[0, 0].real == 2:
            raise RuntimeError("synthetic second visit failure")
        return _fake_fractional_dwell(samples, cfg, edge=edge)

    monkeypatch.setattr(detector, "analyze_glrt64_dwell", fail)
    service = HostAdaptiveAnalysisService(inputs=inputs, products=products)
    try:
        with pytest.raises(RuntimeError, match="second visit"):
            service.analyze_session(inputs.reader.session_id, maximum_workers=4)
        monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
        inputs.reader.calls.clear()
        result = service.analyze_session(inputs.reader.session_id, maximum_workers=4)
        assert result.completed_visits == 6 and result.newly_analyzed_visits == 5
        assert 0 not in inputs.reader.calls
        assert inputs.opens == inputs.closes == 2
    finally:
        monkeypatch.setattr(detector, "analyze_glrt64_dwell", original)
        products.close()
