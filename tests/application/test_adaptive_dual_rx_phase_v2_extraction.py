from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import leo.application.adaptive_dual_rx_phase_v2 as subject
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
    DualReceiverPhaseObservation,
    ReceiverFrameSeries,
)
from leo.scanner.adaptive_hop_analysis import AdaptiveHopFractionalCandidateV1


def candidate(epoch: int, tracking_hz: float, margin: float = 0.2):
    return AdaptiveHopFractionalCandidateV1(
        candidate_rank=0,
        integer_epoch_sample=epoch,
        integer_device_sample_counter=1000 + epoch,
        integer_session_sample=epoch,
        fractional_epoch_offset_samples=0.25,
        fractional_time_s=(epoch + 0.25) / 2_500_000,
        acquired_cfo_hz=tracking_hz - 100.0,
        integer_residual_cfo_hz=100.0,
        integer_tracking_cfo_hz=tracking_hz,
        integer_exact_score=0.4,
        integer_control_score=0.2,
        integer_margin=0.2,
        fractional_residual_cfo_hz=100.0,
        fractional_tracking_cfo_hz=tracking_hz,
        fractional_exact_score=margin + 0.1,
        fractional_control_score=0.1,
        fractional_margin=margin,
        passed_fractional_margin_gate=True,
    )


def test_pairing_requires_one_to_one_common_receiver_offset() -> None:
    left = (candidate(100, -90_000), candidate(400, -60_000))
    right = (candidate(101, -650_000), candidate(401, -620_000))
    visit = SimpleNamespace(
        configuration=SimpleNamespace(sample_rate_hz=2_500_000),
        probes=(
            SimpleNamespace(receiver_id=0, probe_index=0, candidates=left),
            SimpleNamespace(receiver_id=1, probe_index=0, candidates=right),
        ),
    )

    pairs = subject._phase_blind_pairs(visit)

    assert len(pairs) == 2
    assert {pair[2] for pair in pairs} == {-560_000.0}


def _observation(center: float, phase: float, relative_hz: float):
    series = tuple(
        ReceiverFrameSeries(
            receiver_id=receiver,
            frame_starts=(100, 200, 300),
            frame_phasors=(1 + 0j,) * 3,
            control_phasors=(0.1 + 0j,) * 3,
            within_frame_residual_cfo_hz=0.0,
            exact_to_control_power_ratio=10.0,
        )
        for receiver in (0, 1)
    )
    return DualReceiverPhaseObservation(
        center_sample=center,
        wrapped_phase_rad=phase,
        relative_frequency_hz=relative_hz,
        relative_frequency_standard_error_hz=0.2,
        resultant_length=0.95,
        phase_standard_error_deg=4.0,
        independent_frame_count=3,
        receivers=series,  # type: ignore[arg-type]
    )


def test_visit_retains_alias_hypothesis_without_phase_selection(monkeypatch) -> None:
    pairs = [
        (candidate(100, -90_000), candidate(101, -650_000), -560_000.0),
        (candidate(400, -60_000), candidate(401, -620_000), -560_000.0),
    ]
    outputs = iter((_observation(1000.0, 0.2, -560_100.0), _observation(1010.0, 0.5, -559_900.0)))
    monkeypatch.setattr(subject, "_phase_blind_pairs", lambda visit: pairs)
    monkeypatch.setattr(subject, "_extract_pair", lambda iq, visit, pair: next(outputs))
    visit = SimpleNamespace(
        session_id="scan-hop-phase-v2",
        input_manifest_sha256="sha256:" + "1" * 64,
        visit_index=7,
        target_index=1,
        target=SimpleNamespace(edge="lower"),
        configuration=SimpleNamespace(sample_rate_hz=2_500_000),
        valid_start_counter=2_000,
        source_origin_counter=1_000,
    )

    result = subject.extract_phase_visit_v2(
        np.zeros((1, 2), dtype=np.complex64),
        visit,
        glrt_binding_sha256="sha256:" + "2" * 64,
    )

    assert result.state == "qualified" and len(result.hypotheses) == 1
    hypothesis = result.hypotheses[0]
    assert hypothesis.association_uses_phase is False
    assert hypothesis.alias_resolved is False
    assert hypothesis.receiver_offset_hz == -560_000.0
    expected = 0.5 + 2 * np.pi * -559_900 * (-5 / 2_500_000)
    expected -= 0.2 + 2 * np.pi * -560_100 * (5 / 2_500_000)
    assert hypothesis.wrapped_high_minus_low_rad == pytest.approx(np.angle(np.exp(1j * expected)))


def test_alias_rejection_keeps_hypothesis_indexes_contiguous(monkeypatch) -> None:
    pairs = [
        (candidate(100, -90_000), candidate(101, -650_000), -560_000.0),
        (candidate(400, -90_000), candidate(401, -650_000), -560_000.0),
        (candidate(700, -60_000), candidate(701, -620_000), -560_000.0),
    ]
    outputs = iter(
        (
            _observation(1000.0, 0.2, -560_100.0),
            _observation(1010.0, 0.3, -560_000.0),
            _observation(1020.0, 0.5, -559_900.0),
        )
    )
    monkeypatch.setattr(subject, "_phase_blind_pairs", lambda visit: pairs)
    monkeypatch.setattr(subject, "_extract_pair", lambda iq, visit, pair: next(outputs))
    visit = SimpleNamespace(
        session_id="scan-hop-phase-v2",
        input_manifest_sha256="sha256:" + "1" * 64,
        visit_index=7,
        target_index=1,
        target=SimpleNamespace(edge="lower"),
        configuration=SimpleNamespace(sample_rate_hz=2_500_000),
        valid_start_counter=2_000,
        source_origin_counter=1_000,
    )

    result = subject.extract_phase_visit_v2(
        np.zeros((1, 2), dtype=np.complex64),
        visit,
        glrt_binding_sha256="sha256:" + "2" * 64,
    )

    assert [item.hypothesis_index for item in result.hypotheses] == [0, 1]


def test_visit_reports_when_all_phase_blind_pairs_are_pilot_aliases(monkeypatch) -> None:
    pairs = [
        (candidate(100, -90_000), candidate(101, -650_000), -560_000.0),
        (candidate(400, -90_000), candidate(401, -650_000), -560_000.0),
    ]
    outputs = iter((_observation(1000.0, 0.2, -560_100.0), _observation(1010.0, 0.3, -560_000.0)))
    monkeypatch.setattr(subject, "_phase_blind_pairs", lambda visit: pairs)
    monkeypatch.setattr(subject, "_extract_pair", lambda iq, visit, pair: next(outputs))
    visit = SimpleNamespace(
        session_id="scan-hop-phase-v2",
        input_manifest_sha256="sha256:" + "1" * 64,
        visit_index=7,
        target_index=1,
        target=SimpleNamespace(edge="lower"),
        configuration=SimpleNamespace(sample_rate_hz=2_500_000),
        valid_start_counter=2_000,
        source_origin_counter=1_000,
    )

    result = subject.extract_phase_visit_v2(
        np.zeros((1, 2), dtype=np.complex64),
        visit,
        glrt_binding_sha256="sha256:" + "2" * 64,
    )

    assert result.state == "insufficient_signal"
    assert result.reason == "no_alias_distinct_two_signal_hypothesis"
    assert result.consistent_receiver_pair_count == 2
    assert result.phase_quality_pair_count == 2
