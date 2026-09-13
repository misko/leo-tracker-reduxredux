import threading

import numpy as np
import pytest
from pydantic import ValidationError

import leo.scanner.adaptive_hop_analysis as implementation
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisSource, AdaptiveHopVisitAnalysisV1
from leo.scanner.host_adaptive_analysis import (
    HostAdaptiveAnalysisConfigurationV2,
    HostAdaptiveAnalysisSource,
    HostAdaptiveVisitAnalysisV2,
    analyze_host_adaptive_visit,
    analyze_host_adaptive_visit_batch,
    validate_host_adaptive_analysis_binding,
)
from tests.scanner.host_adaptive_fixtures import host_receipt
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell


class Reader:
    def __init__(self, *, receiver=0, mode="adaptive", count=30):
        self.receipt = host_receipt(receiver=receiver, mode=mode, count=count)
        self.session_id = self.receipt.session_id
        self.input_manifest_sha256 = "sha256:" + "1" * 64
        self.calls = []
        self.owner = threading.get_ident()

    def read_visit_ci16(self, index):
        assert threading.get_ident() == self.owner
        self.calls.append(index)
        visit = self.receipt.visits[index]
        values = np.empty((1_200_000, 1, 2), dtype="<i2")
        values[:, 0, :] = [index + 1, -32768]
        return visit, values


@pytest.mark.parametrize("receiver", [0, 1])
@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
def test_native_analysis_preserves_actual_target_counter_precision_and_physical_rx(
    monkeypatch, receiver, mode
):
    reader = Reader(receiver=receiver, mode=mode)
    source = HostAdaptiveAnalysisSource(reader)
    observed = []

    def detector(samples, cfg, *, edge):
        observed.append((samples.shape, cfg.sample_rate_hz, cfg.receiver_ids))
        return _fake_fractional_dwell(samples, cfg, edge=edge)

    monkeypatch.setattr(implementation, "analyze_glrt64_dwell", detector)
    product = analyze_host_adaptive_visit(source, 25)
    assert observed == [((1_200_000, 1), 10_000_000, (receiver,))]
    assert reader.calls == [25]
    assert len(product.probes) == 11
    assert {p.receiver_id for p in product.probes} == {receiver}
    assert product.target_index == (2 if mode == "adaptive" else 1)
    candidate = product.probes[0].candidates[1]
    assert (
        candidate.integer_device_sample_counter == source.visits[25].event.valid_start_counter + 125
    )
    assert candidate.integer_device_sample_counter > 2**53
    assert candidate.fractional_time_s == (candidate.integer_session_sample + 0.375) / 10_000_000
    assert candidate.fractional_time_s > 25 * 0.12
    assert HostAdaptiveVisitAnalysisV2.model_validate_json(product.model_dump_json()) == product
    validate_host_adaptive_analysis_binding(
        product, reader.receipt, input_manifest_sha256=reader.input_manifest_sha256
    )
    with pytest.raises(ValidationError):
        AdaptiveHopVisitAnalysisV1.model_validate_json(product.model_dump_json())
    with pytest.raises(ValidationError):
        AdaptiveHopAnalysisSource(reader)


@pytest.mark.parametrize("receiver", [0, 1])
def test_four_workers_match_serial_and_only_owner_reads_iq(monkeypatch, receiver):
    source = HostAdaptiveAnalysisSource(Reader(receiver=receiver, count=5))
    cfg = HostAdaptiveAnalysisConfigurationV2(receiver_ids=(receiver,))
    monkeypatch.setattr(implementation, "analyze_glrt64_dwell", _fake_fractional_dwell)
    serial = tuple(analyze_host_adaptive_visit(source, i, configuration=cfg) for i in range(4))
    parallel = tuple(analyze_host_adaptive_visit_batch(source, (0, 1, 2, 3), configuration=cfg))
    assert parallel == serial


@pytest.mark.parametrize("receiver", [0, 1])
def test_native_detector_serial_parallel_parity_on_synthetic_pilot(receiver):
    from leo.analysis.starlink.templates import qin_edge_pilot_frame

    reader = Reader(receiver=receiver, count=3)
    template = qin_edge_pilot_frame(10_000_000, "lower")
    samples = 4000 * np.resize(template, 1_200_000)
    components = np.rint(np.column_stack((samples.real, samples.imag)))
    assert np.abs(components).max() < 32768
    iq = components.astype("<i2")
    values = iq[:, None, :]
    reader.read_visit_ci16 = lambda i: (reader.receipt.visits[i], values)
    source = HostAdaptiveAnalysisSource(reader)
    cfg = HostAdaptiveAnalysisConfigurationV2(receiver_ids=(receiver,), probe_stride_ms=120)
    serial = tuple(analyze_host_adaptive_visit(source, i, configuration=cfg) for i in (0, 1))
    parallel = tuple(analyze_host_adaptive_visit_batch(source, (0, 1), configuration=cfg))
    assert serial == parallel
    assert all(len(p.probes) == 1 for p in parallel)


@pytest.mark.parametrize("fault", ["receiver", "rate", "column", "counter", "hash"])
def test_native_analysis_rejects_wrong_source_or_configuration(monkeypatch, fault):
    reader = Reader()
    source = HostAdaptiveAnalysisSource(reader)
    cfg = HostAdaptiveAnalysisConfigurationV2(receiver_ids=(0,))
    monkeypatch.setattr(implementation, "analyze_glrt64_dwell", _fake_fractional_dwell)
    if fault == "receiver":
        cfg = cfg.model_copy(update={"receiver_ids": (1,)})
    elif fault == "rate":
        cfg = cfg.model_copy(update={"sample_rate_hz": 2_500_000})
    elif fault == "column":
        reader.read_visit_ci16 = lambda i: (
            reader.receipt.visits[i],
            np.zeros((1_200_000, 2, 2), "<i2"),
        )
    elif fault == "counter":
        visit = reader.receipt.visits[0]
        reader.read_visit_ci16 = lambda i: (
            visit.model_copy(update={"valid_end_counter_exclusive": 1}),
            np.zeros((1_200_000, 1, 2), "<i2"),
        )
    else:
        reader.input_manifest_sha256 = "sha256:" + "2" * 64
    with pytest.raises(ValueError):
        analyze_host_adaptive_visit(source, 0, configuration=cfg)


@pytest.mark.parametrize("indexes", [(), (0, 0), (0, 1, 2, 3, 4)])
def test_batch_bounds_reject_before_native_read(indexes):
    reader = Reader()
    with pytest.raises(ValueError, match="one to four distinct"):
        tuple(
            analyze_host_adaptive_visit_batch(
                HostAdaptiveAnalysisSource(reader),
                indexes,
                configuration=HostAdaptiveAnalysisConfigurationV2(receiver_ids=(0,)),
            )
        )
    assert reader.calls == []
