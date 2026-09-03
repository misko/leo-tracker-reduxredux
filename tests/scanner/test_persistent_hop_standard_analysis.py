from __future__ import annotations

import numpy as np
import pytest

import leo.scanner.persistent_hop_analysis as persistent_source_module
import leo.scanner.persistent_hop_standard_analysis as persistent_product_module
from leo.scanner import (
    PersistentHopGlrt64Configuration,
    analyze_persistent_hop_sweep,
    analyze_persistent_hop_sweep_v2,
    build_persistent_hop_analysis_source,
    compile_persistent_hop_plan_v1,
)
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop_products import (
    PersistentHopAnalysisChunkV1,
    PersistentHopAnalysisChunkV2,
    PersistentHopCandidateV2,
)


class _ZeroReader:
    def __init__(self, sample_count: int) -> None:
        self.sample_count = sample_count
        self.receiver_ids = (0, 1)
        self.calls: list[tuple[int, int]] = []

    def read_valid_ci16(self, sample_start: int, sample_count: int) -> np.ndarray:
        self.calls.append((sample_start, sample_count))
        return np.zeros((sample_count, 2, 2), dtype="<i2")


def _source(visit_count: int = 8):
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id="hop-analysis-product")
    for _ in range(visit_count):
        session.read_visit()
    session.request_cancel()
    receipt = session.finish()
    radio.close()
    reader = _ZeroReader(receipt.valid_sample_count)
    source = build_persistent_hop_analysis_source(
        receipt=receipt,
        reader=reader,
        input_uri="bulk://scanner-hop-recordings/hop-analysis-product",
        input_manifest_sha256="sha256:" + "1" * 64,
    )
    return source, reader


def _fake_dwell(_samples, configuration, *, edge) -> DwellGlrt64Analysis:
    probes = []
    for probe_index in range(configuration.scheduled_probe_count):
        for receiver_id in configuration.receiver_ids:
            weaker = Glrt64CandidateResponse(
                candidate_rank=0,
                epoch_sample=100,
                acquired_cfo_hz=1_000.0,
                residual_cfo_hz=20.0,
                tracking_cfo_hz=1_020.0,
                exact_score=0.2,
                control_score=0.1,
                margin=0.1,
                passed_margin_gate=True,
            )
            strongest = Glrt64CandidateResponse(
                candidate_rank=1,
                epoch_sample=125,
                acquired_cfo_hz=2_000.0,
                residual_cfo_hz=-10.0,
                tracking_cfo_hz=1_990.0,
                exact_score=0.8,
                control_score=0.1,
                margin=0.7,
                passed_margin_gate=True,
                fractional_epoch_status="refined",
                fractional_epoch_offset_samples=0.25,
                fractional_frame_phase_sample=125.25,
                fractional_exact_score=0.81,
                fractional_control_score=0.1,
            )
            probes.append(
                Glrt64ProbeResponse(
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                    probe_start_ms=probe_index * configuration.probe_stride_ms,
                    candidates=(weaker, strongest),
                )
            )
    return DwellGlrt64Analysis(
        first=None,
        decision_best_margin=0.7,
        full_best_margin=0.7,
        reason=f"fixture {edge}",
        probes=tuple(probes),
    )


def test_sweep_product_is_bounded_complete_and_keeps_fractional_time_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, reader = _source()
    monkeypatch.setattr(persistent_source_module, "analyze_glrt64_dwell", _fake_dwell)

    chunk = analyze_persistent_hop_sweep(source, 0)

    assert chunk.visit_count == 8
    assert len(chunk.probes) == 8 * 2 * 11
    assert len(reader.calls) == 8
    first = chunk.probes[0]
    assert first.target_index == 0
    assert first.candidate_count == 2
    assert first.best is not None
    assert first.best.candidate_rank == 1
    assert first.best.integer_epoch_sample == 125
    assert first.best.fractional_epoch_offset_samples == pytest.approx(0.25)
    assert first.best.effective_device_sample_counter == pytest.approx(
        first.best.integer_device_sample_counter + 0.25
    )
    assert first.best.effective_session_sample == pytest.approx(
        first.best.integer_session_sample + 0.25
    )
    assert first.best.effective_time_s == pytest.approx(
        first.best.effective_session_sample / source.sample_rate_hz
    )

    duplicated = chunk.probes[:-1] + (chunk.probes[0],)
    with pytest.raises(ValueError, match="probe coverage is incomplete"):
        PersistentHopAnalysisChunkV1.model_validate(
            {**chunk.model_dump(mode="python"), "probes": duplicated}
        )


def test_sweep_product_rejects_unknown_or_cross_bound_sweep() -> None:
    source, _reader = _source(visit_count=1)
    configuration = PersistentHopGlrt64Configuration(source.plan)

    with pytest.raises(ValueError, match="does not exist"):
        analyze_persistent_hop_sweep(source, 1, configuration=configuration)


def test_sweep_product_parallel_path_is_ordered_and_uses_one_probe_per_visit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, reader = _source(visit_count=2)
    monkeypatch.setattr(persistent_product_module, "analyze_glrt64_dwell", _fake_dwell)
    configuration = PersistentHopGlrt64Configuration(source.plan, probe_stride_ms=120)

    chunk = analyze_persistent_hop_sweep(
        source,
        0,
        configuration=configuration,
        maximum_workers=2,
    )

    assert reader.calls == [(0, 300_000), (300_000, 300_000)]
    assert chunk.configuration.probe_stride_ms == 120
    assert [(row.visit_index, row.receiver_id) for row in chunk.probes] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    ]


def _fake_fractional_dwell(_samples, configuration, *, edge) -> DwellGlrt64Analysis:
    probes = []
    for probe_index in range(configuration.scheduled_probe_count):
        for receiver_id in configuration.receiver_ids:
            integer_winner = Glrt64CandidateResponse(
                candidate_rank=0,
                epoch_sample=100,
                acquired_cfo_hz=1_000.0,
                residual_cfo_hz=20.0,
                tracking_cfo_hz=1_020.0,
                exact_score=0.14,
                control_score=0.10,
                margin=0.04,
                passed_margin_gate=True,
                fractional_epoch_status="complete",
                fractional_epoch_offset_samples=-0.25,
                fractional_frame_phase_sample=99.75,
                fractional_exact_score=0.115,
                fractional_control_score=0.10,
                fractional_residual_cfo_hz=35.0,
                fractional_tracking_cfo_hz=1_035.0,
                fractional_margin=0.015,
            )
            fractional_winner = Glrt64CandidateResponse(
                candidate_rank=1,
                epoch_sample=125,
                acquired_cfo_hz=2_000.0,
                residual_cfo_hz=-10.0,
                tracking_cfo_hz=1_990.0,
                exact_score=0.12,
                control_score=0.10,
                margin=0.02,
                passed_margin_gate=False,
                fractional_epoch_status="complete",
                fractional_epoch_offset_samples=0.375,
                fractional_frame_phase_sample=125.375,
                fractional_exact_score=0.145,
                fractional_control_score=0.10,
                fractional_residual_cfo_hz=-40.0,
                fractional_tracking_cfo_hz=1_960.0,
                fractional_margin=0.045,
            )
            probes.append(
                Glrt64ProbeResponse(
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                    probe_start_ms=probe_index * configuration.probe_stride_ms,
                    candidates=(integer_winner, fractional_winner),
                )
            )
    return DwellGlrt64Analysis(
        first=None,
        decision_best_margin=0.04,
        full_best_margin=0.04,
        reason=f"fractional fixture {edge}",
        probes=tuple(probes),
    )


def test_v2_ranks_gates_and_reports_cfo_at_fractional_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _reader = _source(visit_count=1)
    monkeypatch.setattr(persistent_source_module, "analyze_glrt64_dwell", _fake_fractional_dwell)

    chunk = analyze_persistent_hop_sweep_v2(source, 0)

    assert isinstance(chunk, PersistentHopAnalysisChunkV2)
    first = chunk.probes[0]
    assert first.candidate_count == first.fractionally_scored_candidate_count == 2
    assert [item.candidate_rank for item in first.fractional_candidates] == [0, 1]
    assert first.winning_candidate_rank == 1
    assert first.best is not None
    assert first.best.candidate_rank == 1
    assert first.best.integer_epoch_sample == 125
    assert first.best.fractional_epoch_offset_samples == pytest.approx(0.375)
    assert first.best.fractional_session_sample == pytest.approx(
        first.best.integer_session_sample + 0.375
    )
    assert first.best.integer_tracking_cfo_hz == pytest.approx(1_990.0)
    assert first.best.fractional_tracking_cfo_hz == pytest.approx(1_960.0)
    assert first.best.passed_integer_margin_gate is False
    assert first.best.passed_fractional_margin_gate is True

    with pytest.raises(ValueError, match="fractional coordinate changed its integer anchor"):
        PersistentHopCandidateV2.model_validate(
            {
                **first.best.model_dump(mode="python"),
                "fractional_session_sample": first.best.fractional_session_sample + 1.0,
            }
        )
