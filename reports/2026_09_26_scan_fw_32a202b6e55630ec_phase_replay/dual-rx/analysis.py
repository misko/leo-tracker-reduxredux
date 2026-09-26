"""Package F dual-receiver estimators with explicit gauge and held support."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


def wrap_rad(value: npt.ArrayLike) -> npt.NDArray[np.float64]:
    values = np.asarray(value, dtype=np.float64)
    return (values + np.pi) % (2 * np.pi) - np.pi


def circular_r(phase: npt.ArrayLike, weight: npt.ArrayLike | None = None) -> float:
    values = np.asarray(phase, dtype=np.float64)
    weights = np.ones(values.shape, dtype=np.float64) if weight is None else np.asarray(weight)
    keep = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not np.any(keep):
        return math.nan
    return float(abs(np.sum(weights[keep] * np.exp(1j * values[keep]))) / np.sum(weights[keep]))


@dataclass(frozen=True, slots=True)
class WindowPhasors:
    starts: npt.NDArray[np.int64]
    centers_counter: npt.NDArray[np.int64]
    phasors: npt.NDArray[np.complex128]
    coherence: npt.NDArray[np.float64]


def direct_window_phasors(
    iq: npt.NDArray[np.complex64],
    valid: npt.NDArray[np.bool_],
    *,
    device_counter_start: int,
    sample_rate_hz: int,
    starts: npt.ArrayLike,
    window_samples: int,
    relative_cfo_hz: float = 0.0,
    relative_rate_hz_s: float = 0.0,
) -> WindowPhasors:
    """Compute RX0*conj(RX1) after restoring RX1 into the RX0 gauge."""

    values = np.asarray(iq)
    mask = np.asarray(valid)
    starts_array = np.asarray(starts, dtype=np.int64)
    if values.ndim != 2 or values.shape[1] != 2 or mask.shape != values.shape:
        raise ValueError("dual-RX IQ and receiver-specific validity geometry disagree")
    if (
        window_samples <= 0
        or np.any(starts_array < 0)
        or np.any(starts_array + window_samples > len(values))
    ):
        raise ValueError("window lies outside the visit")
    taper = np.hanning(window_samples)
    phasors: list[complex] = []
    coherence: list[float] = []
    accepted: list[int] = []
    for start in starts_array:
        support = slice(int(start), int(start) + window_samples)
        if not np.all(mask[support]):
            continue
        absolute = (int(start) + np.arange(window_samples, dtype=np.float64)) / sample_rate_hz
        centered = absolute - 0.060
        cycles = relative_cfo_hz * absolute + 0.5 * relative_rate_hz_s * (
            centered**2 - 0.060**2
        )
        left = values[support, 0].astype(np.complex128)
        right = values[support, 1].astype(np.complex128) * np.exp(-2j * np.pi * cycles)
        product = np.conj(left) * right * taper**2
        phasor = np.sum(product)
        denominator = math.sqrt(
            max(float(np.sum(abs(left * taper) ** 2) * np.sum(abs(right * taper) ** 2)), 1e-30)
        )
        accepted.append(int(start))
        phasors.append(complex(phasor))
        coherence.append(float(abs(phasor) / denominator))
    accepted_array = np.asarray(accepted, dtype=np.int64)
    centers = device_counter_start + accepted_array + (window_samples - 1) // 2
    return WindowPhasors(
        accepted_array,
        centers,
        np.asarray(phasors, dtype=np.complex128),
        np.asarray(coherence, dtype=np.float64),
    )


def deterministic_holdout(starts: npt.ArrayLike, authority: str) -> tuple[np.ndarray, np.ndarray]:
    """Split alternate shuffled windows within each 20 ms stratum."""

    values = np.asarray(starts, dtype=np.int64)
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(authority.encode()).digest()[:8]))
    train: list[int] = []
    held: list[int] = []
    for group in np.array_split(np.arange(len(values)), 6):
        order = rng.permutation(group)
        split = (len(order) + 1) // 2
        train.extend(order[:split])
        held.extend(order[split:])
    return np.sort(values[train]), np.sort(values[held])


def fit_phase_frequency_rate(
    phasors: npt.ArrayLike,
    centers_counter: npt.ArrayLike,
    *,
    integer_origin: int,
    sample_rate_hz: int,
    degree: int,
) -> tuple[float, float, float]:
    """Fit phase without returning or applying a free evaluation intercept."""

    if degree not in (0, 1, 2):
        raise ValueError("degree must be raw, constant-CFO, or CFO-plus-rate")
    values = np.asarray(phasors, dtype=np.complex128)
    counter = np.asarray(centers_counter)
    time_s = (counter.astype(object) - integer_origin).astype(float) / sample_rate_hz
    phase = np.unwrap(np.angle(values))
    if degree == 0:
        return 0.0, 0.0, float(np.angle(np.sum(values)))
    coefficients = np.polyfit(time_s, phase, degree, w=np.maximum(abs(values), 1e-30))
    if degree == 1:
        slope, intercept = coefficients
        return float(slope / (2 * np.pi)), 0.0, float(intercept)
    quadratic, slope, intercept = coefficients
    return float(slope / (2 * np.pi)), float(quadratic / np.pi), float(intercept)


def prediction_error(
    phasors: npt.ArrayLike,
    centers_counter: npt.ArrayLike,
    *,
    integer_origin: int,
    sample_rate_hz: int,
    cfo_hz: float,
    rate_hz_s: float,
    training_intercept_rad: float,
) -> npt.NDArray[np.float64]:
    counter = np.asarray(centers_counter)
    time_s = (counter.astype(object) - integer_origin).astype(float) / sample_rate_hz
    predicted = training_intercept_rad + 2 * np.pi * cfo_hz * time_s + np.pi * rate_hz_s * time_s**2
    return wrap_rad(np.angle(np.asarray(phasors)) - predicted)


def wrong_time_starts(
    starts: npt.ArrayLike, *, visit_samples: int, window_samples: int = 0
) -> np.ndarray:
    """Freeze a 13 ms control offset, away from measured 20/40/60 ms recurrence."""

    values = np.asarray(starts, dtype=np.int64)
    offset = 130_000
    shifted = values + offset
    shifted[shifted + window_samples > visit_samples] -= 2 * offset
    return shifted


def wrong_time_coherence(
    iq: npt.NDArray[np.complex64],
    valid: npt.NDArray[np.bool_],
    *,
    left_starts: npt.ArrayLike,
    right_starts: npt.ArrayLike,
    window_samples: int,
    sample_rate_hz: int,
    relative_cfo_hz: float,
    relative_rate_hz_s: float,
) -> npt.NDArray[np.float64]:
    """Coherence for frozen asynchronous receiver windows."""

    left_axis = np.asarray(left_starts, dtype=np.int64)
    right_axis = np.asarray(right_starts, dtype=np.int64)
    if left_axis.shape != right_axis.shape:
        raise ValueError("wrong-time axes disagree")
    taper = np.hanning(window_samples)
    output = []
    for left_start, right_start in zip(left_axis, right_axis, strict=True):
        left_slice = slice(int(left_start), int(left_start) + window_samples)
        right_slice = slice(int(right_start), int(right_start) + window_samples)
        if not np.all(valid[left_slice, 0]) or not np.all(valid[right_slice, 1]):
            continue
        right_time = (int(right_start) + np.arange(window_samples)) / sample_rate_hz
        centered = right_time - 0.060
        cycles = relative_cfo_hz * right_time + 0.5 * relative_rate_hz_s * (
            centered**2 - 0.060**2
        )
        left = iq[left_slice, 0].astype(np.complex128)
        right = iq[right_slice, 1].astype(np.complex128) * np.exp(-2j * np.pi * cycles)
        numerator = abs(np.sum(np.conj(left) * right * taper**2))
        denominator = math.sqrt(
            max(float(np.sum(abs(left * taper) ** 2) * np.sum(abs(right * taper) ** 2)), 1e-30)
        )
        output.append(numerator / denominator)
    return np.asarray(output, dtype=np.float64)
