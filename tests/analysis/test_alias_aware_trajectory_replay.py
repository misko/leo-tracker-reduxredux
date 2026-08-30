from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest

from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.cfo_dealias import default_replay_gate_v4
from leo.analysis.starlink.pilot_methods import PilotMethod, PilotMethodScore, PilotProbeDetection
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryObservation,
    correct_polynomial_cfo,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    _iter_explicit_probe_batches,
    infer_hough_replay_alias_indices,
    legacy_trajectory_replay_rows,
    rank_hough_replay_alias_candidates,
    replay_pilot_trajectories,
    replay_pilot_trajectories_at_detection_windows_with_conditioned_scores,
    replay_pilot_trajectories_with_conditioned_scores,
    resolve_hough_replay_alias_indices_by_native_replay,
)
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.domain.iq import IqBlock

_ALIAS_SPACING_HZ = 2_500_000 / 11


def test_explicit_probe_reader_preserves_dense_overlapping_windows() -> None:
    class Reader:
        sample_rate_hz = 1_000
        sample_count = 80
        receiver_ids = (0,)

        def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
            del block_samples
            values = np.zeros((self.sample_count, 1, 2), dtype="<i2")
            values[:, 0, 0] = np.arange(self.sample_count, dtype="<i2")
            for start in range(0, self.sample_count, 13):
                block = values[start : start + 13]
                interval = NanosecondIntervalV1(lower_ns=start, upper_ns=start)
                yield IqBlock(
                    samples=block,
                    metadata=IqBlockMetadataV1(
                        radio_id="fixture",
                        receiver_ids=(0,),
                        sample_count=len(block),
                        session_sample_start=start,
                        host_request_utc_ns=interval,
                        host_request_monotonic_ns=interval,
                    ),
                )

    batches = tuple(
        _iter_explicit_probe_batches(
            Reader(),  # type: ignore[arg-type]
            (5, 15, 35),
            10,
            maximum_batch_probes=2,
        )
    )

    assert tuple(len(batch) for batch in batches) == (2, 1)
    windows = tuple(item for batch in batches for item in batch)
    assert tuple(start for start, _ in windows) == (5, 15, 35)
    assert tuple(round(float(samples.real[0] * 32_768)) for _, samples in windows) == (5, 15, 35)


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


@pytest.mark.parametrize(
    ("alias_margins", "expected_aliases", "expected_unresolved"),
    (
        ({2: 0.0, 3: 0.70}, {"trajectory": 3}, ()),
        ({2: 0.70, 3: 0.72}, {}, ("trajectory",)),
    ),
)
def test_native_replay_resolves_only_a_decisive_wrap_boundary_alias(
    monkeypatch,
    alias_margins: dict[int, float],
    expected_aliases: dict[str, int],
    expected_unresolved: tuple[str, ...],
) -> None:
    """The GLRT wrap vote is a prior; native IQ replay decides the physical lift."""

    class Reader:
        sample_rate_hz = 2_500_000

    observation_ids = tuple(f"support-{index:02d}" for index in range(20))
    trajectory = _trajectory("trajectory", observation_ids)
    trajectory = PolynomialTrajectory(
        trajectory_id=trajectory.trajectory_id,
        method=trajectory.method,
        polynomial_degree=trajectory.polynomial_degree,
        reference_time_s=trajectory.reference_time_s,
        coefficients_hz=trajectory.coefficients_hz,
        start_s=0.0,
        end_s=1.9,
        observation_ids=trajectory.observation_ids,
        point_count=trajectory.point_count,
        residual_rms_hz=trajectory.residual_rms_hz,
        bic=trajectory.bic,
        high_gate=trajectory.high_gate,
        em_iterations=trajectory.em_iterations,
    )
    observations = tuple(
        _observation(
            observation_id,
            time_s=index / 10,
            frequency_hz=221_905.0 + (2 if index < 11 else 3) * _ALIAS_SPACING_HZ,
            margin=0.65 if index < 11 else 0.60,
        )
        for index, observation_id in enumerate(observation_ids)
    )
    baseline_score = PilotMethodScore(
        PilotMethod.GLRT64,
        0.64,
        0.04,
        0.60,
        0.0,
        221_905.0 + 3 * _ALIAS_SPACING_HZ,
    )
    detections = tuple(
        PilotProbeDetection(
            NumericalStatus.COMPLETE,
            round(index / 10 * Reader.sample_rate_hz),
            index / 10,
            0,
            baseline_score.tracking_cfo_hz,
            (baseline_score,),
            None,
            None,
            "wrap-boundary fixture",
        )
        for index in range(20)
    )

    assert infer_hough_replay_alias_indices(
        (("family", trajectory),),
        observations,
        alias_spacing_hz=_ALIAS_SPACING_HZ,
    ) == {"trajectory": 2}

    def explicit_batches(_iq, sample_starts, _probe_samples, **_kwargs):
        yield tuple((start, np.ones(16, dtype=np.complex128)) for start in sample_starts)

    def correct(
        samples,
        _sample_rate_hz,
        _sample_start,
        _trajectory,
        *,
        frequency_offset_hz=0.0,
    ):
        corrected = samples.copy()
        corrected[0] = frequency_offset_hz
        return corrected

    def detect(
        samples,
        _sample_rate_hz,
        *,
        sample_start,
        calibration,
        acquisition_config,
        edge,
    ) -> PilotProbeDetection:
        del calibration, acquisition_config, edge
        alias_index = round(float(samples[0].real) / _ALIAS_SPACING_HZ)
        margin = alias_margins.get(alias_index, 0.0)
        score = PilotMethodScore(PilotMethod.GLRT64, margin + 0.04, 0.04, margin, 0.0, 0.0)
        return PilotProbeDetection(
            NumericalStatus.COMPLETE,
            sample_start,
            sample_start / Reader.sample_rate_hz,
            0,
            0.0,
            (score,),
            None,
            None,
            "native replay fixture",
        )

    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback._iter_explicit_probe_batches",
        explicit_batches,
    )
    monkeypatch.setattr("leo.analysis.starlink.trajectory_feedback.correct_polynomial_cfo", correct)
    monkeypatch.setattr("leo.analysis.starlink.trajectory_feedback.detect_pilot_methods", detect)

    resolution = resolve_hough_replay_alias_indices_by_native_replay(
        Reader(),  # type: ignore[arg-type]
        detections,
        (("family", trajectory),),
        observations,
        TrajectoryFeedbackConfig(maximum_workers=1),
        edge="lower",  # type: ignore[arg-type]
        alias_spacing_hz=_ALIAS_SPACING_HZ,
        gate_config=default_replay_gate_v4(sample_rate_hz=Reader.sample_rate_hz),
        usable_baseband_min_hz=-Reader.sample_rate_hz / 2,
        usable_baseband_max_hz=Reader.sample_rate_hz / 2,
    )

    assert resolution.alias_indices == expected_aliases
    assert resolution.unresolved_trajectory_ids == expected_unresolved
    evidence = {item.alias_index: item for item in resolution.evidence}
    assert evidence[2].median_block_corrected_margin == alias_margins[2]
    assert evidence[3].median_block_corrected_margin == alias_margins[3]
    assert evidence[3].selected is bool(expected_aliases)
    if expected_unresolved:
        assert all(not item.selected for item in evidence.values())
        assert "without decisive replay separation" in evidence[3].reason


@pytest.mark.parametrize(
    ("usable_min_hz", "usable_max_hz", "expected_aliases"),
    (
        (-5_000_000.0, 5_000_000.0, (1, 2, 3)),
        (-500_000.0, 500_000.0, (1,)),
        (-200_000.0, 200_000.0, ()),
    ),
)
def test_hough_alias_candidates_respect_the_capture_usable_baseband(
    usable_min_hz: float,
    usable_max_hz: float,
    expected_aliases: tuple[int, ...],
) -> None:
    observation_ids = ("support-2", "support-3")
    trajectory = _trajectory("trajectory", observation_ids)
    observations = (
        _observation(
            observation_ids[0],
            time_s=0.0,
            frequency_hz=221_905.0 + 2 * _ALIAS_SPACING_HZ,
            margin=0.60,
        ),
        _observation(
            observation_ids[1],
            time_s=0.5,
            frequency_hz=221_905.0 + 3 * _ALIAS_SPACING_HZ,
            margin=0.55,
        ),
    )

    candidates = rank_hough_replay_alias_candidates(
        (("family", trajectory),),
        observations,
        alias_spacing_hz=_ALIAS_SPACING_HZ,
        usable_baseband_min_hz=usable_min_hz,
        usable_baseband_max_hz=usable_max_hz,
    )

    assert tuple(item.alias_index for item in candidates) == expected_aliases


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


def test_conditioned_replay_transports_epoch_when_independent_winner_moves(monkeypatch) -> None:
    class Reader:
        sample_rate_hz = 2_500_000

    trajectory = _trajectory("trajectory-conditioned", ("support",))
    baseline_score = PilotMethodScore(PilotMethod.GLRT64, 0.44, 0.04, 0.40, 0.0, -232_640.0)
    detection = PilotProbeDetection(
        NumericalStatus.COMPLETE,
        0,
        0.0,
        73,
        -232_640.0,
        (baseline_score,),
        None,
        None,
        "fixture",
    )
    independent = PilotMethodScore(PilotMethod.GLRT64, 0.04, 0.04, 0.0, 50_000.0, 50_000.0)
    observed_conditioning: list[tuple[int, float, int]] = []

    def probe_batches(*_args, **_kwargs) -> Iterator[tuple[tuple[int, np.ndarray], ...]]:
        yield ((0, np.ones(100, dtype=np.complex128)),)

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
        return PilotProbeDetection(
            NumericalStatus.COMPLETE,
            sample_start,
            0.0,
            999,
            50_000.0,
            (independent,),
            None,
            None,
            "wrong independent winner",
        )

    def conditioned(
        _samples,
        _sample_rate_hz,
        *,
        epoch_sample,
        acquired_cfo_hz,
        edge,
        glrt_size,
    ) -> PilotMethodScore:
        del edge
        observed_conditioning.append((epoch_sample, acquired_cfo_hz, glrt_size))
        return PilotMethodScore(PilotMethod.GLRT64, 0.45, 0.04, 0.41, 0.0, 0.0)

    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback._iter_probe_batches", probe_batches
    )
    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.correct_polynomial_cfo",
        lambda samples, *_args, **_kwargs: samples,
    )
    monkeypatch.setattr("leo.analysis.starlink.trajectory_feedback.detect_pilot_methods", detect)
    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.conditioned_glrt64_score", conditioned
    )

    rows = replay_pilot_trajectories_with_conditioned_scores(
        Reader(),  # type: ignore[arg-type]
        (detection,),
        (("family", trajectory),),
        TrajectoryFeedbackConfig(
            maximum_outer_windows=1,
            maximum_workers=1,
            glrt_size=4_096,
        ),
        edge="lower",  # type: ignore[arg-type]
        alias_indices={trajectory.trajectory_id: -2},
        alias_spacing_hz=_ALIAS_SPACING_HZ,
        association_gate_hz=2_500.0,
    )

    glrt = next(row for row in rows if row["detector_method"] == "glrt64")
    assert len(observed_conditioning) == 1
    epoch, seed_cfo_hz, glrt_size = observed_conditioning[0]
    assert epoch == 73
    assert abs(seed_cfo_hz) < 1.0
    assert glrt_size == 4_096
    assert glrt["corrected_margin"] == 0.0
    assert glrt["conditioned_corrected_margin"] == 0.41
    assert glrt["conditioned_epoch_sample"] == 73
    assert "conditioned_corrected_margin" not in legacy_trajectory_replay_rows(rows)[0]


def test_conditioned_replay_accepts_dense_explicit_probe_starts(monkeypatch) -> None:
    class Reader:
        sample_rate_hz = 2_500_000

    trajectory = _trajectory("trajectory-dense", ("support-a", "support-b"))
    score = PilotMethodScore(
        PilotMethod.GLRT64,
        0.44,
        0.04,
        0.40,
        0.0,
        221_905.0 - 2 * _ALIAS_SPACING_HZ,
    )
    starts = (0, 25_000)
    detections = tuple(
        PilotProbeDetection(
            NumericalStatus.COMPLETE,
            start,
            start / Reader.sample_rate_hz,
            73,
            score.tracking_cfo_hz,
            (score,),
            None,
            None,
            "dense fixture",
        )
        for start in starts
    )
    observed_schedule: list[tuple[tuple[int, ...], int]] = []

    def explicit_batches(_iq, sample_starts, probe_samples):
        observed_schedule.append((sample_starts, probe_samples))
        yield tuple((start, np.ones(100, dtype=np.complex128)) for start in sample_starts)

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
        return next(item for item in detections if item.sample_start == sample_start)

    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback._iter_explicit_probe_batches",
        explicit_batches,
    )
    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.correct_polynomial_cfo",
        lambda samples, *_args, **_kwargs: samples,
    )
    monkeypatch.setattr("leo.analysis.starlink.trajectory_feedback.detect_pilot_methods", detect)
    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.conditioned_glrt64_score",
        lambda *_args, **_kwargs: score,
    )

    rows = replay_pilot_trajectories_at_detection_windows_with_conditioned_scores(
        Reader(),  # type: ignore[arg-type]
        detections,
        (("family", trajectory),),
        TrajectoryFeedbackConfig(maximum_outer_windows=1, maximum_workers=1),
        edge="lower",  # type: ignore[arg-type]
        alias_indices={trajectory.trajectory_id: -2},
        alias_spacing_hz=_ALIAS_SPACING_HZ,
        association_gate_hz=2_500.0,
        probe_samples=50_000,
    )

    assert observed_schedule == [(starts, 50_000)]
    assert tuple(row["sample_start"] for row in rows) == starts
    assert all(row["conditioned_corrected_margin"] == score.margin for row in rows)
