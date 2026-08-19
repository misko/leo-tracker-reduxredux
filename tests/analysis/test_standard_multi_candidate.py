from __future__ import annotations

from collections.abc import Iterator
from threading import Barrier
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink import pilot_methods as pilot_module
from leo.analysis.starlink import trajectory_feedback as feedback_module
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
    TrajectoryBankResult,
    TrajectoryMethodConfig,
    fit_trajectory_bank,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_legacy_pilot_trajectories,
    fit_pilot_trajectories,
    replay_pilot_trajectories,
    scan_legacy_pilot_detections,
    scan_pilot_detections,
    select_trajectory_representatives,
    trajectory_observations,
)
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.domain.iq import IqBlock


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


def test_pilot_scan_parallel_tasks_are_complete_coarse_windows(monkeypatch) -> None:
    barrier = Barrier(2)
    observed_batches: list[tuple[int, ...]] = []

    def detect(batch, *_args):
        observed_batches.append(tuple(sample_start for sample_start, _ in batch))
        barrier.wait(timeout=2)
        return ()

    monkeypatch.setattr(feedback_module, "_detect_batch", detect)

    result = scan_pilot_detections(
        _OneReceiverReader(),
        TrajectoryFeedbackConfig(maximum_outer_windows=4, maximum_workers=2),
    )

    assert result == ()
    assert len(observed_batches) == 4
    assert all(len(batch) == 20 for batch in observed_batches)
    assert sorted(batch[0] for batch in observed_batches) == [0, 1_000, 2_000, 3_000]
    assert all(batch[-1] - batch[0] == 950 for batch in observed_batches)


@pytest.mark.parametrize(
    "config,error",
    (
        (
            TrajectoryFeedbackConfig(maximum_replayed_families=-1),
            "positive integer",
        ),
        (
            TrajectoryFeedbackConfig(coarse_window_samples_per_second=2),
            "exact one-second",
        ),
    ),
)
def test_every_feedback_computation_rejects_invalid_shared_config(
    config: TrajectoryFeedbackConfig,
    error: str,
) -> None:
    reader = _OneReceiverReader()

    with pytest.raises(ValueError, match=error):
        scan_pilot_detections(reader, config)
    with pytest.raises(ValueError, match=error):
        scan_legacy_pilot_detections(reader, config)
    with pytest.raises(ValueError, match=error):
        fit_pilot_trajectories((), config)
    with pytest.raises(ValueError, match=error):
        fit_legacy_pilot_trajectories((), config)
    with pytest.raises(ValueError, match=error):
        replay_pilot_trajectories(reader, (), (), config)


@pytest.mark.parametrize("maximum", (-1, 0, True))
def test_public_representative_selector_rejects_invalid_scalar_bound(maximum) -> None:
    empty = TrajectoryBankResult(
        config_digest="sha256:" + "0" * 64,
        trajectories=(),
        families=(),
        observation_count=0,
        truncated_trajectory_count=0,
    )

    with pytest.raises(ValueError, match="maximum_replayed_families must be a positive integer"):
        select_trajectory_representatives(empty, maximum)


def test_public_representative_selector_accepts_positive_bound_for_empty_bank() -> None:
    empty = TrajectoryBankResult(
        config_digest="sha256:" + "0" * 64,
        trajectories=(),
        families=(),
        observation_count=0,
        truncated_trajectory_count=0,
    )

    assert select_trajectory_representatives(empty, 1) == ()


def test_intermittent_candidate_is_segmented_across_a_real_gap() -> None:
    detections = tuple(
        PilotProbeDetection(
            NumericalStatus.COMPLETE,
            index * 100,
            index * 0.1,
            0,
            100_000.0 + index * 25.0,
            _candidate(0, 100_000.0 + index * 25.0).scores,
            None,
            None,
            "intermittent fixture",
            source_candidate_count=1,
            candidates=(_candidate(0, 100_000.0 + index * 25.0),),
        )
        for index in (*range(20), *range(40, 61))
    )
    config = TrajectoryBankConfig(
        (
            TrajectoryMethodConfig(
                PilotMethod.GLRT64,
                high_gate=0.5,
                local_residual_gate_hz=500.0,
                final_residual_gate_hz=500.0,
                minimum_local_points=5,
                minimum_high_points=2,
                maximum_merge_gap_s=0.5,
                endpoint_gate_hz=1_000.0,
                endpoint_growth_hz_per_s=500.0,
                maximum_slope_difference_hz_per_s=5_000.0,
            ),
        ),
        polynomial_degrees=(1,),
        deduplication_frequency_gate_hz=1_000.0,
    )

    bank = fit_trajectory_bank(trajectory_observations(detections), config)

    assert len(bank.trajectories) == 2
    extents = sorted((item.start_s, item.end_s) for item in bank.trajectories)
    assert extents == [(0.0, 1.9000000000000001), (4.0, 6.0)]


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


class _OneReceiverReader:
    sample_rate_hz = 1_000
    center_frequency_hz = 1_000_000
    receiver_ids = (0,)
    sample_count = 4_000

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        interval = NanosecondIntervalV1(lower_ns=0, upper_ns=0)
        for start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - start)
            yield IqBlock(
                samples=np.zeros((count, 1, 2), dtype="<i2"),
                metadata=IqBlockMetadataV1(
                    radio_id="radio-0",
                    receiver_ids=self.receiver_ids,
                    sample_count=count,
                    session_sample_start=start,
                    host_request_utc_ns=interval,
                    host_request_monotonic_ns=interval,
                ),
            )
