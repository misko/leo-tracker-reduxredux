"""Additive seeded multi-mode composition for the research PNT tracker.

V4 deliberately changes acquisition, not the continuous tracker.  The seeded
acquisition primitive retains discrete epoch/CFO audit proposals and this
module runs one fresh :func:`analyze_contiguous_pilot_pnt_kalman` instance for
every accepted mode.  Rejected proposals remain in the acquisition evidence
and never enter the tracker.  The tracker receives the unchanged
:class:`PilotPntKalmanConfigV3` policy with only the accepted mode's Doppler
rate substituted as its initial condition.  Acquisition recovery cannot alter
the per-frame gates or modulo-pi phase-lock qualification used by V3.

The result keeps three questions separate:

* ``acquisition`` owns pilot-presence, specificity, alias, and uniqueness
  decisions;
* ``numerical_status`` summarizes whether the accepted modes could be tracked;
* each mode's ``tracking.phase_lock_qualified`` remains the existing V3-core
  phase verdict.

This module is research-only.  It is re-exported as an explicit opt-in API but
is not connected to the Standard analyzer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from leo.analysis.qam.pilot_pnt_kalman import (
    PilotPntKalmanConfigV3,
    PilotPntKalmanResult,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.seeded_acquisition import (
    KnownPilotModeCandidate,
    KnownPilotModeSeed,
    SeededPilotAcquisitionConfig,
    SeededPilotAcquisitionResult,
    acquire_seeded_known_pilot_modes,
)
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, StarlinkEdge


@dataclass(frozen=True, slots=True)
class PilotPntKalmanConfigV4:
    """Independent seeded acquisition and unchanged phase-safe tracking policy.

    ``tracker_config`` supplies every V3 policy and threshold.  Each accepted
    mode replaces only its initial Doppler-rate state before entering a fresh
    core instance.
    """

    acquisition_config: SeededPilotAcquisitionConfig = field(
        default_factory=SeededPilotAcquisitionConfig
    )
    tracker_config: PilotPntKalmanConfigV3 = field(default_factory=PilotPntKalmanConfigV3)

    def __post_init__(self) -> None:
        if not isinstance(self.acquisition_config, SeededPilotAcquisitionConfig):
            raise ValueError("PNT Kalman V4 requires a seeded acquisition configuration")
        if not isinstance(self.tracker_config, PilotPntKalmanConfigV3):
            raise ValueError("PNT Kalman V4 requires a V3 tracker configuration")
        _validate_phase_safe_tracker(self.tracker_config)


@dataclass(frozen=True, slots=True)
class PilotPntKalmanV4ModeResult:
    """One accepted discrete acquisition mode and its independent local track."""

    mode: KnownPilotModeCandidate
    tracking: PilotPntKalmanResult

    @property
    def numerical_status(self) -> NumericalStatus:
        """Numerical outcome without interpreting acquisition or phase quality."""

        return self.tracking.status

    @property
    def phase_lock_qualified(self) -> bool:
        """Existing V3-core modulo-pi phase verdict for this mode."""

        return self.tracking.phase_lock_qualified


@dataclass(frozen=True, slots=True)
class PilotPntKalmanV4Result:
    """Research result with acquisition, numerical, and phase outcomes separated."""

    numerical_status: NumericalStatus
    acquisition: SeededPilotAcquisitionResult
    mode_results: tuple[PilotPntKalmanV4ModeResult, ...]
    complete_mode_count: int
    phase_lock_qualified_mode_count: int
    reason: str
    candidate_only: bool = True
    standard_pipeline: bool = False

    def __post_init__(self) -> None:
        complete_count = sum(
            row.numerical_status is NumericalStatus.COMPLETE for row in self.mode_results
        )
        phase_count = sum(row.phase_lock_qualified for row in self.mode_results)
        if self.complete_mode_count != complete_count:
            raise ValueError("V4 complete-mode count does not match per-mode outcomes")
        if self.phase_lock_qualified_mode_count != phase_count:
            raise ValueError("V4 phase-lock count does not match per-mode outcomes")
        if not self.candidate_only or self.standard_pipeline:
            raise ValueError("PNT Kalman V4 is candidate-only and outside Standard")


@dataclass(frozen=True, slots=True)
class PilotPntKalmanV4SegmentSeed:
    """Caller-qualified continuity arc with segment-local acquisition seeds."""

    start_sample: int
    stop_sample: int
    seed: KnownPilotModeSeed
    additional_seeds: tuple[KnownPilotModeSeed, ...] = ()

    def __post_init__(self) -> None:
        bounds = (self.start_sample, self.stop_sample)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in bounds):
            raise ValueError("V4 segment bounds must be integers")
        if self.start_sample < 0 or self.stop_sample <= self.start_sample:
            raise ValueError("V4 segment bounds must be nonempty and nonnegative")
        if not isinstance(self.seed, KnownPilotModeSeed):
            raise ValueError("V4 segment requires one primary known-pilot seed")
        if not isinstance(self.additional_seeds, tuple) or any(
            not isinstance(item, KnownPilotModeSeed) for item in self.additional_seeds
        ):
            raise ValueError("V4 segment additional seeds must be a seed tuple")
        identities = tuple(
            (item.branch_id, item.provenance_sha256) for item in (self.seed, *self.additional_seeds)
        )
        if len(set(identities)) != len(identities):
            raise ValueError("V4 segment seed branch/provenance identities must be unique")


@dataclass(frozen=True, slots=True)
class PilotPntKalmanV4SegmentResult:
    """One independently acquired and tracked caller-qualified continuity arc."""

    segment: PilotPntKalmanV4SegmentSeed
    result: PilotPntKalmanV4Result

    @property
    def numerical_status(self) -> NumericalStatus:
        return self.result.numerical_status


@dataclass(frozen=True, slots=True)
class PilotPntKalmanV4PiecewiseResult:
    """Aggregate of independent V4 filters separated by caller boundaries."""

    numerical_status: NumericalStatus
    segments: tuple[PilotPntKalmanV4SegmentResult, ...]
    complete_segment_count: int
    complete_mode_count: int
    phase_lock_qualified_mode_count: int
    reacquisition_count: int
    reason: str
    candidate_only: bool = True
    standard_pipeline: bool = False

    def __post_init__(self) -> None:
        expected_segments = sum(
            row.numerical_status is NumericalStatus.COMPLETE for row in self.segments
        )
        expected_modes = sum(row.result.complete_mode_count for row in self.segments)
        expected_phase = sum(row.result.phase_lock_qualified_mode_count for row in self.segments)
        if self.complete_segment_count != expected_segments:
            raise ValueError("piecewise V4 complete-segment count is inconsistent")
        if self.complete_mode_count != expected_modes:
            raise ValueError("piecewise V4 complete-mode count is inconsistent")
        if self.phase_lock_qualified_mode_count != expected_phase:
            raise ValueError("piecewise V4 phase-lock count is inconsistent")
        if self.reacquisition_count != max(0, len(self.segments) - 1):
            raise ValueError("piecewise V4 reacquisition count is inconsistent")
        if not self.candidate_only or self.standard_pipeline:
            raise ValueError("piecewise PNT Kalman V4 is candidate-only and outside Standard")


def analyze_contiguous_pilot_pnt_kalman_v4(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    seed: KnownPilotModeSeed,
    additional_seeds: tuple[KnownPilotModeSeed, ...] = (),
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
    expected_symbol_roll: int = 0,
    config: PilotPntKalmanConfigV4 | None = None,
) -> PilotPntKalmanV4Result:
    """Acquire bounded discrete modes, then track each with a fresh V3 core.

    The primary seed and any additional caller-qualified trajectory families
    are acquired together.  All accepted modes are attempted in acquisition
    order.  Neither a global
    acquisition verdict nor another mode's numerical/phase outcome suppresses
    an accepted mode's track attempt.  Rejected retained proposals remain
    audit evidence only.  No state, covariance, channel reference, or
    bootstrap history is shared between modes.
    """

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("PNT Kalman V4 samples must be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample rate must be finite and positive")
    if (
        not math.isfinite(maximum_residual_cfo_hz)
        or maximum_residual_cfo_hz <= 0.0
        or maximum_residual_cfo_hz > 0.5 / OFDM_SYMBOL_DURATION_S
    ):
        raise ValueError("maximum residual CFO must be positive and within symbol Nyquist")
    if isinstance(expected_symbol_roll, bool) or not isinstance(expected_symbol_roll, int):
        raise ValueError("expected symbol roll must be an integer")

    settings = config or PilotPntKalmanConfigV4()
    if not isinstance(settings, PilotPntKalmanConfigV4):
        raise ValueError("config must be a PilotPntKalmanConfigV4")
    _validate_phase_safe_tracker(settings.tracker_config)

    acquisition = acquire_seeded_known_pilot_modes(
        values,
        sample_rate_hz,
        seed=seed,
        additional_seeds=additional_seeds,
        edge=selected_edge,
        expected_symbol_roll=expected_symbol_roll,
        config=settings.acquisition_config,
    )
    rows = tuple(
        PilotPntKalmanV4ModeResult(
            mode=mode,
            tracking=analyze_contiguous_pilot_pnt_kalman(
                values,
                sample_rate_hz,
                epoch_sample=mode.epoch_sample,
                initial_absolute_cfo_hz=mode.absolute_cfo_hz,
                edge=selected_edge,
                maximum_residual_cfo_hz=maximum_residual_cfo_hz,
                expected_symbol_roll=expected_symbol_roll,
                config=_tracker_config_for_mode(settings.tracker_config, mode),
            ),
        )
        for mode in acquisition.accepted_modes
    )
    numerical_status, reason = _aggregate_numerical_outcome(acquisition, rows)
    return PilotPntKalmanV4Result(
        numerical_status=numerical_status,
        acquisition=acquisition,
        mode_results=rows,
        complete_mode_count=sum(row.numerical_status is NumericalStatus.COMPLETE for row in rows),
        phase_lock_qualified_mode_count=sum(row.phase_lock_qualified for row in rows),
        reason=reason,
    )


def analyze_piecewise_pilot_pnt_kalman_v4(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    segments: tuple[PilotPntKalmanV4SegmentSeed, ...],
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
    expected_symbol_roll: int = 0,
    config: PilotPntKalmanConfigV4 | None = None,
) -> PilotPntKalmanV4PiecewiseResult:
    """Run fresh V4 acquisition and tracking on caller-qualified arcs.

    Segment seeds and epochs are local to their sliced arc.  Boundaries are
    supplied by the caller: this function neither discovers change points nor
    transfers a state, covariance, channel reference, or bootstrap history
    between segments.
    """

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("piecewise PNT Kalman V4 samples must be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample rate must be finite and positive")
    arcs = tuple(segments)
    if not arcs:
        raise ValueError("piecewise PNT Kalman V4 requires at least one segment")
    if any(not isinstance(segment, PilotPntKalmanV4SegmentSeed) for segment in arcs):
        raise ValueError("piecewise PNT Kalman V4 segments must use V4 segment seeds")
    previous_stop = 0
    for segment in arcs:
        if segment.start_sample < previous_stop:
            raise ValueError("piecewise PNT Kalman V4 segments must be ordered and nonoverlapping")
        if segment.stop_sample > values.size:
            raise ValueError("piecewise PNT Kalman V4 segment extends beyond the sample window")
        previous_stop = segment.stop_sample

    settings = config or PilotPntKalmanConfigV4()
    if not isinstance(settings, PilotPntKalmanConfigV4):
        raise ValueError("config must be a PilotPntKalmanConfigV4")
    rows = tuple(
        PilotPntKalmanV4SegmentResult(
            segment=segment,
            result=analyze_contiguous_pilot_pnt_kalman_v4(
                values[segment.start_sample : segment.stop_sample],
                sample_rate_hz,
                seed=segment.seed,
                additional_seeds=segment.additional_seeds,
                edge=selected_edge,
                maximum_residual_cfo_hz=maximum_residual_cfo_hz,
                expected_symbol_roll=expected_symbol_roll,
                config=settings,
            ),
        )
        for segment in arcs
    )
    complete_segment_count = sum(row.numerical_status is NumericalStatus.COMPLETE for row in rows)
    if complete_segment_count == len(rows):
        numerical_status = NumericalStatus.COMPLETE
        reason = "every caller-qualified continuity arc completed an independent V4 analysis"
    elif complete_segment_count:
        numerical_status = NumericalStatus.INSUFFICIENT
        reason = "only a subset of caller-qualified continuity arcs completed V4 analysis"
    elif any(row.numerical_status is NumericalStatus.INSUFFICIENT for row in rows):
        numerical_status = NumericalStatus.INSUFFICIENT
        reason = "caller-qualified continuity arcs lacked sufficient V4 evidence"
    else:
        numerical_status = NumericalStatus.NO_RESULT
        reason = "no caller-qualified continuity arc produced a V4 track"
    return PilotPntKalmanV4PiecewiseResult(
        numerical_status=numerical_status,
        segments=rows,
        complete_segment_count=complete_segment_count,
        complete_mode_count=sum(row.result.complete_mode_count for row in rows),
        phase_lock_qualified_mode_count=sum(
            row.result.phase_lock_qualified_mode_count for row in rows
        ),
        reacquisition_count=max(0, len(rows) - 1),
        reason=reason,
    )


def _validate_phase_safe_tracker(config: PilotPntKalmanConfigV3) -> None:
    policies = (
        config.independent_phase_reacquisition,
        config.initial_full_frame_epoch_acquisition,
        config.decouple_phase_from_frequency,
    )
    if not all(policies):
        raise ValueError("PNT Kalman V4 requires the unchanged phase-safe V3 tracker policy")


def _tracker_config_for_mode(
    config: PilotPntKalmanConfigV3,
    mode: KnownPilotModeCandidate,
) -> PilotPntKalmanConfigV3:
    """Apply only a mode-specific initial rate to the frozen V3 policy."""

    selected = replace(
        config,
        initial_doppler_rate_hz_s=float(mode.doppler_rate_hz_s),
    )
    _validate_phase_safe_tracker(selected)
    return selected


def _aggregate_numerical_outcome(
    acquisition: SeededPilotAcquisitionResult,
    rows: tuple[PilotPntKalmanV4ModeResult, ...],
) -> tuple[NumericalStatus, str]:
    if not rows:
        status = (
            NumericalStatus.INSUFFICIENT
            if acquisition.status is NumericalStatus.INSUFFICIENT
            else NumericalStatus.NO_RESULT
        )
        return status, "seeded acquisition accepted no mode for local tracking"

    complete_count = sum(row.numerical_status is NumericalStatus.COMPLETE for row in rows)
    if complete_count == len(rows):
        return (
            NumericalStatus.COMPLETE,
            "every accepted acquisition mode completed an independent phase-safe track",
        )
    if complete_count:
        return (
            NumericalStatus.INSUFFICIENT,
            "only a subset of accepted acquisition modes completed local tracking",
        )
    if any(row.numerical_status is NumericalStatus.INSUFFICIENT for row in rows):
        return (
            NumericalStatus.INSUFFICIENT,
            "accepted acquisition modes lacked sufficient local tracking data",
        )
    return NumericalStatus.NO_RESULT, "no accepted acquisition mode produced a local track"


__all__ = [
    "PilotPntKalmanConfigV4",
    "PilotPntKalmanV4ModeResult",
    "PilotPntKalmanV4PiecewiseResult",
    "PilotPntKalmanV4Result",
    "PilotPntKalmanV4SegmentResult",
    "PilotPntKalmanV4SegmentSeed",
    "analyze_contiguous_pilot_pnt_kalman_v4",
    "analyze_piecewise_pilot_pnt_kalman_v4",
]
