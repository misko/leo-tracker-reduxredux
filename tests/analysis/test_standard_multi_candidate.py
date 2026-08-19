from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from leo.analysis.starlink import pilot_methods as pilot_module
from leo.analysis.starlink.acquisition import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
    detect_pilot_method_candidates,
)
from leo.analysis.starlink.trajectories import (
    TrajectoryBankConfig,
    TrajectoryMethodConfig,
    fit_trajectory_bank,
)
from leo.analysis.starlink.trajectory_feedback import trajectory_observations


def test_pilot_scan_retains_bounded_ranked_multiple_candidates(monkeypatch) -> None:
    acquired = tuple(SimpleNamespace(rank=index) for index in range(3))
    monkeypatch.setattr(
        pilot_module,
        "acquire_symbolwise",
        lambda *_args, **_kwargs: SimpleNamespace(winner=acquired[0], candidates=acquired),
    )

    def evaluate(_values, _sample_rate_hz, candidate) -> PilotMethodCandidate:
        score = PilotMethodScore(
            PilotMethod.GLRT64,
            0.9 - candidate.rank * 0.1,
            0.1,
            0.8 - candidate.rank * 0.1,
            0.0,
            100_000.0 + candidate.rank * 25_000.0,
        )
        return PilotMethodCandidate(
            candidate.rank,
            20 + candidate.rank,
            score.tracking_cfo_hz,
            (score,),
            0.8,
            0.5,
        )

    monkeypatch.setattr(pilot_module, "_evaluate_candidate", evaluate)

    result = detect_pilot_method_candidates(
        np.ones(100, dtype=np.complex128),
        2_500_000,
        sample_start=0,
        calibration=ReceiverFrequencyCalibration("rx", 0.0, "1" * 64),
        acquisition_config=SymbolwiseAcquisitionConfig(maximum_probe_samples=100),
        maximum_scored_candidates=2,
    )

    assert result.source_candidate_count == 3
    assert result.truncated_candidate_count == 1
    assert tuple(item.rank for item in result.candidates) == (0, 1)
    assert tuple(item.acquired_cfo_hz for item in result.candidates) == (100_000.0, 125_000.0)
    assert result.acquired_cfo_hz == result.candidates[0].acquired_cfo_hz


def test_crossing_candidate_basins_survive_into_two_trajectory_branches() -> None:
    detections = []
    for index in range(50):
        time_s = index * 0.1
        candidates = tuple(
            _candidate(rank, frequency)
            for rank, frequency in (
                (0, 100_000.0 + 10_000.0 * time_s),
                (1, 150_000.0 - 10_000.0 * time_s),
            )
        )
        detections.append(
            PilotProbeDetection(
                NumericalStatus.COMPLETE,
                index * 100,
                time_s,
                candidates[0].local_epoch_sample,
                candidates[0].acquired_cfo_hz,
                candidates[0].scores,
                None,
                None,
                "two crossing candidate basins",
                source_candidate_count=2,
                candidates=candidates,
            )
        )
    observations = trajectory_observations(tuple(detections))
    config = TrajectoryBankConfig(
        (
            TrajectoryMethodConfig(
                PilotMethod.GLRT64,
                high_gate=0.5,
                local_residual_gate_hz=500.0,
                final_residual_gate_hz=500.0,
                minimum_local_points=5,
                minimum_high_points=2,
                maximum_merge_gap_s=1.1,
                endpoint_gate_hz=1_000.0,
                endpoint_growth_hz_per_s=500.0,
                maximum_slope_difference_hz_per_s=25_000.0,
            ),
        ),
        polynomial_degrees=(1,),
        deduplication_frequency_gate_hz=1_000.0,
    )

    bank = fit_trajectory_bank(observations, config)

    assert len(observations) == 100
    assert len({item.observation_id for item in observations}) == 100
    assert len(bank.trajectories) == 2
    slopes = sorted(item.coefficients_hz[0] for item in bank.trajectories)
    assert slopes[0] < -9_999.0
    assert slopes[1] > 9_999.0
    assert all(item.start_s == 0.0 and item.end_s == 4.9 for item in bank.trajectories)


def _candidate(rank: int, frequency_hz: float) -> PilotMethodCandidate:
    score = PilotMethodScore(
        PilotMethod.GLRT64,
        0.9,
        0.1,
        0.8,
        0.0,
        frequency_hz,
    )
    return PilotMethodCandidate(rank, 0, frequency_hz, (score,), None, None)
