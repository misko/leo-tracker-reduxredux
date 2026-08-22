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


def _freeze(values: np.ndarray) -> np.ndarray:
    output = np.asarray(values).copy()
    output.flags.writeable = False
    return output
