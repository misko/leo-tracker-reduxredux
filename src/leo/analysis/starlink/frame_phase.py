"""Frame-local phase diagnostics for conditioned Starlink pilot correlations.

The Qin edge pilot repeats across Starlink OFDM frames, but the carrier phase
need not be continuous between frames.  These primitives therefore estimate a
separate circular phase state for every frame.  They never fit a curved CFO
trajectory and never use a neighboring frame to improve the current estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class FramePhaseState:
    """One independently estimated frame-local pilot phase state."""

    frame_index: int
    midpoint_s: float
    phase_cycles: float
    coherence: float
    median_absolute_residual_cycles: float
    mean_normalized_power: float
    control_coherence: float
    control_phase_cycles: float
    control_median_absolute_residual_cycles: float
    control_mean_normalized_power: float
    phase_invariant_signature: npt.NDArray[np.complex128]


@dataclass(frozen=True, slots=True)
class HeldoutPhasePrediction:
    """Held-out test of one constant phase increment across frame indexes."""

    increment_cycles_per_frame: float
    intercept_cycles: float
    training_concentration: float
    heldout_errors_cycles: npt.NDArray[np.float64]


def estimate_frame_phase_states(
    exact_values: npt.ArrayLike,
    control_values: npt.ArrayLike,
    exact_power: npt.ArrayLike,
    control_power: npt.ArrayLike,
    times_s: npt.ArrayLike,
) -> tuple[FramePhaseState, ...]:
    """Estimate one robust circular phase location per complete pilot frame.

    Inputs are the already CFO-conditioned, per-symbol complex correlations
    for the exact Qin pilot and its symbol-rolled control.  A bounded power
    weight prevents one unusually large symbol from setting the frame phase.
    The returned signature removes global phase and norm; it is diagnostic
    waveform-shape evidence, not a satellite identifier.
    """

    exact = _complex_matrix("exact_values", exact_values)
    control = _complex_matrix("control_values", control_values)
    exact_scores = _real_matrix("exact_power", exact_power)
    control_scores = _real_matrix("control_power", control_power)
    moments = _real_matrix("times_s", times_s)
    shape = exact.shape
    if any(value.shape != shape for value in (control, exact_scores, control_scores, moments)):
        raise ValueError("frame-local phase inputs must have identical shapes")
    if not np.all(np.isfinite(exact)) or not np.all(np.isfinite(control)):
        raise ValueError("frame-local complex correlations must be finite")
    if np.any(exact_scores < 0) or np.any(control_scores < 0):
        raise ValueError("normalized pilot power must be nonnegative")

    output: list[FramePhaseState] = []
    for frame_index in range(shape[0]):
        exact_phase, exact_coherence, exact_error, signature = _frame_location(
            exact[frame_index], exact_scores[frame_index]
        )
        control_phase, control_coherence, control_error, _ = _frame_location(
            control[frame_index], control_scores[frame_index]
        )
        output.append(
            FramePhaseState(
                frame_index=frame_index,
                midpoint_s=float(np.mean(moments[frame_index])),
                phase_cycles=exact_phase,
                coherence=exact_coherence,
                median_absolute_residual_cycles=exact_error,
                mean_normalized_power=float(np.mean(exact_scores[frame_index])),
                control_coherence=control_coherence,
                control_phase_cycles=control_phase,
                control_median_absolute_residual_cycles=control_error,
                control_mean_normalized_power=float(np.mean(control_scores[frame_index])),
                phase_invariant_signature=signature,
            )
        )
    return tuple(output)


def fit_heldout_constant_phase_increment(
    phase_cycles: npt.ArrayLike,
    frame_indexes: npt.ArrayLike | None = None,
    *,
    grid_size: int = 4096,
) -> HeldoutPhasePrediction:
    """Fit two of every three frames and predict the interleaved third.

    A constant phase increment is a constant residual CFO, not a curved CFO
    model. Interleaving training and held-out frames avoids long extrapolation
    while ensuring no held-out phase enters the fit. Retaining adjacent indexes
    in training also avoids the half-cycle slope alias created by even-only
    training.
    """

    phases = np.asarray(phase_cycles, dtype=float)
    indexes = (
        np.arange(len(phases), dtype=int)
        if frame_indexes is None
        else np.asarray(frame_indexes, dtype=int)
    )
    if phases.ndim != 1 or indexes.ndim != 1 or phases.shape != indexes.shape:
        raise ValueError("phase cycles and frame indexes must be matching vectors")
    if len(phases) < 4 or not np.all(np.isfinite(phases)):
        raise ValueError("held-out phase prediction requires at least four finite frames")
    if np.any(np.diff(indexes) <= 0):
        raise ValueError("frame indexes must be strictly increasing")
    if isinstance(grid_size, bool) or not isinstance(grid_size, int) or grid_size < 32:
        raise ValueError("phase-increment grid size must be an integer of at least 32")
    heldout = (indexes - indexes[0]) % 3 == 1
    training = ~heldout
    grid = np.arange(grid_size, dtype=float) / grid_size - 0.5
    residual = phases[training][None, :] - grid[:, None] * indexes[training][None, :]
    vectors = np.mean(np.exp(2j * np.pi * residual), axis=1)
    best = int(np.argmax(np.abs(vectors)))
    increment = float(grid[best])
    intercept = float(np.angle(vectors[best]) / (2.0 * np.pi))
    errors = np.abs(
        wrapped_cycle_difference(
            phases[heldout], intercept + increment * indexes[heldout]
        )
    )
    errors = np.asarray(errors, dtype=float)
    errors.flags.writeable = False
    return HeldoutPhasePrediction(
        increment_cycles_per_frame=increment,
        intercept_cycles=intercept,
        training_concentration=float(abs(vectors[best])),
        heldout_errors_cycles=errors,
    )


def circular_concentration(cycles: npt.ArrayLike) -> float:
    """Return mean resultant length in ``[0, 1]`` for phase cycles."""

    values = np.asarray(cycles, dtype=float)
    if values.ndim != 1:
        raise ValueError("circular samples must be one-dimensional")
    if not values.size:
        return 0.0
    if not np.all(np.isfinite(values)):
        raise ValueError("circular samples must be finite")
    return float(abs(np.mean(np.exp(2j * np.pi * values))))


def wrapped_cycle_difference(leading: npt.ArrayLike, trailing: npt.ArrayLike) -> np.ndarray:
    """Subtract phases and wrap the result into ``[-0.5, 0.5)`` cycles."""

    result = np.asarray(leading, dtype=float) - np.asarray(trailing, dtype=float)
    return (result + 0.5) % 1.0 - 0.5


def _frame_location(
    values: npt.NDArray[np.complex128],
    normalized_power: npt.NDArray[np.float64],
) -> tuple[float, float, float, npt.NDArray[np.complex128]]:
    magnitudes = np.abs(values)
    positive = magnitudes > 0
    if not np.any(positive):
        return 0.0, 0.0, 0.5, np.zeros(values.shape, dtype=np.complex128)

    # Square-root power retains reliability ordering while limiting dynamic
    # range.  The four-times-median cap makes the circular location robust to
    # a single high-energy symbol without introducing a line or phase model.
    weights = np.sqrt(np.maximum(normalized_power, 0.0))
    median = float(np.median(weights[positive]))
    cap = max(4.0 * median, np.finfo(float).eps)
    weights = np.minimum(weights, cap)
    weights = np.where(positive, np.maximum(weights, np.finfo(float).eps), 0.0)
    unit = np.divide(
        values,
        magnitudes,
        out=np.zeros_like(values),
        where=positive,
    )
    vector = complex(np.sum(weights * unit))
    phase = math.atan2(vector.imag, vector.real)
    coherence = float(abs(vector) / max(float(np.sum(weights)), np.finfo(float).eps))
    residual_cycles = wrapped_cycle_difference(
        np.angle(values) / (2.0 * np.pi), phase / (2.0 * np.pi)
    )
    error = _weighted_median(np.abs(residual_cycles), weights)

    dephased = values * np.exp(-1j * phase)
    norm = float(np.linalg.norm(dephased))
    signature = (
        np.asarray(dephased / norm, dtype=np.complex128)
        if norm > 0
        else np.zeros(values.shape, dtype=np.complex128)
    )
    signature.flags.writeable = False
    return float(phase / (2.0 * np.pi)), coherence, error, signature


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    indexes = np.argsort(values, kind="stable")
    ordered = values[indexes]
    cumulative = np.cumsum(weights[indexes])
    if not cumulative.size or cumulative[-1] <= 0:
        return 0.5
    selected = int(np.searchsorted(cumulative, 0.5 * cumulative[-1], side="left"))
    return float(ordered[min(selected, len(ordered) - 1)])


def _complex_matrix(name: str, values: npt.ArrayLike) -> npt.NDArray[np.complex128]:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim != 2 or not result.shape[0] or result.shape[1] < 2:
        raise ValueError(f"{name} must be a nonempty frame-by-symbol matrix")
    return result


def _real_matrix(name: str, values: npt.ArrayLike) -> npt.NDArray[np.float64]:
    result = np.asarray(values, dtype=float)
    if result.ndim != 2 or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be one finite frame-by-symbol matrix")
    return result
