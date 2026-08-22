from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import PilotMethod, PilotMethodScore, PilotProbeDetection
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryObservation,
    correct_polynomial_cfo,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    infer_hough_replay_alias_indices,
    replay_pilot_trajectories,
)

_ALIAS_SPACING_HZ = 2_500_000 / 11


def _trajectory(
    trajectory_id: str,
    observation_ids: tuple[str, ...],
    *,
    intercept_hz: float = 221_905.0,
) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        trajectory_id=trajectory_id,
        method=PilotMethod.GLRT64,
        polynomial_degree=1,
        reference_time_s=0.0,
        coefficients_hz=(0.0, intercept_hz),
        start_s=0.0,
        end_s=1.0,
        observation_ids=observation_ids,
        point_count=len(observation_ids),
        residual_rms_hz=0.0,
        bic=0.0,
        high_gate=0.0,
        em_iterations=0,
    )


def _observation(
    observation_id: str,
    *,
    time_s: float,
    frequency_hz: float,
    margin: float,
) -> TrajectoryObservation:
    return TrajectoryObservation(
        observation_id=observation_id,
        method=PilotMethod.GLRT64,
        sample_start=round(time_s * 2_500_000),
        time_s=time_s,
        tracking_cfo_hz=frequency_hz,
        score=margin + 0.04,
        control_score=0.04,
        margin=margin,
    )


def test_hough_replay_resolves_each_overlapping_segment_from_its_weighted_support() -> None:
    first_ids = tuple(f"first-{index}" for index in range(7))
    second_ids = ("second-a", "second-b")
    first = _trajectory("first", first_ids)
    second = _trajectory("second", second_ids, intercept_hz=-80_000.0)
    observations = (
        _observation(
            first_ids[0],
            time_s=0.0,
            frequency_hz=221_905.0 - 2 * _ALIAS_SPACING_HZ,
            margin=0.45,
        ),
        _observation(
            first_ids[1],
            time_s=0.1,
            frequency_hz=221_905.0 - 2 * _ALIAS_SPACING_HZ,
            margin=0.40,
        ),
        *(
            _observation(
                observation_id,
                time_s=0.2 + 0.1 * index,
                frequency_hz=221_905.0 - _ALIAS_SPACING_HZ,
                margin=0.001,
            )
            for index, observation_id in enumerate(first_ids[2:])
        ),
        _observation(
            second_ids[0],
            time_s=0.0,
            frequency_hz=-80_000.0 + _ALIAS_SPACING_HZ,
            margin=0.35,
        ),
        _observation(
            second_ids[1],
            time_s=0.2,
            frequency_hz=-80_000.0 + _ALIAS_SPACING_HZ,
            margin=0.30,
        ),
    )

    aliases = infer_hough_replay_alias_indices(
        (("family-first", first), ("family-second", second)),
        observations,
        alias_spacing_hz=_ALIAS_SPACING_HZ,
    )

    assert aliases == {"first": -2, "second": 1}


def test_lifted_cfo_correction_preserves_signal_that_canonical_alias_destroys() -> None:
    sample_rate_hz = 2_500_000
    count = sample_rate_hz // 50
    trajectory = _trajectory("trajectory", ("support",))
    physical_frequency_hz = 221_905.0 - 2 * _ALIAS_SPACING_HZ
    times = np.arange(count, dtype=float) / sample_rate_hz
    samples = np.exp(2j * np.pi * physical_frequency_hz * times)

    wrong_alias = correct_polynomial_cfo(samples, sample_rate_hz, 0, trajectory)
    resolved_alias = correct_polynomial_cfo(
        samples,
        sample_rate_hz,
        0,
        trajectory,
        frequency_offset_hz=-2 * _ALIAS_SPACING_HZ,
    )

    assert abs(np.mean(wrong_alias)) < 0.001
    assert abs(np.mean(resolved_alias)) > 0.999999


def test_replay_applies_the_inferred_alias_offset_before_redetection(monkeypatch) -> None:
    class Reader:
        sample_rate_hz = 2_500_000

    trajectory = _trajectory("trajectory", ("support",))
    score = PilotMethodScore(PilotMethod.GLRT64, 0.5, 0.04, 0.46, 0.0, -232_640.0)
    detection = PilotProbeDetection(
        NumericalStatus.COMPLETE,
        0,
        0.0,
        0,
        -232_640.0,
        (score,),
        None,
        None,
        "fixture",
    )
    observed_offsets: list[float] = []

    def probe_batches(*_args, **_kwargs) -> Iterator[tuple[tuple[int, np.ndarray], ...]]:
        yield ((0, np.ones(100, dtype=np.complex128)),)

    def correct(samples, _sample_rate_hz, _sample_start, _trajectory, *, frequency_offset_hz=0.0):
        observed_offsets.append(frequency_offset_hz)
        return samples

    def detect(
        _samples,
        _sample_rate_hz,
        *,
        sample_start,
        calibration,
        acquisition_config,
        edge,
    ) -> PilotProbeDetection:
        del calibration, acquisition_config, edge
        return detection.__class__(
            detection.status,
            sample_start,
            sample_start / Reader.sample_rate_hz,
            detection.local_epoch_sample,
            detection.acquired_cfo_hz,
            detection.scores,
            detection.qam_accuracy,
            detection.qam_evm,
            detection.reason,
        )

    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback._iter_probe_batches", probe_batches
    )
    monkeypatch.setattr("leo.analysis.starlink.trajectory_feedback.correct_polynomial_cfo", correct)
    monkeypatch.setattr("leo.analysis.starlink.trajectory_feedback.detect_pilot_methods", detect)

    rows = replay_pilot_trajectories(
        Reader(),  # type: ignore[arg-type]
        (detection,),
        (("family", trajectory),),
        TrajectoryFeedbackConfig(maximum_outer_windows=1, maximum_workers=1),
        edge="lower",  # type: ignore[arg-type]
        alias_indices={"trajectory": -2},
        alias_spacing_hz=_ALIAS_SPACING_HZ,
    )

    assert observed_offsets == [-2 * _ALIAS_SPACING_HZ]
    assert len(rows) == 1
    assert rows[0]["corrected_margin"] == 0.46
