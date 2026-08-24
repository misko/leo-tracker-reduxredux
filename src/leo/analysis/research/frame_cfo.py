"""Research estimators for one-frame known-pilot carrier frequency.

These functions operate on a pilot-wiped ``(symbol, tone)`` complex matrix.
They deliberately do not acquire timing or choose a Starlink CFO alias.  A
caller must first bind the frame to one timing/CFO basin and provide a bounded
residual-frequency search interval.

The ordinary profile likelihood is the Gaussian-noise maximum-likelihood
estimator after analytically eliminating one unknown complex gain per tone.
The robust variant alternates that frequency fit with Huber symbol weights and
bounded inverse-residual-variance tone weights.  It is a research comparator,
not a published Standard contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class ProfiledFrameCfo:
    """One bounded frame-CFO estimate and auditable fit diagnostics."""

    frequency_hz: float
    frequency_uncertainty_hz: float
    normalized_coherence: float
    effective_symbol_count: float
    heavily_downweighted_symbol_fraction: float
    search_boundary: bool
    iteration_count: int


def ordinary_profile_cfo(
    matched: npt.ArrayLike,
    times_s: npt.ArrayLike,
    *,
    maximum_residual_cfo_hz: float,
    coarse_step_hz: float = 100.0,
    fine_step_hz: float = 5.0,
) -> ProfiledFrameCfo:
    """Profile one complex gain per tone under equal-variance Gaussian noise."""

    values, times = _inputs(matched, times_s, maximum_residual_cfo_hz)
    symbol_weights = np.ones(len(times), dtype=float)
    tone_weights = np.ones(values.shape[1], dtype=float)
    frequency = _maximize_profile(
        values,
        times,
        symbol_weights,
        tone_weights,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        coarse_step_hz=coarse_step_hz,
        fine_step_hz=fine_step_hz,
    )
    return _diagnostics(
        values,
        times,
        frequency,
        symbol_weights,
        tone_weights,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        iteration_count=1,
    )


def robust_profile_cfo(
    matched: npt.ArrayLike,
    times_s: npt.ArrayLike,
    *,
    maximum_residual_cfo_hz: float,
    coarse_step_hz: float = 100.0,
    fine_step_hz: float = 5.0,
    huber_threshold: float = 2.5,
    maximum_iterations: int = 4,
    maximum_tone_weight_ratio: float = 8.0,
) -> ProfiledFrameCfo:
    """Robust profile likelihood with symbol and tone contamination control.

    The initial point is the ordinary eight-gain profile maximum.  Each robust
    iteration estimates a complex channel per tone, obtains a median-based
    residual scale per tone, Huber-downweights symbols that disagree across a
    majority of tones, and caps inverse-noise tone weights.  Fixed weights are
    then used in a new bounded profile-likelihood maximization.

    The tone-weight cap is important: without it, one spur-free but nearly
    noiseless-looking tone can dominate a short frame through a chance scale
    underestimate.
    """

    values, times = _inputs(matched, times_s, maximum_residual_cfo_hz)
    finite = (coarse_step_hz, fine_step_hz, huber_threshold, maximum_tone_weight_ratio)
    if any(not math.isfinite(value) or value <= 0.0 for value in finite):
        raise ValueError("frame-CFO tuning values must be finite and positive")
    if maximum_iterations < 1:
        raise ValueError("maximum iterations must be positive")
    symbol_weights = np.ones(len(times), dtype=float)
    tone_weights = _tone_consensus_weights(
        values,
        times,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        coarse_step_hz=coarse_step_hz,
        fine_step_hz=fine_step_hz,
        maximum_tone_weight_ratio=maximum_tone_weight_ratio,
    )
    frequency = _maximize_profile(
        values,
        times,
        symbol_weights,
        tone_weights,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        coarse_step_hz=coarse_step_hz,
        fine_step_hz=fine_step_hz,
    )
    completed = 1
    for iteration in range(maximum_iterations):
        rotation = np.exp(-2j * np.pi * frequency * times)
        dechirped = values * rotation[:, None]
        weight_total = max(float(np.sum(symbol_weights)), np.finfo(float).eps)
        channel = np.sum(symbol_weights[:, None] * dechirped, axis=0) / weight_total
        residual = dechirped - channel[None, :]

        # For circular complex Gaussian noise, median(|e|^2) / log(2) is a
        # robust variance estimate.  A common floor prevents a single tone
        # with a chance-small residual scale from receiving unbounded weight.
        scale_squared = np.median(np.abs(residual) ** 2, axis=0) / math.log(2.0)
        positive = scale_squared[scale_squared > np.finfo(float).tiny]
        common_scale = float(np.median(positive)) if positive.size else 1.0
        scale_squared = np.maximum(scale_squared, 0.125 * common_scale)
        precision = common_scale / np.maximum(scale_squared, np.finfo(float).tiny)
        tone_weights = np.clip(
            tone_weights * precision,
            1.0 / maximum_tone_weight_ratio**2,
            maximum_tone_weight_ratio,
        )

        standardized = np.abs(residual) ** 2 / scale_squared[None, :]
        symbol_residual = np.sqrt(np.median(standardized, axis=1))
        symbol_weights = np.minimum(
            1.0,
            huber_threshold / np.maximum(symbol_residual, np.finfo(float).eps),
        )
        updated = _maximize_profile(
            values,
            times,
            symbol_weights,
            tone_weights,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
            coarse_step_hz=coarse_step_hz,
            fine_step_hz=fine_step_hz,
        )
        completed = iteration + 2
        if abs(updated - frequency) <= max(0.05, fine_step_hz * 0.02):
            frequency = updated
            break
        frequency = updated
    return _diagnostics(
        values,
        times,
        frequency,
        symbol_weights,
        tone_weights,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        iteration_count=completed,
    )


def differential_phase_cfo(
    matched: npt.ArrayLike,
    times_s: npt.ArrayLike,
    *,
    maximum_residual_cfo_hz: float,
    huber_phase_rad: float = 0.35,
    maximum_iterations: int = 6,
) -> float:
    """Estimate CFO from robust adjacent-symbol phase increments.

    This is a search-free phase-slope comparator.  It cancels the static
    complex gain of each tone through adjacent products.  Its unambiguous
    interval is set by the largest adjacent time gap, so it fails closed when
    the requested residual-frequency interval would wrap that increment.
    """

    values, times = _inputs(matched, times_s, maximum_residual_cfo_hz)
    if not math.isfinite(huber_phase_rad) or huber_phase_rad <= 0.0:
        raise ValueError("phase Huber threshold must be finite and positive")
    if maximum_iterations < 1:
        raise ValueError("maximum iterations must be positive")
    order = np.argsort(times)
    ordered = values[order]
    deltas = np.diff(times[order])
    if np.any(deltas <= 0.0):
        raise ValueError("frame symbol times must be unique")
    if maximum_residual_cfo_hz >= 0.5 / float(np.max(deltas)):
        raise ValueError("requested CFO interval is ambiguous for adjacent-symbol phase")
    products = ordered[1:] * np.conj(ordered[:-1])
    magnitudes = np.abs(products)
    units = np.divide(
        products,
        magnitudes,
        out=np.zeros_like(products),
        where=magnitudes > np.finfo(float).tiny,
    )
    pair_vectors = np.sum(units, axis=1)
    pair_weight = np.abs(pair_vectors)
    pair_phase = np.angle(pair_vectors)
    frequency = float(
        np.sum(pair_weight * pair_phase / (2.0 * np.pi * deltas))
        / max(float(np.sum(pair_weight)), np.finfo(float).eps)
    )
    for _ in range(maximum_iterations):
        residual = np.angle(np.exp(1j * (pair_phase - 2.0 * np.pi * frequency * deltas)))
        robust = np.minimum(
            1.0,
            huber_phase_rad / np.maximum(np.abs(residual), np.finfo(float).eps),
        )
        weights = pair_weight * robust
        denominator = float(np.sum(weights * deltas**2))
        if denominator <= np.finfo(float).tiny:
            break
        correction = float(np.sum(weights * deltas * residual) / denominator / (2.0 * np.pi))
        frequency += correction
        if abs(correction) < 0.01:
            break
    return float(np.clip(frequency, -maximum_residual_cfo_hz, maximum_residual_cfo_hz))


def profiled_coherence(
    matched: npt.ArrayLike,
    times_s: npt.ArrayLike,
    frequency_hz: float,
) -> float:
    """Return the existing eight-gain normalized profile coherence at one CFO."""

    values = np.asarray(matched, dtype=np.complex128)
    times = np.asarray(times_s, dtype=float)
    if values.ndim != 2 or times.shape != (len(values),) or not len(values):
        raise ValueError("matched pilots must be symbol by tone with one time per symbol")
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(times)):
        raise ValueError("matched pilots and times must be finite")
    amplitude = np.sum(values * np.exp(-2j * np.pi * frequency_hz * times)[:, None], axis=0)
    ceiling = len(times) * float(np.sum(np.abs(values) ** 2))
    return float(np.sum(np.abs(amplitude) ** 2) / max(ceiling, np.finfo(float).tiny))


def _inputs(
    matched: npt.ArrayLike,
    times_s: npt.ArrayLike,
    maximum_residual_cfo_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(matched, dtype=np.complex128)
    times = np.asarray(times_s, dtype=float)
    if values.ndim != 2 or values.shape[0] < 20 or values.shape[1] < 1:
        raise ValueError("matched pilots must contain at least 20 symbols and one tone")
    if times.shape != (values.shape[0],):
        raise ValueError("one symbol time is required for every matched-pilot row")
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(times)):
        raise ValueError("matched pilots and times must be finite")
    if not math.isfinite(maximum_residual_cfo_hz) or maximum_residual_cfo_hz <= 0.0:
        raise ValueError("maximum residual CFO must be finite and positive")
    if np.ptp(times) <= 0.0:
        raise ValueError("frame symbol times must span a positive interval")
    return values, times


def _frequency_grid(limit_hz: float, step_hz: float) -> np.ndarray:
    if not math.isfinite(step_hz) or step_hz <= 0.0:
        raise ValueError("frequency step must be finite and positive")
    count = max(1, int(math.ceil(2.0 * limit_hz / step_hz)))
    return np.linspace(-limit_hz, limit_hz, count + 1)


def _weighted_profile(
    values: np.ndarray,
    times: np.ndarray,
    frequencies: np.ndarray,
    symbol_weights: np.ndarray,
    tone_weights: np.ndarray,
) -> np.ndarray:
    rotations = np.exp(-2j * np.pi * frequencies[:, None] * times[None, :])
    amplitudes = rotations @ (values * symbol_weights[:, None])
    return np.sum(tone_weights[None, :] * np.abs(amplitudes) ** 2, axis=1)


def _tone_consensus_weights(
    values: np.ndarray,
    times: np.ndarray,
    *,
    maximum_residual_cfo_hz: float,
    coarse_step_hz: float,
    fine_step_hz: float,
    maximum_tone_weight_ratio: float,
) -> np.ndarray:
    """Downweight tones whose own frequency maximum misses the modal cluster."""

    if values.shape[1] == 1:
        return np.ones(1, dtype=float)
    coarse = _frequency_grid(maximum_residual_cfo_hz, coarse_step_hz)
    coarse_amplitude = np.exp(-2j * np.pi * coarse[:, None] * times[None, :]) @ values
    coarse_positions = np.argmax(np.abs(coarse_amplitude) ** 2, axis=0)
    coarse_best = coarse[coarse_positions]
    local_limit = min(coarse_step_hz, maximum_residual_cfo_hz)
    fine_offsets = _frequency_grid(local_limit, fine_step_hz)
    fine = np.clip(
        coarse_best[:, None] + fine_offsets[None, :],
        -maximum_residual_cfo_hz,
        maximum_residual_cfo_hz,
    )
    rotations = np.exp(-2j * np.pi * fine[:, :, None] * times[None, None, :])
    fine_amplitude = np.einsum("tfs,st->tf", rotations, values, optimize=True)
    fine_power = np.abs(fine_amplitude) ** 2
    best = np.argmax(fine_power, axis=1)
    frequencies = fine[np.arange(values.shape[1]), best].astype(float)
    for tone, position in enumerate(best):
        if 0 < position < fine.shape[1] - 1:
            leading, center, trailing = (
                float(value) for value in fine_power[tone, position - 1 : position + 2]
            )
            denominator = leading - 2.0 * center + trailing
            step = float(fine[tone, position] - fine[tone, position - 1])
            if abs(denominator) > np.finfo(float).tiny and step > 0.0:
                fraction = float(np.clip(0.5 * (leading - trailing) / denominator, -0.5, 0.5))
                frequencies[tone] += fraction * step
    coherence = np.asarray(
        [
            profiled_coherence(values[:, tone : tone + 1], times, frequency)
            for tone, frequency in enumerate(frequencies)
        ],
        dtype=float,
    )
    # About one third of a Fourier-resolution cell tolerates noisy single-tone
    # maxima while still separating a coherent narrowband contaminant.
    consensus_radius_hz = max(4.0 * fine_step_hz, 0.35 / float(np.ptp(times)))
    best_center = float(np.median(frequencies))
    best_key = (-1, -math.inf)
    for candidate in frequencies:
        member = np.abs(frequencies - candidate) <= consensus_radius_hz
        key = (int(np.count_nonzero(member)), float(np.sum(coherence[member])))
        if key > best_key:
            best_key = key
            best_center = float(np.median(frequencies[member]))
    member = np.abs(frequencies - best_center) <= consensus_radius_hz
    floor = 1.0 / maximum_tone_weight_ratio**2
    return np.where(member, 1.0, floor)


def _maximize_profile(
    values: np.ndarray,
    times: np.ndarray,
    symbol_weights: np.ndarray,
    tone_weights: np.ndarray,
    *,
    maximum_residual_cfo_hz: float,
    coarse_step_hz: float,
    fine_step_hz: float,
) -> float:
    coarse = _frequency_grid(maximum_residual_cfo_hz, coarse_step_hz)
    coarse_power = _weighted_profile(values, times, coarse, symbol_weights, tone_weights)
    coarse_best = float(coarse[int(np.argmax(coarse_power))])
    local_limit = min(coarse_step_hz, maximum_residual_cfo_hz)
    fine_offsets = _frequency_grid(local_limit, fine_step_hz)
    fine = np.clip(coarse_best + fine_offsets, -maximum_residual_cfo_hz, maximum_residual_cfo_hz)
    fine = np.unique(fine)
    power = _weighted_profile(values, times, fine, symbol_weights, tone_weights)
    best = int(np.argmax(power))
    frequency = float(fine[best])
    if 0 < best < len(fine) - 1:
        leading, center, trailing = (float(value) for value in power[best - 1 : best + 2])
        left_step = frequency - float(fine[best - 1])
        right_step = float(fine[best + 1]) - frequency
        if math.isclose(left_step, right_step, rel_tol=1e-9, abs_tol=1e-12):
            denominator = leading - 2.0 * center + trailing
            if abs(denominator) > np.finfo(float).tiny:
                fraction = float(np.clip(0.5 * (leading - trailing) / denominator, -0.5, 0.5))
                frequency += fraction * left_step
    return float(np.clip(frequency, -maximum_residual_cfo_hz, maximum_residual_cfo_hz))


def _diagnostics(
    values: np.ndarray,
    times: np.ndarray,
    frequency: float,
    symbol_weights: np.ndarray,
    tone_weights: np.ndarray,
    *,
    maximum_residual_cfo_hz: float,
    iteration_count: int,
) -> ProfiledFrameCfo:
    rotation = np.exp(-2j * np.pi * frequency * times)
    weight_total = max(float(np.sum(symbol_weights)), np.finfo(float).eps)
    channel = np.sum(symbol_weights[:, None] * values * rotation[:, None], axis=0) / weight_total
    combined = np.sum(
        tone_weights[None, :] * values * np.conj(channel)[None, :],
        axis=1,
    )
    residual_phase = np.angle(combined * rotation)
    phase_center = float(
        np.angle(np.sum(symbol_weights * np.abs(combined) * np.exp(1j * residual_phase)))
    )
    centered_phase = np.angle(np.exp(1j * (residual_phase - phase_center)))
    diagnostic_weights = symbol_weights * np.abs(combined)
    diagnostic_total = max(float(np.sum(diagnostic_weights)), np.finfo(float).eps)
    phase_variance = float(np.sum(diagnostic_weights * centered_phase**2) / diagnostic_total)
    time_center = float(np.sum(diagnostic_weights * times) / diagnostic_total)
    time_variance = float(
        np.sum(diagnostic_weights * (times - time_center) ** 2) / diagnostic_total
    )
    effective = float(
        np.sum(diagnostic_weights) ** 2
        / max(float(np.sum(diagnostic_weights**2)), np.finfo(float).tiny)
    )
    uncertainty = math.sqrt(phase_variance / max(effective * time_variance, 1e-20)) / (2.0 * np.pi)
    coherence = profiled_coherence(values, times, frequency)
    boundary_tolerance = max(0.05, 1e-6 * maximum_residual_cfo_hz)
    return ProfiledFrameCfo(
        frequency_hz=float(frequency),
        frequency_uncertainty_hz=float(uncertainty),
        normalized_coherence=coherence,
        effective_symbol_count=effective,
        heavily_downweighted_symbol_fraction=float(np.mean(symbol_weights < 0.5)),
        search_boundary=bool(abs(abs(frequency) - maximum_residual_cfo_hz) <= boundary_tolerance),
        iteration_count=iteration_count,
    )
