"""Known Qin-pilot QAM metrics with inverse-noise receiver combining.

The numerical kernel is a clean, infrastructure-free port of
``leo_tracker/radio/beacon/decode.py`` at leo-tracker commit
0bb80d14759fd8496b74e7d3219a690be18565a6 and is cross-checked against
``starlink_pilot_constellation.py`` at leo-tracker-redux commit
b2b8827832715f7cd45196cd08919bcc5dd2a3f0. These metrics cover known
synchronization symbols, never user payload.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import cast

import numpy as np

from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)


@dataclass(frozen=True, slots=True)
class PilotQamMetrics:
    hard_symbol_accuracy: float
    rms_evm: float
    noise_variance: float
    soft_mean_confidence: float
    soft_mean_expected_probability: float
    frame_count: int
    effective_frame_count: float


@dataclass(frozen=True, slots=True)
class PilotQamResult:
    status: NumericalStatus
    metrics: PilotQamMetrics | None
    absolute_cfo_hz: float | None
    residual_cfo_refinement_hz: float | None
    reason: str
    known_symbols_only: bool = True
    candidate_only: bool = True
    expected: np.ndarray = field(default_factory=lambda: np.empty((0, 8)), repr=False)
    equalized: np.ndarray = field(default_factory=lambda: np.empty((0, 8)), repr=False)
    frame_equalized: np.ndarray = field(default_factory=lambda: np.empty((0, 300, 8)), repr=False)


@dataclass(frozen=True, slots=True)
class CombinedPilotQamResult:
    status: NumericalStatus
    metrics: PilotQamMetrics | None
    receiver_weights: tuple[float, ...]
    reason: str
    known_symbols_only: bool = True
    candidate_only: bool = True
    equalized: np.ndarray = field(default_factory=lambda: np.empty((0, 8)), repr=False)


@dataclass(frozen=True, slots=True)
class PilotPhaseSlopeFrame:
    """One frame-local edge-pilot carrier estimate.

    ``phase_at_reference_rad`` is measured against a channel response estimated
    from this result's frames.  It is diagnostic only: callers must not unwrap
    it between frames without separately proving carrier continuity.
    """

    frame_index: int
    frame_start_sample: int
    reference_sample: float
    residual_cfo_hz: float
    absolute_cfo_hz: float
    frequency_uncertainty_hz: float
    phase_at_reference_rad: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    phase_residual_rms_rad: float
    symbol_count: int = 300


@dataclass(frozen=True, slots=True)
class PilotPhaseSlopeResult:
    """Research-only per-frame Doppler evidence from all known edge pilots."""

    status: NumericalStatus
    frames: tuple[PilotPhaseSlopeFrame, ...]
    aggregate_residual_cfo_hz: float | None
    aggregate_absolute_cfo_hz: float | None
    reason: str
    known_symbols_only: bool = True
    candidate_only: bool = True
    phase_continuity_assumed: bool = False


@dataclass(frozen=True, slots=True)
class PilotFrameCfoConfig:
    """Fail-closed gates for one acquisition-bound Qin frame CFO.

    The residual search refines an absolute-CFO alias supplied by acquisition;
    this config cannot select a different OFDM alias or timing lattice.
    """

    residual_half_width_hz: float = 2_000.0
    minimum_exact_coherence: float = 0.02
    minimum_coherence_margin: float = 0.0
    maximum_even_odd_disagreement_hz: float = 100.0
    maximum_timing_spread_hz: float = 50.0
    maximum_half_frame_z: float = 4.0
    maximum_tone_deletion_shift_hz: float = 75.0

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.residual_half_width_hz)
            or self.residual_half_width_hz <= 0.0
            or self.residual_half_width_hz > 0.5 / OFDM_SYMBOL_DURATION_S
        ):
            raise ValueError("residual CFO half width is unsupported")
        if (
            not math.isfinite(self.minimum_exact_coherence)
            or not 0.0 <= self.minimum_exact_coherence <= 1.0
        ):
            raise ValueError("minimum exact coherence must lie in [0, 1]")
        if (
            not math.isfinite(self.minimum_coherence_margin)
            or not -1.0 <= self.minimum_coherence_margin <= 1.0
        ):
            raise ValueError("minimum coherence margin must lie in [-1, 1]")
        positive = (
            self.maximum_even_odd_disagreement_hz,
            self.maximum_timing_spread_hz,
            self.maximum_half_frame_z,
            self.maximum_tone_deletion_shift_hz,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("frame-CFO gates must be finite and positive")


@dataclass(frozen=True, slots=True)
class PilotFrameCfoEstimate:
    """One independently qualified, acquisition-bound Qin frame CFO.

    A complete result retains its measurement even when a diagnostic gate
    rejects it.  ``measurement_supported`` is the sole signal that the point
    is eligible for a downstream Doppler fit.
    """

    status: NumericalStatus
    measurement_supported: bool
    rejection_reasons: tuple[str, ...]
    frame_start_sample: int
    reference_sample: float
    residual_cfo_hz: float | None
    absolute_cfo_hz: float | None
    frequency_uncertainty_hz: float | None
    exact_coherence: float | None
    control_coherence: float | None
    coherence_margin: float | None
    even_residual_cfo_hz: float | None
    odd_residual_cfo_hz: float | None
    even_odd_disagreement_hz: float | None
    timing_spread_hz: float | None
    half_frame_difference_z: float | None
    tone_deletion_spread_hz: float | None
    search_boundary: bool
    known_symbols_only: bool = True
    candidate_only: bool = True


@dataclass(frozen=True, slots=True)
class PilotFrameCfoSplitValidation:
    """Even-trained, odd-validated CFO evidence for one acquired frame.

    Membership in the validation cohort is determined only by the even Qin
    symbols.  The odd estimate is retained solely as a held-out response; it
    never changes ``training_supported``.  This companion is diagnostic and
    does not replace :class:`PilotFrameCfoEstimate` as the qualified point.
    """

    status: NumericalStatus
    training_supported: bool
    training_rejection_reasons: tuple[str, ...]
    frame_start_sample: int
    reference_sample: float
    even_residual_cfo_hz: float | None
    odd_residual_cfo_hz: float | None
    even_absolute_cfo_hz: float | None
    odd_absolute_cfo_hz: float | None
    even_frequency_uncertainty_hz: float | None
    odd_frequency_uncertainty_hz: float | None
    even_exact_coherence: float | None
    even_control_coherence: float | None
    even_coherence_margin: float | None
    even_search_boundary: bool
    odd_search_boundary: bool
    known_symbols_only: bool = True
    candidate_only: bool = True


@dataclass(frozen=True, slots=True)
class PilotFrameCfoLikelihoodProfile:
    """Sampled even/odd Qin profile likelihoods for one acquired frame.

    Frequencies are residuals relative to the supplied acquisition CFO.  The
    exact and roll-control curves in each parity fold share one additive
    normalization, so their differences remain meaningful.  Even and odd
    folds have separate normalizations and must not be subtracted directly.

    The embedded split validation is the point-estimate companion.  Its even
    fold alone determines training membership; none of the odd or control
    profile values can change that decision.
    """

    status: NumericalStatus
    split_validation: PilotFrameCfoSplitValidation
    residual_grid_hz: np.ndarray = field(repr=False)
    even_exact_log_likelihood: np.ndarray = field(repr=False)
    even_control_log_likelihood: np.ndarray = field(repr=False)
    odd_exact_log_likelihood: np.ndarray = field(repr=False)
    odd_control_log_likelihood: np.ndarray = field(repr=False)
    likelihood_model: str = "per-frame common-variance complex Gaussian"
    known_symbols_only: bool = True
    candidate_only: bool = True
    odd_symbols_influenced_fit: bool = False


@dataclass(frozen=True, slots=True)
class PilotFrameComplexFold:
    """One parity fold's frame-local complex sufficient statistic.

    ``channel_vector`` is evaluated at ``reference_sample`` in the raw
    capture-sample carrier-phase gauge.  It is therefore invariant to the
    acquisition NCO seed and to the local origin of the guarded slice.  The
    vector still contains the receiver/channel phase and is not an absolute
    transmit phase or timing observable.
    """

    residual_cfo_hz: float
    absolute_cfo_hz: float
    frequency_uncertainty_hz: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    phase_residual_rms_rad: float
    search_boundary: bool
    channel_vector: np.ndarray = field(repr=False)


@dataclass(frozen=True, slots=True)
class PilotFrameComplexSplitObservation:
    """Even-trained/odd-held-out complex evidence from one acquired frame.

    Only the even fold influences ``training_supported``.  The odd fold is a
    response for leakage-safe validation and must not select frames, aliases,
    resets, or iteration counts.  Carrier phase is modulo pi for these pilots,
    and timing inferred across the tones is receiver-relative to a separately
    qualified local channel reference.
    """

    status: NumericalStatus
    training_supported: bool
    training_rejection_reasons: tuple[str, ...]
    frame_start_sample: int
    reference_sample: float
    even: PilotFrameComplexFold | None
    odd: PilotFrameComplexFold | None
    known_symbols_only: bool = True
    candidate_only: bool = True
    carrier_phase_period_rad: float = math.pi
    absolute_carrier_phase_resolved: bool = False
    frame_timing_is_receiver_relative: bool = True


@dataclass(frozen=True, slots=True)
class _FrameSlopeFit:
    residual_cfo_hz: float
    frequency_uncertainty_hz: float
    exact_coherence: float
    control_coherence: float
    phase_residual_rms_rad: float
    channel_vector: np.ndarray = field(repr=False)


def analyze_pilot_qam(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    epoch_sample: int,
    absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
) -> PilotQamResult:
    """Demodulate and cross-fit all complete known-pilot frames."""

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if epoch_sample < 0 or not math.isfinite(absolute_cfo_hz):
        raise ValueError("epoch must be nonnegative and CFO finite")
    minimum_rate_hz = 8 * 234_375.0
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz:.0f} Hz")
    starts = _complete_frame_starts(values.size, sample_rate_hz, epoch_sample)
    if not starts:
        return _empty(
            NumericalStatus.INSUFFICIENT,
            "window contains no complete known-pilot frame",
        )
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty(NumericalStatus.NO_RESULT, "window has zero signal energy")

    demodulator = _KnownPilotDemodulator(values, sample_rate_hz, selected_edge, absolute_cfo_hz)
    pilots = np.asarray([demodulator.frame(start) for start in starts], dtype=np.complex64)
    expected = qin_edge_pilot_symbols(selected_edge)
    residual_cfo_hz = _estimate_residual_cfo(pilots, expected)
    pilot_times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_time_s = float(np.mean(pilot_times_s))
    pilots *= np.exp(-2j * np.pi * residual_cfo_hz * (pilot_times_s - reference_time_s))[
        None, :, None
    ]

    frame_match = np.sum(pilots * np.conj(expected)[None, :, :], axis=(1, 2))
    frame_phase = np.angle(frame_match)
    aligned = pilots * np.exp(-1j * frame_phase)[:, None, None]
    frame_energy = np.sum(np.abs(pilots) ** 2, axis=(1, 2))
    frame_quality = np.abs(frame_match) ** 2 / np.maximum(frame_energy, 1e-20)
    positive = frame_quality[frame_quality > 0]
    if positive.size:
        frame_quality = np.minimum(frame_quality, 4 * np.median(positive))
    total_quality = float(np.sum(frame_quality))
    frame_weights = (
        frame_quality / total_quality
        if total_quality > 0
        else np.full(len(starts), 1 / len(starts))
    )
    stacked = np.sum(aligned * frame_weights[:, None, None], axis=0)
    equalized = _cross_fit_equalize(stacked, expected)
    full_channel = np.mean(stacked * np.conj(expected), axis=0)
    frame_equalized = (
        aligned
        / np.where(
            np.abs(full_channel) > 1e-20,
            full_channel,
            np.complex64(1),
        )[None, None, :]
    )
    metric_values = _metric_values(equalized, expected)
    metrics = PilotQamMetrics(
        hard_symbol_accuracy=metric_values[0],
        rms_evm=metric_values[1],
        noise_variance=metric_values[2],
        soft_mean_confidence=metric_values[3],
        soft_mean_expected_probability=metric_values[4],
        frame_count=len(starts),
        effective_frame_count=float(1 / np.sum(frame_weights**2)),
    )
    return PilotQamResult(
        NumericalStatus.COMPLETE,
        metrics,
        float(absolute_cfo_hz + residual_cfo_hz),
        residual_cfo_hz,
        "known synchronization-pilot quality; payload was not decoded",
        expected=_freeze(expected),
        equalized=_freeze(equalized),
        frame_equalized=_freeze(frame_equalized),
    )


def analyze_pilot_phase_slope(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    epoch_sample: int,
    absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
) -> PilotPhaseSlopeResult:
    """Estimate one independent carrier-frequency slope per complete frame.

    All 300 known pilot symbols and all eight edge subcarriers contribute to
    each estimate.  The likelihood maximizes over a separate complex channel
    coefficient for every subcarrier, so a common frame phase is a nuisance
    parameter rather than a continuity assumption.  A 17-symbol-rolled Qin
    sequence is evaluated through the identical search as the negative control.
    """

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if epoch_sample < 0 or not math.isfinite(absolute_cfo_hz):
        raise ValueError("epoch must be nonnegative and CFO finite")
    if not math.isfinite(maximum_residual_cfo_hz) or maximum_residual_cfo_hz <= 0:
        raise ValueError("maximum residual CFO must be finite and positive")
    if maximum_residual_cfo_hz > 0.5 / OFDM_SYMBOL_DURATION_S:
        raise ValueError("maximum residual CFO exceeds the symbol-rate Nyquist limit")
    minimum_rate_hz = 8 * 234_375.0
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz:.0f} Hz")
    starts = _complete_frame_starts(values.size, sample_rate_hz, epoch_sample)
    if not starts:
        return _empty_phase_slope(
            NumericalStatus.INSUFFICIENT,
            "window contains no complete known-pilot frame",
        )
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty_phase_slope(NumericalStatus.NO_RESULT, "window has zero signal energy")

    demodulator = _KnownPilotDemodulator(
        values,
        sample_rate_hz,
        selected_edge,
        absolute_cfo_hz,
    )
    pilots = np.asarray([demodulator.frame(start) for start in starts], dtype=np.complex128)
    expected = qin_edge_pilot_symbols(selected_edge)
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    return _estimate_phase_slope_frames(
        pilots,
        expected,
        control,
        starts,
        sample_rate_hz=sample_rate_hz,
        absolute_cfo_hz=absolute_cfo_hz,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
    )


def estimate_edge_pilot_frame_cfo(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    frame_start_sample: int,
    acquisition_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    config: PilotFrameCfoConfig | None = None,
) -> PilotFrameCfoEstimate:
    """Estimate and qualify CFO in one already acquired 1.333 ms frame.

    ``samples`` is exactly one compact guarded slice: one raw sample before the
    nominal frame, the complete frame content, and one sample after it.
    ``frame_start_sample`` is the nominal frame's absolute recording coordinate,
    not an index into this slice.  The guards make timing sensitivity observed
    rather than optional while retaining an auditable global frame coordinate.
    """

    values = np.asarray(samples, dtype=np.complex128)
    settings = config or PilotFrameCfoConfig()
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("samples must be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    minimum_rate_hz = 8 * 234_375.0
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz:.0f} Hz")
    if not isinstance(frame_start_sample, (int, np.integer)):
        raise ValueError("frame start must be an integer sample")
    if not math.isfinite(acquisition_absolute_cfo_hz):
        raise ValueError("acquisition absolute CFO must be finite")
    frame_start = int(frame_start_sample)
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if frame_start < 1:
        raise ValueError("absolute frame start must leave a preceding recording sample")
    if values.size != frame_content + 2:
        raise ValueError("samples must be exactly one frame with one-sample guards")

    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    reference_sample = float(frame_start + reference_offset_s * sample_rate_hz)
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty_frame_cfo(
            NumericalStatus.NO_RESULT,
            "zero_pilot_energy",
            frame_start,
            reference_sample,
        )

    demodulator = _KnownPilotDemodulator(
        values,
        sample_rate_hz,
        selected_edge,
        acquisition_absolute_cfo_hz,
    )
    pilots = (
        demodulator.frame(0),
        demodulator.frame(1),
        demodulator.frame(2),
    )
    expected = qin_edge_pilot_symbols(selected_edge)
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    return _estimate_edge_pilot_frame_cfo_from_cubes(
        pilots,
        expected,
        control,
        frame_start_sample=frame_start,
        reference_sample=reference_sample,
        acquisition_absolute_cfo_hz=acquisition_absolute_cfo_hz,
        config=settings,
    )


def estimate_edge_pilot_frame_cfo_split_validation(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    frame_start_sample: int,
    acquisition_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    config: PilotFrameCfoConfig | None = None,
) -> PilotFrameCfoSplitValidation:
    """Train on even Qin symbols and retain odd symbols for validation only."""

    values = np.asarray(samples, dtype=np.complex128)
    settings = config or PilotFrameCfoConfig()
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("samples must be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    minimum_rate_hz = 8 * 234_375.0
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz:.0f} Hz")
    if not isinstance(frame_start_sample, (int, np.integer)):
        raise ValueError("frame start must be an integer sample")
    if not math.isfinite(acquisition_absolute_cfo_hz):
        raise ValueError("acquisition absolute CFO must be finite")
    frame_start = int(frame_start_sample)
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if frame_start < 1:
        raise ValueError("absolute frame start must leave a preceding recording sample")
    if values.size != frame_content + 2:
        raise ValueError("samples must be exactly one frame with one-sample guards")

    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    reference_sample = float(frame_start + reference_offset_s * sample_rate_hz)
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty_frame_cfo_split(frame_start, reference_sample)

    demodulator = _KnownPilotDemodulator(
        values,
        sample_rate_hz,
        selected_edge,
        acquisition_absolute_cfo_hz,
    )
    return _estimate_edge_pilot_frame_cfo_split_from_cube(
        demodulator.frame(1),
        qin_edge_pilot_symbols(selected_edge),
        qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL),
        frame_start_sample=frame_start,
        reference_sample=reference_sample,
        acquisition_absolute_cfo_hz=acquisition_absolute_cfo_hz,
        config=settings,
    )


def evaluate_edge_pilot_frame_cfo_likelihood(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    frame_start_sample: int,
    acquisition_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    residual_grid_hz: np.ndarray,
    config: PilotFrameCfoConfig | None = None,
) -> PilotFrameCfoLikelihoodProfile:
    """Evaluate an acquisition-bound CFO profile without joining frame phase.

    One unknown complex gain per pilot tone is analytically profiled out at
    every requested frequency.  This preserves each frame's complete local
    frequency evidence for a later noncoherent rate fit while allowing an odd
    Qin validation lane that cannot influence the even-trained trajectory.
    """

    values = np.asarray(samples, dtype=np.complex128)
    grid = np.asarray(residual_grid_hz, dtype=float)
    settings = config or PilotFrameCfoConfig()
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("samples must be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    minimum_rate_hz = 8 * 234_375.0
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz:.0f} Hz")
    if not isinstance(frame_start_sample, (int, np.integer)):
        raise ValueError("frame start must be an integer sample")
    if not math.isfinite(acquisition_absolute_cfo_hz):
        raise ValueError("acquisition absolute CFO must be finite")
    if grid.ndim != 1 or grid.size < 3 or not np.all(np.isfinite(grid)):
        raise ValueError("residual CFO grid must contain at least three finite values")
    if np.any(np.diff(grid) <= 0.0):
        raise ValueError("residual CFO grid must be strictly increasing")
    if grid[0] < -settings.residual_half_width_hz or grid[-1] > settings.residual_half_width_hz:
        raise ValueError("residual CFO grid exceeds the configured acquisition basin")
    frame_start = int(frame_start_sample)
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if frame_start < 1:
        raise ValueError("absolute frame start must leave a preceding recording sample")
    if values.size != frame_content + 2:
        raise ValueError("samples must be exactly one frame with one-sample guards")

    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    reference_sample = float(frame_start + reference_offset_s * sample_rate_hz)
    empty_split = _empty_frame_cfo_split(frame_start, reference_sample)
    empty = _freeze(np.empty(0, dtype=float))
    pilots = _KnownPilotDemodulator(
        values,
        sample_rate_hz,
        selected_edge,
        acquisition_absolute_cfo_hz,
    ).frame(1)
    if float(np.sum(np.abs(pilots[::2]) ** 2)) <= np.finfo(float).tiny:
        return PilotFrameCfoLikelihoodProfile(
            status=NumericalStatus.NO_RESULT,
            split_validation=empty_split,
            residual_grid_hz=_freeze(grid.copy()),
            even_exact_log_likelihood=empty,
            even_control_log_likelihood=empty,
            odd_exact_log_likelihood=empty,
            odd_control_log_likelihood=empty,
        )

    expected = qin_edge_pilot_symbols(selected_edge)
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    split = _estimate_edge_pilot_frame_cfo_split_from_cube(
        pilots,
        expected,
        control,
        frame_start_sample=frame_start,
        reference_sample=reference_sample,
        acquisition_absolute_cfo_hz=acquisition_absolute_cfo_hz,
        config=settings,
    )
    exact = pilots * np.conj(expected)
    null = pilots * np.conj(control)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)

    profiles: list[np.ndarray] = []
    for indexes in (slice(0, None, 2), slice(1, None, 2)):
        exact_profile = _profile_log_likelihood(exact[indexes], times_s[indexes], grid)
        control_profile = _profile_log_likelihood(null[indexes], times_s[indexes], grid)
        common_maximum = max(float(np.max(exact_profile)), float(np.max(control_profile)))
        profiles.extend(
            (
                _freeze(exact_profile - common_maximum),
                _freeze(control_profile - common_maximum),
            )
        )
    return PilotFrameCfoLikelihoodProfile(
        status=NumericalStatus.COMPLETE,
        split_validation=split,
        residual_grid_hz=_freeze(grid.copy()),
        even_exact_log_likelihood=profiles[0],
        even_control_log_likelihood=profiles[1],
        odd_exact_log_likelihood=profiles[2],
        odd_control_log_likelihood=profiles[3],
    )


def estimate_edge_pilot_frame_complex_split(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    frame_start_sample: int,
    acquisition_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    config: PilotFrameCfoConfig | None = None,
) -> PilotFrameComplexSplitObservation:
    """Return even/odd complex folds for iterative phase/rate research.

    The acquisition result remains authoritative for the frame epoch and CFO
    alias.  This function independently profiles one frame's residual CFO and
    eight complex tone gains.  Its channel vectors use a raw capture-sample
    phase gauge, but callers must still treat phase as a per-frame nuisance
    until continuity and a local channel reference are separately qualified.
    """

    values = np.asarray(samples, dtype=np.complex128)
    settings = config or PilotFrameCfoConfig()
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("samples must be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    minimum_rate_hz = 8 * 234_375.0
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz:.0f} Hz")
    if not isinstance(frame_start_sample, (int, np.integer)):
        raise ValueError("frame start must be an integer sample")
    if not math.isfinite(acquisition_absolute_cfo_hz):
        raise ValueError("acquisition absolute CFO must be finite")
    frame_start = int(frame_start_sample)
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if frame_start < 1:
        raise ValueError("absolute frame start must leave a preceding recording sample")
    if values.size != frame_content + 2:
        raise ValueError("samples must be exactly one frame with one-sample guards")

    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    reference_sample = float(frame_start + reference_offset_s * sample_rate_hz)
    pilots = _KnownPilotDemodulator(
        values,
        sample_rate_hz,
        selected_edge,
        acquisition_absolute_cfo_hz,
    ).frame(1)
    if float(np.sum(np.abs(pilots[::2]) ** 2)) <= np.finfo(float).tiny:
        return _empty_frame_complex_split(frame_start, reference_sample)
    expected = qin_edge_pilot_symbols(selected_edge)
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    exact = pilots * np.conj(expected)
    null = pilots * np.conj(control)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    even_fit = _fit_phase_slope_frame(
        exact[::2],
        null[::2],
        times_s[::2],
        maximum_residual_cfo_hz=settings.residual_half_width_hz,
    )
    odd_fit = _fit_phase_slope_frame(
        exact[1::2],
        null[1::2],
        times_s[1::2],
        maximum_residual_cfo_hz=settings.residual_half_width_hz,
    )

    # `_KnownPilotDemodulator` sees the guarded slice's local coordinates.
    # Restoring the acquisition-NCO phase at the local reference coordinate
    # puts the fitted vector in the raw capture-sample gauge.  This deliberately
    # retains the physical/receiver carrier phase while removing slice-origin
    # and acquisition-seed conventions.
    local_reference_sample = 1.0 + reference_offset_s * sample_rate_hz
    phase_cycles = math.remainder(
        acquisition_absolute_cfo_hz * local_reference_sample / sample_rate_hz,
        1.0,
    )
    capture_gauge = np.exp(2j * np.pi * phase_cycles)
    boundary_tolerance_hz = max(0.05, 1e-6 * settings.residual_half_width_hz)

    def fold(fit: _FrameSlopeFit) -> PilotFrameComplexFold:
        boundary = bool(
            abs(abs(fit.residual_cfo_hz) - settings.residual_half_width_hz) <= boundary_tolerance_hz
        )
        return PilotFrameComplexFold(
            residual_cfo_hz=float(fit.residual_cfo_hz),
            absolute_cfo_hz=float(acquisition_absolute_cfo_hz + fit.residual_cfo_hz),
            frequency_uncertainty_hz=float(fit.frequency_uncertainty_hz),
            exact_coherence=float(fit.exact_coherence),
            control_coherence=float(fit.control_coherence),
            coherence_margin=float(fit.exact_coherence - fit.control_coherence),
            phase_residual_rms_rad=float(fit.phase_residual_rms_rad),
            search_boundary=boundary,
            channel_vector=_freeze(fit.channel_vector * capture_gauge),
        )

    even = fold(even_fit)
    odd = fold(odd_fit)
    rejections = []
    if even.exact_coherence < settings.minimum_exact_coherence:
        rejections.append("even_exact_coherence_below_minimum")
    if even.coherence_margin < settings.minimum_coherence_margin:
        rejections.append("even_coherence_margin_below_minimum")
    if even.search_boundary:
        rejections.append("even_search_boundary")
    return PilotFrameComplexSplitObservation(
        status=NumericalStatus.COMPLETE,
        training_supported=not rejections,
        training_rejection_reasons=tuple(rejections),
        frame_start_sample=frame_start,
        reference_sample=reference_sample,
        even=even,
        odd=odd,
    )


def combine_receiver_qam(receivers: tuple[PilotQamResult, ...]) -> CombinedPilotQamResult:
    """Inverse-noise combine independently equalized receiver evidence."""

    if len(receivers) < 2:
        return CombinedPilotQamResult(
            NumericalStatus.INSUFFICIENT,
            None,
            (),
            "at least two receiver results are required for combining",
        )
    if any(
        item.status is not NumericalStatus.COMPLETE or item.metrics is None for item in receivers
    ):
        return CombinedPilotQamResult(
            NumericalStatus.NO_RESULT,
            None,
            (),
            "every receiver must have complete QAM evidence",
        )
    first_shape = receivers[0].equalized.shape
    if any(item.equalized.shape != first_shape for item in receivers):
        raise ValueError("receiver equalized symbol shapes differ")
    expected = receivers[0].expected
    if any(not np.array_equal(item.expected, expected) for item in receivers[1:]):
        raise ValueError("receiver expected pilot matrices differ")
    noise = np.asarray(
        [max(cast(PilotQamMetrics, item.metrics).noise_variance, 1e-6) for item in receivers]
    )
    weights = (1 / noise) / np.sum(1 / noise)
    equalized = sum(weights[index] * item.equalized for index, item in enumerate(receivers))
    values = _metric_values(equalized, expected)
    frame_count = min(item.frame_equalized.shape[0] for item in receivers)
    metrics = PilotQamMetrics(
        hard_symbol_accuracy=values[0],
        rms_evm=values[1],
        noise_variance=values[2],
        soft_mean_confidence=values[3],
        soft_mean_expected_probability=values[4],
        frame_count=frame_count,
        effective_frame_count=float(frame_count),
    )
    return CombinedPilotQamResult(
        NumericalStatus.COMPLETE,
        metrics,
        tuple(float(value) for value in weights),
        "inverse-noise combination of independently equalized known pilots",
        equalized=_freeze(equalized),
    )


class _KnownPilotDemodulator:
    def __init__(
        self,
        samples: np.ndarray,
        sample_rate_hz: float,
        edge: StarlinkEdge,
        absolute_cfo_hz: float,
    ) -> None:
        self._samples = samples
        self._rate = sample_rate_hz
        self._cfo = absolute_cfo_hz
        self._edge = edge

    def frame(self, frame_start: int) -> np.ndarray:
        result = np.empty((300, 8), dtype=np.complex128)
        for positions, relative, solves in _known_pilot_layout(float(self._rate), self._edge):
            absolute = frame_start + relative
            values = np.asarray(self._samples[absolute], dtype=np.complex128)
            values *= np.exp(-2j * np.pi * self._cfo * absolute / self._rate)
            result[positions] = np.einsum("sfc,sc->sf", solves, values, optimize=False)
        return result


@lru_cache(maxsize=16)
def _known_pilot_layout(
    sample_rate_hz: float,
    edge: StarlinkEdge,
) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray], ...]:
    """Group symbol solves by sample count for bounded vectorized demodulation."""

    symbols = np.arange(2, 302)
    starts = np.rint(symbols * sample_rate_hz * OFDM_SYMBOL_DURATION_S).astype(int)
    stops = np.rint((symbols + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S).astype(int)
    counts = stops - starts
    groups = []
    for count in np.unique(counts):
        positions = np.flatnonzero(counts == count)
        relative = starts[positions, None] + np.arange(int(count))[None, :]
        solves = np.stack(
            tuple(
                _known_pilot_solve(
                    sample_rate_hz,
                    edge,
                    int(symbols[position]),
                    int(starts[position]),
                    int(stops[position]),
                )
                for position in positions
            )
        )
        positions.flags.writeable = False
        relative.flags.writeable = False
        solves.flags.writeable = False
        groups.append((positions, relative, solves))
    return tuple(groups)


@lru_cache(maxsize=1_024)
def _known_pilot_solve(
    sample_rate_hz: float,
    edge: StarlinkEdge,
    symbol: int,
    local_start: int,
    local_stop: int,
) -> np.ndarray:
    """Cache immutable, IQ-independent demodulation matrices by geometry."""

    local = np.arange(local_start, local_stop)
    time_s = local / sample_rate_hz - symbol * OFDM_SYMBOL_DURATION_S - CYCLIC_PREFIX_DURATION_S
    frequencies = edge_frequencies_hz(edge)
    result = np.linalg.pinv(
        np.exp(2j * np.pi * time_s[:, None] * frequencies[None, :]) / math.sqrt(8)
    )
    result.flags.writeable = False
    return result


def _estimate_residual_cfo(pilots: np.ndarray, expected: np.ndarray) -> float:
    frame_match = np.sum(pilots * np.conj(expected)[None, :, :], axis=(1, 2))
    aligned = pilots * np.exp(-1j * np.angle(frame_match))[:, None, None]
    channel = np.mean(aligned * np.conj(expected)[None, :, :], axis=(0, 1))
    symbol_match = np.sum(
        pilots * np.conj(expected)[None, :, :] * np.conj(channel)[None, None, :],
        axis=2,
    )
    phase = np.unwrap(np.angle(symbol_match), axis=1)
    time_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    time_s -= np.mean(time_s)
    slopes = []
    for frame in range(pilots.shape[0]):
        weight = np.abs(symbol_match[frame])
        usable = weight > np.median(weight) * 0.25
        if np.count_nonzero(usable) >= 20:
            slopes.append(
                np.polyfit(
                    time_s[usable],
                    phase[frame, usable],
                    1,
                    w=np.sqrt(weight[usable]),
                )[0]
                / (2 * np.pi)
            )
    return float(np.clip(np.median(slopes) if slopes else 0.0, -2_000, 2_000))


def _estimate_phase_slope_frames(
    pilots: np.ndarray,
    expected: np.ndarray,
    control: np.ndarray,
    frame_starts: tuple[int, ...],
    *,
    sample_rate_hz: float,
    absolute_cfo_hz: float,
    maximum_residual_cfo_hz: float,
) -> PilotPhaseSlopeResult:
    """Pure frame-cube kernel behind :func:`analyze_pilot_phase_slope`."""

    values = np.asarray(pilots, dtype=np.complex128)
    exact_symbols = np.asarray(expected, dtype=np.complex128)
    control_symbols = np.asarray(control, dtype=np.complex128)
    if values.ndim != 3 or values.shape[1:] != (300, 8):
        raise ValueError("pilots must have shape (frames, 300, 8)")
    if exact_symbols.shape != (300, 8) or control_symbols.shape != (300, 8):
        raise ValueError("expected and control pilots must have shape (300, 8)")
    if values.shape[0] != len(frame_starts):
        raise ValueError("frame start count does not match pilot frame count")
    if not values.shape[0]:
        return _empty_phase_slope(NumericalStatus.INSUFFICIENT, "no pilot frames were supplied")
    if any(not math.isfinite(value) for value in (sample_rate_hz, absolute_cfo_hz)):
        raise ValueError("sample rate and absolute CFO must be finite")
    if (
        sample_rate_hz <= 0
        or not math.isfinite(maximum_residual_cfo_hz)
        or maximum_residual_cfo_hz <= 0
        or maximum_residual_cfo_hz > 0.5 / OFDM_SYMBOL_DURATION_S
    ):
        raise ValueError("sample rate or maximum residual CFO is unsupported")

    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_offset_s = float(np.mean(times_s))
    centered_times_s = times_s - reference_offset_s
    exact_matched = values * np.conj(exact_symbols)[None, :, :]
    control_matched = values * np.conj(control_symbols)[None, :, :]
    fits = tuple(
        _fit_phase_slope_frame(
            exact_matched[index],
            control_matched[index],
            centered_times_s,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        )
        for index in range(values.shape[0])
    )
    relative_phases = _relative_frame_phases(fits)
    margins = np.asarray(
        [fit.exact_coherence - fit.control_coherence for fit in fits],
        dtype=float,
    )
    residuals = np.asarray([fit.residual_cfo_hz for fit in fits], dtype=float)
    supported = margins > 0
    aggregate = float(np.median(residuals[supported] if np.any(supported) else residuals))
    frames = tuple(
        PilotPhaseSlopeFrame(
            frame_index=index,
            frame_start_sample=int(frame_start),
            reference_sample=float(frame_start + reference_offset_s * sample_rate_hz),
            residual_cfo_hz=fit.residual_cfo_hz,
            absolute_cfo_hz=float(absolute_cfo_hz + fit.residual_cfo_hz),
            frequency_uncertainty_hz=fit.frequency_uncertainty_hz,
            phase_at_reference_rad=float(relative_phases[index]),
            exact_coherence=fit.exact_coherence,
            control_coherence=fit.control_coherence,
            coherence_margin=float(margins[index]),
            phase_residual_rms_rad=fit.phase_residual_rms_rad,
        )
        for index, (frame_start, fit) in enumerate(zip(frame_starts, fits, strict=True))
    )
    return PilotPhaseSlopeResult(
        NumericalStatus.COMPLETE,
        frames,
        aggregate,
        float(absolute_cfo_hz + aggregate),
        "frame-local 300-symbol edge-pilot phase slopes; inter-frame phase was not assumed",
    )


def _fit_phase_slope_frame(
    exact: np.ndarray,
    control: np.ndarray,
    times_s: np.ndarray,
    *,
    maximum_residual_cfo_hz: float,
) -> _FrameSlopeFit:
    frequency_hz = _maximize_frequency_likelihood(
        exact,
        times_s,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
    )
    frequency_hz = _refine_frequency_from_phase(exact, times_s, frequency_hz)
    frequency_hz = float(np.clip(frequency_hz, -maximum_residual_cfo_hz, maximum_residual_cfo_hz))
    control_frequency_hz = _maximize_frequency_likelihood(
        control,
        times_s,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
    )
    exact_coherence = _frequency_coherence(exact, times_s, frequency_hz)
    control_coherence = _frequency_coherence(control, times_s, control_frequency_hz)

    dechirped = exact * np.exp(-2j * np.pi * frequency_hz * times_s)[:, None]
    channel = np.mean(dechirped, axis=0)
    symbol_match = np.sum(exact * np.conj(channel)[None, :], axis=1)
    residual_phase = np.angle(symbol_match * np.exp(-2j * np.pi * frequency_hz * times_s))
    weights = np.abs(symbol_match)
    phase_center = float(np.angle(np.sum(weights * np.exp(1j * residual_phase))))
    centered_phase = np.angle(np.exp(1j * (residual_phase - phase_center)))
    weight_total = float(np.sum(weights))
    phase_variance = (
        float(np.sum(weights * centered_phase**2) / weight_total)
        if weight_total > 0
        else math.pi**2 / 3
    )
    effective_count = (
        weight_total**2 / max(float(np.sum(weights**2)), 1e-20) if weight_total > 0 else 1.0
    )
    centered_time = times_s - (
        float(np.sum(weights * times_s) / weight_total) if weight_total > 0 else 0.0
    )
    time_variance = (
        float(np.sum(weights * centered_time**2) / weight_total) if weight_total > 0 else 0.0
    )
    uncertainty_hz = math.sqrt(phase_variance / max(effective_count * time_variance, 1e-20)) / (
        2 * np.pi
    )
    return _FrameSlopeFit(
        frequency_hz,
        float(uncertainty_hz),
        exact_coherence,
        control_coherence,
        float(math.sqrt(max(phase_variance, 0.0))),
        _freeze(channel),
    )


def _estimate_edge_pilot_frame_cfo_from_cubes(
    pilots: tuple[np.ndarray, np.ndarray, np.ndarray],
    expected: np.ndarray,
    control: np.ndarray,
    *,
    frame_start_sample: int,
    reference_sample: float,
    acquisition_absolute_cfo_hz: float,
    config: PilotFrameCfoConfig,
) -> PilotFrameCfoEstimate:
    """Pure pilot-cube kernel behind :func:`estimate_edge_pilot_frame_cfo`."""

    cubes = tuple(np.asarray(item, dtype=np.complex128) for item in pilots)
    exact_symbols = np.asarray(expected, dtype=np.complex128)
    control_symbols = np.asarray(control, dtype=np.complex128)
    if len(cubes) != 3 or any(item.shape != (300, 8) for item in cubes):
        raise ValueError("timing -1/0/+1 pilots must each have shape (300, 8)")
    if exact_symbols.shape != (300, 8) or control_symbols.shape != (300, 8):
        raise ValueError("expected and control pilots must have shape (300, 8)")
    arrays = (*cubes, exact_symbols, control_symbols)
    if any(not np.all(np.isfinite(item)) for item in arrays):
        raise ValueError("pilot cubes and known symbols must be finite")
    if not math.isfinite(reference_sample) or not math.isfinite(acquisition_absolute_cfo_hz):
        raise ValueError("frame reference and acquisition CFO must be finite")

    nominal = cubes[1]
    exact = nominal * np.conj(exact_symbols)
    matched_energy = float(np.sum(np.abs(exact) ** 2))
    if matched_energy <= np.finfo(float).tiny:
        return _empty_frame_cfo(
            NumericalStatus.NO_RESULT,
            "zero_pilot_energy",
            frame_start_sample,
            reference_sample,
        )
    null = nominal * np.conj(control_symbols)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    limit_hz = config.residual_half_width_hz
    full = _fit_phase_slope_frame(
        exact,
        null,
        times_s,
        maximum_residual_cfo_hz=limit_hz,
    )
    even = _fit_phase_slope_frame(
        exact[::2],
        null[::2],
        times_s[::2],
        maximum_residual_cfo_hz=limit_hz,
    )
    odd = _fit_phase_slope_frame(
        exact[1::2],
        null[1::2],
        times_s[1::2],
        maximum_residual_cfo_hz=limit_hz,
    )
    shifted_frequencies = []
    for shifted in (cubes[0], cubes[2]):
        shifted_frequencies.append(
            _fit_phase_slope_frame(
                shifted * np.conj(exact_symbols),
                shifted * np.conj(control_symbols),
                times_s,
                maximum_residual_cfo_hz=limit_hz,
            ).residual_cfo_hz
        )
    halves = []
    for indexes in (slice(0, 150), slice(150, 300)):
        halves.append(
            _fit_phase_slope_frame(
                exact[indexes],
                null[indexes],
                times_s[indexes],
                maximum_residual_cfo_hz=limit_hz,
            )
        )
    half_sigma_hz = math.hypot(
        halves[0].frequency_uncertainty_hz,
        halves[1].frequency_uncertainty_hz,
    )
    half_frame_difference_z = abs(halves[0].residual_cfo_hz - halves[1].residual_cfo_hz) / max(
        half_sigma_hz, np.finfo(float).tiny
    )
    timing_spread_hz = max(
        abs(frequency_hz - full.residual_cfo_hz) for frequency_hz in shifted_frequencies
    )
    even_odd_disagreement_hz = abs(even.residual_cfo_hz - odd.residual_cfo_hz)
    tone_deletion_spread_hz = _tone_deletion_frequency_spread(
        exact,
        times_s,
        full.residual_cfo_hz,
        maximum_residual_cfo_hz=limit_hz,
    )
    boundary_tolerance_hz = max(0.05, 1e-6 * limit_hz)
    search_boundary = bool(abs(abs(full.residual_cfo_hz) - limit_hz) <= boundary_tolerance_hz)
    margin = full.exact_coherence - full.control_coherence
    rejections = []
    if full.exact_coherence < config.minimum_exact_coherence:
        rejections.append("exact_coherence_below_minimum")
    if margin < config.minimum_coherence_margin:
        rejections.append("coherence_margin_below_minimum")
    if even_odd_disagreement_hz > config.maximum_even_odd_disagreement_hz:
        rejections.append("even_odd_disagreement_above_maximum")
    if timing_spread_hz > config.maximum_timing_spread_hz:
        rejections.append("timing_spread_above_maximum")
    if half_frame_difference_z > config.maximum_half_frame_z:
        rejections.append("half_frame_difference_above_maximum")
    if tone_deletion_spread_hz > config.maximum_tone_deletion_shift_hz:
        rejections.append("tone_deletion_shift_above_maximum")
    if search_boundary:
        rejections.append("search_boundary")
    residual_cfo_hz = float(full.residual_cfo_hz)
    return PilotFrameCfoEstimate(
        status=NumericalStatus.COMPLETE,
        measurement_supported=not rejections,
        rejection_reasons=tuple(rejections),
        frame_start_sample=int(frame_start_sample),
        reference_sample=float(reference_sample),
        residual_cfo_hz=residual_cfo_hz,
        absolute_cfo_hz=float(acquisition_absolute_cfo_hz + residual_cfo_hz),
        frequency_uncertainty_hz=float(full.frequency_uncertainty_hz),
        exact_coherence=float(full.exact_coherence),
        control_coherence=float(full.control_coherence),
        coherence_margin=float(margin),
        even_residual_cfo_hz=float(even.residual_cfo_hz),
        odd_residual_cfo_hz=float(odd.residual_cfo_hz),
        even_odd_disagreement_hz=float(even_odd_disagreement_hz),
        timing_spread_hz=float(timing_spread_hz),
        half_frame_difference_z=float(half_frame_difference_z),
        tone_deletion_spread_hz=float(tone_deletion_spread_hz),
        search_boundary=search_boundary,
    )


def _estimate_edge_pilot_frame_cfo_split_from_cube(
    pilots: np.ndarray,
    expected: np.ndarray,
    control: np.ndarray,
    *,
    frame_start_sample: int,
    reference_sample: float,
    acquisition_absolute_cfo_hz: float,
    config: PilotFrameCfoConfig,
) -> PilotFrameCfoSplitValidation:
    """Pure even-training/odd-validation kernel with no odd-data selection."""

    cube = np.asarray(pilots, dtype=np.complex128)
    exact_symbols = np.asarray(expected, dtype=np.complex128)
    control_symbols = np.asarray(control, dtype=np.complex128)
    if cube.shape != (300, 8):
        raise ValueError("pilot cube must have shape (300, 8)")
    if exact_symbols.shape != cube.shape or control_symbols.shape != cube.shape:
        raise ValueError("expected and control pilots must have shape (300, 8)")
    if any(not np.all(np.isfinite(item)) for item in (cube, exact_symbols, control_symbols)):
        raise ValueError("pilot cube and known symbols must be finite")
    if not math.isfinite(reference_sample) or not math.isfinite(acquisition_absolute_cfo_hz):
        raise ValueError("frame reference and acquisition CFO must be finite")
    if float(np.sum(np.abs(cube) ** 2)) <= np.finfo(float).tiny:
        return _empty_frame_cfo_split(frame_start_sample, reference_sample)

    exact = cube * np.conj(exact_symbols)
    null = cube * np.conj(control_symbols)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    even = _fit_phase_slope_frame(
        exact[::2],
        null[::2],
        times_s[::2],
        maximum_residual_cfo_hz=config.residual_half_width_hz,
    )
    odd = _fit_phase_slope_frame(
        exact[1::2],
        null[1::2],
        times_s[1::2],
        maximum_residual_cfo_hz=config.residual_half_width_hz,
    )
    boundary_tolerance_hz = max(0.05, 1e-6 * config.residual_half_width_hz)
    even_boundary = bool(
        abs(abs(even.residual_cfo_hz) - config.residual_half_width_hz) <= boundary_tolerance_hz
    )
    odd_boundary = bool(
        abs(abs(odd.residual_cfo_hz) - config.residual_half_width_hz) <= boundary_tolerance_hz
    )
    margin = even.exact_coherence - even.control_coherence
    rejections = []
    if even.exact_coherence < config.minimum_exact_coherence:
        rejections.append("even_exact_coherence_below_minimum")
    if margin < config.minimum_coherence_margin:
        rejections.append("even_coherence_margin_below_minimum")
    if even_boundary:
        rejections.append("even_search_boundary")
    return PilotFrameCfoSplitValidation(
        status=NumericalStatus.COMPLETE,
        training_supported=not rejections,
        training_rejection_reasons=tuple(rejections),
        frame_start_sample=int(frame_start_sample),
        reference_sample=float(reference_sample),
        even_residual_cfo_hz=float(even.residual_cfo_hz),
        odd_residual_cfo_hz=float(odd.residual_cfo_hz),
        even_absolute_cfo_hz=float(acquisition_absolute_cfo_hz + even.residual_cfo_hz),
        odd_absolute_cfo_hz=float(acquisition_absolute_cfo_hz + odd.residual_cfo_hz),
        even_frequency_uncertainty_hz=float(even.frequency_uncertainty_hz),
        odd_frequency_uncertainty_hz=float(odd.frequency_uncertainty_hz),
        even_exact_coherence=float(even.exact_coherence),
        even_control_coherence=float(even.control_coherence),
        even_coherence_margin=float(margin),
        even_search_boundary=even_boundary,
        odd_search_boundary=odd_boundary,
    )


def _tone_deletion_frequency_spread(
    exact: np.ndarray,
    times_s: np.ndarray,
    full_frequency_hz: float,
    *,
    maximum_residual_cfo_hz: float,
) -> float:
    """Maximum CFO shift after deleting any one of the eight pilot tones."""

    frequencies = []
    for tone in range(exact.shape[1]):
        deleted = np.delete(exact, tone, axis=1)
        frequency_hz = _maximize_frequency_likelihood(
            deleted,
            times_s,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        )
        frequency_hz = _refine_frequency_from_phase(deleted, times_s, frequency_hz)
        frequencies.append(
            float(
                np.clip(
                    frequency_hz,
                    -maximum_residual_cfo_hz,
                    maximum_residual_cfo_hz,
                )
            )
        )
    return float(np.max(np.abs(np.asarray(frequencies) - full_frequency_hz)))


def _maximize_frequency_likelihood(
    matched: np.ndarray,
    times_s: np.ndarray,
    *,
    maximum_residual_cfo_hz: float,
) -> float:
    """Maximize over frequency after analytically removing eight complex gains."""

    coarse_step_hz = min(100.0, maximum_residual_cfo_hz)
    coarse = np.arange(
        -maximum_residual_cfo_hz,
        maximum_residual_cfo_hz + 0.5 * coarse_step_hz,
        coarse_step_hz,
    )
    coarse_power = _frequency_likelihood(matched, times_s, coarse)
    coarse_best = float(coarse[int(np.argmax(coarse_power))])
    fine_step_hz = min(5.0, coarse_step_hz / 10)
    fine_start = max(-maximum_residual_cfo_hz, coarse_best - coarse_step_hz)
    fine_stop = min(maximum_residual_cfo_hz, coarse_best + coarse_step_hz)
    fine = np.arange(fine_start, fine_stop + 0.5 * fine_step_hz, fine_step_hz)
    fine_power = _frequency_likelihood(matched, times_s, fine)
    best = int(np.argmax(fine_power))
    frequency_hz = float(fine[best])
    if 0 < best < len(fine) - 1:
        leading, center, trailing = fine_power[best - 1 : best + 2]
        denominator = float(leading - 2 * center + trailing)
        if abs(denominator) > 1e-20:
            fractional = float(np.clip(0.5 * (leading - trailing) / denominator, -0.5, 0.5))
            frequency_hz += fractional * fine_step_hz
    return frequency_hz


def _frequency_likelihood(
    matched: np.ndarray,
    times_s: np.ndarray,
    frequencies_hz: np.ndarray,
) -> np.ndarray:
    rotations = np.exp(-2j * np.pi * frequencies_hz[:, None] * times_s[None, :])
    amplitudes = rotations @ matched
    return np.sum(np.abs(amplitudes) ** 2, axis=1)


def _profile_log_likelihood(
    matched: np.ndarray,
    times_s: np.ndarray,
    frequencies_hz: np.ndarray,
) -> np.ndarray:
    """Common-variance Gaussian profile after eliminating tone gains."""

    symbol_count, tone_count = matched.shape
    energy = float(np.sum(np.abs(matched) ** 2))
    projected = _frequency_likelihood(matched, times_s, frequencies_hz) / symbol_count
    floor = max(energy * 1e-15, np.finfo(float).tiny)
    residual = np.maximum(energy - projected, floor)
    observation_count = symbol_count * tone_count
    return -observation_count * np.log(residual / observation_count)


def _frequency_coherence(matched: np.ndarray, times_s: np.ndarray, frequency_hz: float) -> float:
    rotation = np.exp(-2j * np.pi * frequency_hz * times_s)
    amplitude = np.sum(matched * rotation[:, None], axis=0)
    ceiling = matched.shape[0] * float(np.sum(np.abs(matched) ** 2))
    return float(np.sum(np.abs(amplitude) ** 2) / max(ceiling, 1e-20))


def _refine_frequency_from_phase(
    matched: np.ndarray,
    times_s: np.ndarray,
    frequency_hz: float,
) -> float:
    """Refine the likelihood peak without connecting separate frames."""

    result = frequency_hz
    for _ in range(2):
        dechirped = matched * np.exp(-2j * np.pi * result * times_s)[:, None]
        channel = np.mean(dechirped, axis=0)
        symbol_match = np.sum(matched * np.conj(channel)[None, :], axis=1)
        residual = np.unwrap(np.angle(symbol_match * np.exp(-2j * np.pi * result * times_s)))
        weights = np.abs(symbol_match)
        usable = weights > np.median(weights) * 0.25
        if np.count_nonzero(usable) < 20:
            break
        selected_weights = weights[usable]
        selected_times = times_s[usable]
        selected_phase = residual[usable]
        weight_total = float(np.sum(selected_weights))
        time_center = float(np.sum(selected_weights * selected_times) / weight_total)
        phase_center = float(np.sum(selected_weights * selected_phase) / weight_total)
        centered_time = selected_times - time_center
        denominator = float(np.sum(selected_weights * centered_time**2))
        if denominator <= 1e-20:
            break
        slope = float(
            np.sum(selected_weights * centered_time * (selected_phase - phase_center)) / denominator
        )
        correction_hz = slope / (2 * np.pi)
        if not math.isfinite(correction_hz) or abs(correction_hz) > 25.0:
            break
        result += correction_hz
    return float(result)


def _relative_frame_phases(fits: tuple[_FrameSlopeFit, ...]) -> np.ndarray:
    vectors = np.stack(tuple(fit.channel_vector for fit in fits))
    norms = np.linalg.norm(vectors, axis=1)
    units = vectors / np.maximum(norms[:, None], 1e-20)
    weights = np.maximum(
        np.asarray(
            [fit.exact_coherence - fit.control_coherence for fit in fits],
            dtype=float,
        ),
        0.0,
    )
    if not np.any(weights > 0):
        weights = np.asarray([fit.exact_coherence for fit in fits], dtype=float)
    if not np.any(weights > 0):
        weights = np.ones(len(fits), dtype=float)
    reference = units[int(np.argmax(weights))].copy()
    for _ in range(8):
        phases = np.angle(np.sum(units * np.conj(reference)[None, :], axis=1))
        aligned = units * np.exp(-1j * phases)[:, None]
        updated = np.sum(aligned * weights[:, None], axis=0)
        norm = float(np.linalg.norm(updated))
        if norm <= 1e-20:
            break
        reference = updated / norm
    return np.angle(np.sum(units * np.conj(reference)[None, :], axis=1))


def _cross_fit_equalize(stacked: np.ndarray, expected: np.ndarray) -> np.ndarray:
    equalized = np.empty_like(stacked)
    indexes = np.arange(300)
    for parity in range(2):
        training = indexes % 2 != parity
        testing = ~training
        channel = np.mean(stacked[training] * np.conj(expected[training]), axis=0)
        equalized[testing] = stacked[testing] / np.where(
            np.abs(channel) > 1e-20,
            channel,
            np.complex64(1),
        )
    return equalized


def _metric_values(
    equalized: np.ndarray, expected: np.ndarray
) -> tuple[float, float, float, float, float]:
    expected_values = np.broadcast_to(expected, equalized.shape)
    states = _constellation_states(expected)
    constellation = np.exp(0.5j * np.pi * (np.arange(4, dtype=float) + 0.5))
    distance = np.abs(equalized[..., None] - constellation) ** 2
    hard = np.argmin(distance, axis=-1)
    error = equalized - expected_values
    noise_variance = max(float(np.mean(np.abs(error) ** 2)), 1e-6)
    logits = -distance / noise_variance
    logits -= np.max(logits, axis=-1, keepdims=True)
    likelihood = np.exp(logits)
    probabilities = likelihood / np.sum(likelihood, axis=-1, keepdims=True)
    known = np.broadcast_to(states, hard.shape)
    expected_probability = np.take_along_axis(probabilities, known[..., None], axis=-1)[..., 0]
    return (
        float(np.mean(hard == known)),
        float(np.sqrt(np.mean(np.abs(error) ** 2))),
        noise_variance,
        float(np.mean(np.max(probabilities, axis=-1))),
        float(np.mean(expected_probability)),
    )


def _constellation_states(values: np.ndarray) -> np.ndarray:
    phases = np.angle(values) / (np.pi / 2) - 0.5
    return np.mod(np.rint(phases).astype(int), 4)


def _complete_frame_starts(
    sample_count: int, sample_rate_hz: float, epoch_sample: int
) -> tuple[int, ...]:
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    result: list[int] = []
    frame = 0
    while True:
        start = epoch_sample + round(frame * sample_rate_hz / FRAME_RATE_HZ)
        if start + frame_content > sample_count:
            return tuple(result)
        result.append(start)
        frame += 1


def _empty(status: NumericalStatus, reason: str) -> PilotQamResult:
    return PilotQamResult(status, None, None, None, reason)


def _empty_phase_slope(status: NumericalStatus, reason: str) -> PilotPhaseSlopeResult:
    return PilotPhaseSlopeResult(status, (), None, None, reason)


def _empty_frame_cfo(
    status: NumericalStatus,
    reason: str,
    frame_start_sample: int,
    reference_sample: float,
) -> PilotFrameCfoEstimate:
    return PilotFrameCfoEstimate(
        status=status,
        measurement_supported=False,
        rejection_reasons=(reason,),
        frame_start_sample=int(frame_start_sample),
        reference_sample=float(reference_sample),
        residual_cfo_hz=None,
        absolute_cfo_hz=None,
        frequency_uncertainty_hz=None,
        exact_coherence=None,
        control_coherence=None,
        coherence_margin=None,
        even_residual_cfo_hz=None,
        odd_residual_cfo_hz=None,
        even_odd_disagreement_hz=None,
        timing_spread_hz=None,
        half_frame_difference_z=None,
        tone_deletion_spread_hz=None,
        search_boundary=False,
    )


def _empty_frame_cfo_split(
    frame_start_sample: int,
    reference_sample: float,
) -> PilotFrameCfoSplitValidation:
    return PilotFrameCfoSplitValidation(
        status=NumericalStatus.NO_RESULT,
        training_supported=False,
        training_rejection_reasons=("zero_pilot_energy",),
        frame_start_sample=int(frame_start_sample),
        reference_sample=float(reference_sample),
        even_residual_cfo_hz=None,
        odd_residual_cfo_hz=None,
        even_absolute_cfo_hz=None,
        odd_absolute_cfo_hz=None,
        even_frequency_uncertainty_hz=None,
        odd_frequency_uncertainty_hz=None,
        even_exact_coherence=None,
        even_control_coherence=None,
        even_coherence_margin=None,
        even_search_boundary=False,
        odd_search_boundary=False,
    )


def _empty_frame_complex_split(
    frame_start_sample: int,
    reference_sample: float,
) -> PilotFrameComplexSplitObservation:
    return PilotFrameComplexSplitObservation(
        status=NumericalStatus.NO_RESULT,
        training_supported=False,
        training_rejection_reasons=("zero_pilot_energy",),
        frame_start_sample=int(frame_start_sample),
        reference_sample=float(reference_sample),
        even=None,
        odd=None,
    )


def _freeze(values: np.ndarray) -> np.ndarray:
    output = np.asarray(values).copy()
    output.flags.writeable = False
    return output
