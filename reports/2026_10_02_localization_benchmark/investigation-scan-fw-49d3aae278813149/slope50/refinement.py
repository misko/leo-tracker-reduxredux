"""Continuous refinement for fixed, one-observation-per-group assignments."""

from __future__ import annotations

import numpy as np
from common import ALIAS_HZ, circular

ROBUST_SCALE_HZ = 200.0
MIN_TIMING_GROUPS = 30
MIN_TIMING_SUPPORTED_DURATION_S = 20.0
PARAMETER_COUNT = 70
SATELLITE_COUNT = 64


def _field(assignments, name):
    try:
        return assignments[name]
    except (KeyError, TypeError):
        raise ValueError(f"assignments must contain {name!r}") from None


def _validate(data, assignments, initial, sigma_s, bound_s, max_nfev):
    parameters = np.asarray(initial, dtype=float)
    if parameters.shape != (PARAMETER_COUNT,) or not np.all(np.isfinite(parameters)):
        raise ValueError("initial must be a finite length-70 vector")
    if not np.isfinite(sigma_s) or sigma_s <= 0:
        raise ValueError("sigma_s must be positive and finite")
    if not np.isfinite(bound_s) or bound_s <= 0:
        raise ValueError("bound_s must be positive and finite")
    if not isinstance(max_nfev, (int, np.integer)) or max_nfev <= 0:
        raise ValueError("max_nfev must be a positive integer")

    rows = np.asarray(_field(assignments, "rows"))
    satellites = np.asarray(_field(assignments, "satellites"))
    weights = np.asarray(_field(assignments, "weights"), dtype=float)
    if rows.ndim != 1 or satellites.ndim != 1 or weights.ndim != 1:
        raise ValueError("assignment rows, satellites, and weights must be one-dimensional")
    if not (len(rows) == len(satellites) == len(weights)) or not len(rows):
        raise ValueError("assignment arrays must have equal nonzero length")
    if not np.issubdtype(rows.dtype, np.integer):
        raise ValueError("assignment rows must be integers")
    if not np.issubdtype(satellites.dtype, np.integer):
        raise ValueError("assignment satellites must be integers")
    rows = rows.astype(int, copy=False)
    satellites = satellites.astype(int, copy=False)

    measured = np.asarray(data.measured)
    times = np.asarray(data.times)
    groups = np.asarray(data.group)
    receivers = np.asarray(data.receiver)
    if not (measured.ndim == times.ndim == groups.ndim == receivers.ndim == 1):
        raise ValueError("data observation attributes must be one-dimensional")
    if not (len(measured) == len(times) == len(groups) == len(receivers)):
        raise ValueError("data observation attributes must have equal length")
    if np.any(rows < 0) or np.any(rows >= len(measured)):
        raise ValueError("assignment row outside data")
    if len(np.unique(rows)) != len(rows):
        raise ValueError("assignment rows must be unique")
    if len(np.unique(groups[rows])) != len(rows):
        raise ValueError("assignments must contain exactly one observation per group")
    if np.any((satellites < 0) | (satellites >= SATELLITE_COUNT)):
        raise ValueError("assignment satellite outside the 64-candidate parameter vector")
    if hasattr(data, "numbers") and np.any(satellites >= len(data.numbers)):
        raise ValueError("assignment satellite outside data.numbers")
    if np.any(~np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError("assignment weights must be positive and finite")
    if np.any(~np.isfinite(measured[rows])) or np.any(~np.isfinite(times[rows])):
        raise ValueError("assigned measurements and times must be finite")
    if np.any(~np.isin(receivers[rows], (0, 1))):
        raise ValueError("assigned receivers must be 0 or 1")
    return parameters.copy(), rows, satellites, weights


def _soft_l1_residual(errors_hz):
    scaled = np.asarray(errors_hz, dtype=float) / ROBUST_SCALE_HZ
    return scaled * np.sqrt(2 / (np.sqrt(1 + scaled * scaled) + 1))


def _canonical_alias(value):
    return (value + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def _timing_support(data, rows, satellites):
    support = []
    times = np.asarray(data.times)[rows]
    groups = np.asarray(data.group)[rows]
    for satellite in np.unique(satellites):
        selected = satellites == satellite
        group_count = len(np.unique(groups[selected]))
        unique_times = np.unique(times[selected])
        span_s = float(np.ptp(unique_times)) if len(unique_times) else 0.0
        supported_duration_s = float(np.sum(np.minimum(np.diff(unique_times), 1.0)))
        support.append(
            {
                "satellite_index": int(satellite),
                "groups": int(group_count),
                "span_s": span_s,
                "supported_duration_s_capped_1s_gaps": supported_duration_s,
                "active": bool(
                    group_count >= MIN_TIMING_GROUPS
                    and supported_duration_s >= MIN_TIMING_SUPPORTED_DURATION_S
                ),
            }
        )
    return support


def _predict(data, parameters, rows, satellites):
    prediction, visible = data.predict(parameters, rows=rows, satellites=satellites)
    prediction = np.asarray(prediction, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    if prediction.shape != rows.shape or visible.shape != rows.shape:
        raise ValueError("paired data.predict must return two arrays matching assignment rows")
    return prediction, visible


def _frequency_state(data, parameters, rows, satellites):
    prediction, visible = _predict(data, parameters, rows, satellites)
    errors = circular(np.asarray(data.measured)[rows], prediction)
    usable = visible & np.isfinite(prediction) & np.isfinite(errors)
    penalized = np.where(usable, errors, ALIAS_HZ / 2)
    return penalized, usable


def _conditioning(data, parameters, rows, satellites, weights, active_timing):
    target_columns = [0, 1, *[6 + satellite for satellite in active_timing]]
    target_names = [
        "east_km",
        "north_km",
        *[f"tau_{satellite}_s" for satellite in active_timing],
    ]
    target_steps = [0.01, 0.01, *([0.001] * len(active_timing))]
    nuisance_columns = [2, 3, 4, 5]
    nuisance_names = [
        "rx0_intercept_hz",
        "rx0_slope_hz_s",
        "rx1_intercept_hz",
        "rx1_slope_hz_s",
    ]
    nuisance_steps = [1.0, 0.001, 1.0, 0.001]
    derivatives = []
    valid = np.ones(len(rows), dtype=bool)
    for column, step in zip(
        target_columns + nuisance_columns, target_steps + nuisance_steps, strict=True
    ):
        plus = parameters.copy()
        minus = parameters.copy()
        plus[column] += step
        minus[column] -= step
        plus_prediction, plus_visible = _predict(data, plus, rows, satellites)
        minus_prediction, minus_visible = _predict(data, minus, rows, satellites)
        local = (
            plus_visible
            & minus_visible
            & np.isfinite(plus_prediction)
            & np.isfinite(minus_prediction)
        )
        valid &= local
        derivatives.append(circular(plus_prediction, minus_prediction) / (2 * step))
    matrix = np.column_stack(derivatives)[valid] * np.sqrt(weights[valid, None])
    target_count = len(target_columns)
    target = matrix[:, :target_count]
    nuisance = matrix[:, target_count:]
    nuisance_rank = int(np.linalg.matrix_rank(nuisance)) if nuisance.size else 0
    if nuisance.size:
        coefficients = np.linalg.lstsq(nuisance, target, rcond=None)[0]
        residualized = target - nuisance @ coefficients
    else:
        residualized = target
    original_norms = np.linalg.norm(target, axis=0) if len(target) else np.zeros(target_count)
    norms = np.linalg.norm(residualized, axis=0) if len(residualized) else np.zeros(target_count)
    retained = np.divide(norms, original_norms, out=np.zeros_like(norms), where=original_norms > 0)
    informative = norms > max(float(np.max(norms, initial=0)) * 1e-12, 1e-12)
    normalized = (
        residualized[:, informative] / norms[informative]
        if np.any(informative)
        else residualized[:, :0]
    )
    singular = np.linalg.svd(normalized, compute_uv=False) if normalized.size else np.array([])
    condition = (
        float(singular[0] / singular[-1])
        if len(singular) and singular[-1] > np.finfo(float).eps * singular[0]
        else None
    )
    rank = int(np.linalg.matrix_rank(normalized)) if normalized.size else 0
    normalized_full = np.zeros_like(residualized)
    if np.any(informative):
        normalized_full[:, informative] = residualized[:, informative] / norms[informative]
    correlations = normalized_full.T @ normalized_full
    np.fill_diagonal(correlations, 0)
    max_pair = float(np.max(np.abs(correlations), initial=0))
    position_timing = correlations[:2, 2:]
    max_position_timing = float(np.max(np.abs(position_timing), initial=0))
    return {
        "method": (
            "weighted central differences; position/timing projected off fitted RX intercept "
            "and slope columns; residualized columns normalized before SVD"
        ),
        "rows": int(np.sum(valid)),
        "columns": target_names,
        "rx_nuisance_columns": nuisance_names,
        "rx_nuisance_rank": nuisance_rank,
        "column_norms_hz_per_unit_before_rx_projection": original_norms.tolist(),
        "column_norms_hz_per_unit_after_rx_projection": norms.tolist(),
        "retained_norm_fraction_after_rx_projection": retained.tolist(),
        "informative_columns": [
            name for name, keep in zip(target_names, informative, strict=True) if keep
        ],
        "rank": rank,
        "condition_number": condition,
        "singular_values": singular.tolist(),
        "maximum_absolute_column_correlation": max_pair,
        "maximum_position_timing_correlation": max_position_timing,
    }


def fit_fixed(
    data,
    assignments,
    initial,
    timing=False,
    sigma_s=1.0,
    bound_s=3.0,
    max_nfev=160,
):
    """Fit position, receiver lines, and supported fixed-assignment timing shifts."""
    from scipy.optimize import least_squares

    initial, rows, satellites, weights = _validate(
        data, assignments, initial, sigma_s, bound_s, max_nfev
    )
    support = _timing_support(data, rows, satellites)
    active_timing = [row["satellite_index"] for row in support if timing and row["active"]]

    base = initial.copy()
    base[2] = _canonical_alias(base[2])
    base[4] = _canonical_alias(base[4])
    base[6:] = 0.0
    active = np.array([0, 1, 2, 3, 4, 5, *[6 + index for index in active_timing]], dtype=int)
    scales = np.array([20.0, 20.0, 1000.0, 1.0, 1000.0, 1.0, *([1.0] * len(active_timing))])
    lower = np.array(
        [-200.0, -200.0, -np.inf, -50.0, -np.inf, -50.0, *([-bound_s] * len(active_timing))]
    )
    upper = np.array([200.0, 200.0, np.inf, 50.0, np.inf, 50.0, *([bound_s] * len(active_timing))])
    starting = np.clip(base[active], lower, upper)

    def unpack(scaled):
        parameters = base.copy()
        parameters[active] = scaled * scales
        return parameters

    def residual(scaled):
        parameters = unpack(scaled)
        errors, _ = _frequency_state(data, parameters, rows, satellites)
        frequency = np.sqrt(weights) * _soft_l1_residual(errors)
        if not active_timing:
            return frequency
        prior = parameters[6 + np.asarray(active_timing)] / sigma_s
        return np.r_[frequency, prior]

    fitted = least_squares(
        residual,
        starting / scales,
        bounds=(lower / scales, upper / scales),
        loss="linear",
        max_nfev=int(max_nfev),
        method="trf",
        ftol=1e-9,
        xtol=1e-9,
        gtol=1e-9,
    )
    parameters = unpack(fitted.x)
    parameters[2] = _canonical_alias(parameters[2])
    parameters[4] = _canonical_alias(parameters[4])
    errors, visible = _frequency_state(data, parameters, rows, satellites)
    transformed = np.sqrt(weights) * _soft_l1_residual(errors)
    timing_values = parameters[6 + np.asarray(active_timing, dtype=int)]
    frequency_objective = float(0.5 * transformed @ transformed)
    prior_objective = float(0.5 * np.sum((timing_values / sigma_s) ** 2))
    visible_errors = errors[visible]
    diagnostics = {
        "observations": len(rows),
        "sum_weights": float(np.sum(weights)),
        "mean_weight": float(np.mean(weights)),
        "sum_weights_per_active_tau": (
            float(np.sum(weights) / len(active_timing)) if active_timing else None
        ),
        "visible_observations": int(np.sum(visible)),
        "invisible_penalized_observations": int(np.sum(~visible)),
        "robust_scale_hz": ROBUST_SCALE_HZ,
        "frequency_objective": frequency_objective,
        "timing_prior_objective": prior_objective,
        "timing_prior_count": len(active_timing),
        "timing_sigma_s": float(sigma_s),
        "timing_bound_s": float(bound_s),
        "timing_support": support,
        "active_timing_satellites": active_timing,
        "rms_visible_hz": (
            float(np.sqrt(np.mean(visible_errors**2))) if len(visible_errors) else None
        ),
        "slope_at_bound": [bool(abs(parameters[index]) >= 50.0 - 1e-7) for index in (3, 5)],
        "timing_at_bound": [bool(abs(value) >= bound_s - 1e-7) for value in timing_values],
        "optimizer_status": int(fitted.status),
        "optimizer_optimality": float(fitted.optimality),
        "optimizer_cost": float(fitted.cost),
        "optimizer_active_mask": fitted.active_mask.tolist(),
        "conditioning": _conditioning(data, parameters, rows, satellites, weights, active_timing),
    }
    return {
        "parameters": parameters,
        "success": bool(fitted.success),
        "message": str(fitted.message),
        "nfev": int(fitted.nfev),
        "objective": frequency_objective + prior_objective,
        "diagnostics": diagnostics,
    }
