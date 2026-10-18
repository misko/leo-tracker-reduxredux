"""Deterministic robust degree-one regression for accepted CFO segments."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class HuberLinearFit:
    reference_time_s: float
    slope_hz_per_s: float
    intercept_at_reference_hz: float
    residual_rms_hz: float
    residual_max_hz: float
    median_absolute_residual_hz: float
    mad_scale_hz: float
    huber_objective: float
    iteration_count: int
    converged: bool

    @property
    def coefficients_hz(self) -> tuple[float, float]:
        return (self.slope_hz_per_s, self.intercept_at_reference_hz)


def fit_huber_linear_irls(
    time_s: np.ndarray,
    values_hz: np.ndarray,
    *,
    initial_coefficients_hz: tuple[float, float],
    reference_time_s: float,
    tuning_constant: float = 1.345,
    scale_floor_hz: float = 100.0,
    maximum_iterations: int = 32,
    prediction_tolerance_hz: float = 1e-6,
) -> HuberLinearFit:
    """Refine one fixed-membership line using MAD-scaled Huber IRLS.

    ``initial_coefficients_hz`` are highest-power-first and expressed around
    ``reference_time_s``. Point membership is immutable; this function only
    refines the two degree-one coefficients.
    """

    times = np.asarray(time_s, dtype=np.float64)
    values = np.asarray(values_hz, dtype=np.float64)
    if times.ndim != 1 or values.ndim != 1 or times.shape != values.shape:
        raise ValueError("Huber linear inputs must be equal one-dimensional arrays")
    if times.size < 3 or np.unique(times).size < 2:
        raise ValueError("Huber linear refinement requires three points at two times")
    finite = (
        *times,
        *values,
        *initial_coefficients_hz,
        reference_time_s,
        tuning_constant,
        scale_floor_hz,
        prediction_tolerance_hz,
    )
    if any(not math.isfinite(float(item)) for item in finite):
        raise ValueError("Huber linear inputs must be finite")
    if (
        tuning_constant <= 0.0
        or scale_floor_hz <= 0.0
        or maximum_iterations < 1
        or prediction_tolerance_hz <= 0.0
    ):
        raise ValueError("Huber linear configuration must be positive")

    relative_time = times - reference_time_s
    design = np.column_stack((relative_time, np.ones(times.size, dtype=np.float64)))
    coefficients = np.asarray(initial_coefficients_hz, dtype=np.float64)
    converged = False
    iteration_count = 0
    scale = scale_floor_hz
    for iteration_number in range(1, maximum_iterations + 1):
        iteration_count = iteration_number
        residual = values - design @ coefficients
        residual_center = float(np.median(residual))
        mad = float(np.median(np.abs(residual - residual_center)))
        scale = max(scale_floor_hz, 1.4826 * mad)
        standardized = np.abs(residual) / scale
        weights = np.ones_like(standardized)
        tail = standardized > tuning_constant
        weights[tail] = tuning_constant / standardized[tail]
        root_weights = np.sqrt(weights)
        updated = np.linalg.lstsq(
            design * root_weights[:, None],
            values * root_weights,
            rcond=None,
        )[0]
        maximum_prediction_change = float(np.max(np.abs(design @ (updated - coefficients))))
        coefficients = updated
        if maximum_prediction_change <= prediction_tolerance_hz:
            converged = True
            break

    residual = values - design @ coefficients
    residual_center = float(np.median(residual))
    mad = float(np.median(np.abs(residual - residual_center)))
    scale = max(scale_floor_hz, 1.4826 * mad)
    standardized = np.abs(residual) / scale
    quadratic = standardized <= tuning_constant
    rho = np.where(
        quadratic,
        0.5 * standardized**2,
        tuning_constant * standardized - 0.5 * tuning_constant**2,
    )
    return HuberLinearFit(
        reference_time_s=float(reference_time_s),
        slope_hz_per_s=float(coefficients[0]),
        intercept_at_reference_hz=float(coefficients[1]),
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        residual_max_hz=float(np.max(np.abs(residual))),
        median_absolute_residual_hz=float(np.median(np.abs(residual))),
        mad_scale_hz=scale,
        huber_objective=float(np.sum(rho)),
        iteration_count=iteration_count,
        converged=converged,
    )
