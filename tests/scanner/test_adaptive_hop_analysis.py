from dataclasses import replace

import numpy as np
import pytest
from pydantic import ValidationError

import leo.scanner.adaptive_hop_analysis as analysis_module
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopAnalysisSource,
    AdaptiveHopVisitAnalysisV1,
    analyze_adaptive_hop_visit,
    validate_adaptive_analysis_binding,
)
from tests.scanner.adaptive_hop_fixtures import receipt_fixture
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell


class Reader:
    def __init__(self, *, rate=2_500_000, mode="adaptive", count=30):
        self.receipt = receipt_fixture(rate=rate, mode=mode, count=count)
        self.session_id = self.receipt.session_id
        self.input_manifest_sha256 = "sha256:" + "1" * 64
        self.calls = []

    def read_visit_ci16(self, index):
        self.calls.append(index)
        visit = self.receipt.visits[index]
        values = np.zeros((visit.valid_sample_count, 2, 2), dtype="<i2")
        values[:, 0, :] = [index + 1, 2]
        values[:, 1, :] = [visit.event.target_index + 10, -3]
        return visit, values


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_actual_visits_and_fractional_decisions_keep_exact_anchor_and_real_gaps(
    monkeypatch, rate, mode
):
    reader = Reader(rate=rate, mode=mode)
    source = AdaptiveHopAnalysisSource(reader)
    assert reader.calls == []
    monkeypatch.setattr(analysis_module, "analyze_glrt64_dwell", _fake_fractional_dwell)
    product = analyze_adaptive_hop_visit(source, 25)
    assert reader.calls == [25]
    assert len(product.probes) == 22
    assert product.target_index == (2 if mode == "adaptive" else 1)
    assert not hasattr(product, "sweep_index")
    first = product.probes[0]
    assert first.winning_candidate_rank == 1
    assert not first.candidates[0].passed_fractional_margin_gate
    winner = first.candidates[1]
    assert winner.passed_fractional_margin_gate
    assert winner.integer_margin == 0.02 and winner.fractional_margin == 0.045
    assert winner.integer_tracking_cfo_hz == 1990 and winner.fractional_tracking_cfo_hz == 1960
    assert winner.integer_device_sample_counter == source.visits[25].event.valid_start_counter + 125
    assert winner.integer_device_sample_counter > 2**53
    assert winner.fractional_epoch_offset_samples == 0.375
    relative = winner.integer_device_sample_counter - reader.receipt.terminal.first_counter
    assert winner.integer_session_sample == relative
    assert winner.fractional_time_s == (relative + 0.375) / rate
    assert winner.fractional_time_s > 25 * 0.12
    assert not hasattr(winner, "fractional_device_sample_counter")
    assert product.model_dump(mode="json")["probes"][0]["candidates"][1][
        "integer_device_sample_counter"
    ] == str(winner.integer_device_sample_counter)
    assert AdaptiveHopVisitAnalysisV1.model_validate_json(product.model_dump_json()) == product
    validate_adaptive_analysis_binding(
        product, reader.receipt, input_manifest_sha256=reader.input_manifest_sha256
    )


@pytest.mark.parametrize("index", [-1, True, 1.0, 29, 30, 2500])
def test_incomplete_or_invalid_index_never_reads_iq(index):
    reader = Reader()
    with pytest.raises(ValueError, match="complete retained"):
        AdaptiveHopAnalysisSource(reader).read_visit(index)
    assert reader.calls == []


def test_source_validates_identity_and_exact_ci16_geometry():
    reader = Reader(count=2)
    source = AdaptiveHopAnalysisSource(reader)
    samples = source.read_visit(0)
    assert samples.shape == (300000, 2) and samples.dtype == np.complex64
    assert samples[0].tolist() == [1 + 2j, 10 - 3j]
    assert not samples.flags.writeable
    reader.input_manifest_sha256 = "sha256:" + "2" * 64
    with pytest.raises(ValueError, match="changed manifest"):
        source.read_visit(0)
    reader.session_id = "wrong"
    with pytest.raises(ValueError, match="session identity"):
        AdaptiveHopAnalysisSource(reader)


@pytest.mark.parametrize("fault", ["dtype", "shape", "layout", "target"])
def test_reader_cannot_relabel_or_reshape_iq(fault):
    reader = Reader(count=3)
    valid = reader.read_visit_ci16

    def broken(index):
        visit, values = valid(index)
        if fault == "dtype":
            values = values.astype(np.float32)
        if fault == "shape":
            values = values[:-1]
        if fault == "layout":
            values = np.asfortranarray(values)
        if fault == "target":
            visit = reader.receipt.visits[1]
        return visit, values

    reader.read_visit_ci16 = broken
    with pytest.raises(ValueError):
        AdaptiveHopAnalysisSource(reader).read_visit(0)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_probe",
        "duplicate_probe",
        "wrong_rx",
        "wrong_time",
        "integer_only",
        "outside_valid",
        "nonfinite",
    ],
)
def test_complete_probe_inventory_and_fractional_abstention(monkeypatch, fault):
    def detector(samples, cfg, *, edge):
        result = _fake_fractional_dwell(samples, cfg, edge=edge)
        probes = list(result.probes)
        if fault == "missing_probe":
            probes.pop()
        if fault == "duplicate_probe":
            probes[-1] = probes[0]
        if fault == "wrong_rx":
            probes[0] = replace(probes[0], receiver_id=2)
        if fault == "wrong_time":
            probes[0] = replace(probes[0], probe_start_ms=1)
        if fault in ("integer_only", "outside_valid", "nonfinite"):
            changes = (
                {"fractional_epoch_status": "not_evaluated"}
                if fault == "integer_only"
                else {"epoch_sample": 0, "fractional_epoch_offset_samples": -0.5}
                if fault == "outside_valid"
                else {"fractional_margin": float("nan")}
            )
            probes[0] = replace(
                probes[0], candidates=tuple(replace(c, **changes) for c in probes[0].candidates)
            )
        return replace(result, probes=tuple(probes))

    monkeypatch.setattr(analysis_module, "analyze_glrt64_dwell", detector)
    source = AdaptiveHopAnalysisSource(Reader(count=2))
    if fault in ("integer_only", "outside_valid"):
        product = analyze_adaptive_hop_visit(source, 0)
        assert product.probes[0].candidates == ()
        assert len(product.probes[0].unavailable_candidates) == 2
        assert product.probes[0].winning_candidate_rank is None
        assert product.probes[0].unavailable_candidates[0].reason == (
            "fractional_incomplete" if fault == "integer_only" else "outside_retained_interval"
        )
    else:
        with pytest.raises(ValueError):
            analyze_adaptive_hop_visit(source, 0)


@pytest.mark.parametrize(
    "fault", ["counter", "relative", "time", "gate", "target", "manifest", "policy"]
)
def test_product_and_receipt_binding_rejects_mislabelled_science(monkeypatch, fault):
    reader = Reader(count=2)
    monkeypatch.setattr(analysis_module, "analyze_glrt64_dwell", _fake_fractional_dwell)
    product = analyze_adaptive_hop_visit(AdaptiveHopAnalysisSource(reader), 0)
    payload = product.model_dump()
    candidate = payload["probes"][0]["candidates"][0]
    if fault == "counter":
        candidate["integer_device_sample_counter"] += 1
    if fault == "relative":
        candidate["integer_session_sample"] += 1
    if fault == "time":
        candidate["fractional_time_s"] += 1
    if fault == "gate":
        candidate["passed_fractional_margin_gate"] = True
    if fault == "target":
        payload["target_index"] = 1
    if fault == "manifest":
        payload["input_manifest_sha256"] = "sha256:" + "2" * 64
    if fault == "policy":
        payload["policy_generation"] += 1
    with pytest.raises(ValueError):
        changed = AdaptiveHopVisitAnalysisV1.model_validate(payload)
        validate_adaptive_analysis_binding(
            changed, reader.receipt, input_manifest_sha256=reader.input_manifest_sha256
        )


def test_analysis_configuration_is_frozen_and_explicitly_dense_by_default():
    cfg = AdaptiveHopAnalysisConfigurationV1(sample_rate_hz=5_000_000)
    assert cfg.probe_samples == 100000 and cfg.dwell_samples == 600000
    assert cfg.scheduled_probe_count == 11 and cfg.receiver_ids == (0, 1)
    assert (
        AdaptiveHopAnalysisConfigurationV1(
            sample_rate_hz=5_000_000, probe_stride_ms=120
        ).scheduled_probe_count
        == 1
    )
    for changes in (
        {"probe_stride_ms": 9},
        {"sample_rate_hz": 1},
        {"glrt64_margin_gate": float("inf")},
        {"receiver_ids": [False, True]},
        {"receiver_ids": [0.0, 1.0]},
        {"receiver_ids": [1, 0]},
    ):
        with pytest.raises(ValidationError):
            AdaptiveHopAnalysisConfigurationV1.model_validate({**cfg.model_dump(), **changes})
