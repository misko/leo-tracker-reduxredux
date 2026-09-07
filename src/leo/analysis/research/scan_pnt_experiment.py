"""Pure numerical retrospective Doppler experiments with explicit held-out scoring.

All inputs are arrays, including externally supplied orbit predictions. No I/O or
orbit catalogue lookup is performed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Arc:
    time_s: np.ndarray
    frequency_hz: np.ndarray
    segment: np.ndarray

    def __post_init__(self) -> None:
        if not (self.time_s.shape == self.frequency_hz.shape == self.segment.shape):
            raise ValueError("arc arrays must have matching shapes")
        if self.time_s.ndim != 1 or self.time_s.size < 8:
            raise ValueError("an arc requires at least eight observations")
        if not np.all(np.isfinite(self.time_s)) or not np.all(np.isfinite(self.frequency_hz)):
            raise ValueError("non-finite observations")


def split_segments(
    arc: Arc, fraction: float = 0.6, within: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Reserve later measurements independently in each fixed source tracklet."""
    if not 0 < fraction < 1:
        raise ValueError("training fraction must be inside (0, 1)")
    available = np.ones(arc.time_s.size, dtype=bool) if within is None else within.copy()
    training = np.zeros(arc.time_s.size, dtype=bool)
    for name in np.unique(arc.segment):
        indices = np.flatnonzero(available & (arc.segment == name))
        indices = indices[np.argsort(arc.time_s[indices], kind="stable")]
        if indices.size < 4:
            raise ValueError("each source segment needs four observations for splitting")
        cut = max(2, min(indices.size - 2, int(indices.size * fraction)))
        training[indices[:cut]] = True
    return training, available & ~training


def segment_rms(residual: np.ndarray, segment: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Each segment receives equal weight, regardless of receiver duplication."""
    squared = []
    for name in np.unique(segment):
        selected = mask & (segment == name)
        if not np.any(selected):
            raise ValueError("RMS mask omits a segment")
        squared.append(np.mean(np.square(residual[..., selected]), axis=-1))
    return np.sqrt(np.mean(squared, axis=0))


def remove_offsets(residual: np.ndarray, segment: np.ndarray, training: np.ndarray) -> np.ndarray:
    aligned = residual.copy()
    for name in np.unique(segment):
        mask = segment == name
        if not np.any(mask & training):
            raise ValueError("cannot learn an offset without training support")
        aligned[..., mask] -= np.mean(residual[..., mask & training], axis=-1)[..., None]
    return aligned


def polynomial_fit(
    arc: Arc, degree: int, training: np.ndarray, *, derivative_time_s: float | None = None
) -> dict:
    """Scaled least squares; covariance uses design SVD, not squared conditioning."""
    if degree not in (1, 2, 3):
        raise ValueError("polynomial degree must be one, two, or three")
    reference = float(np.mean(arc.time_s[training]))
    scale = max(float(np.ptp(arc.time_s[training])), 1.0)
    x = (arc.time_s - reference) / scale
    names = np.unique(arc.segment)
    design = np.column_stack(
        [*(arc.segment == name for name in names), *(x**power for power in range(1, degree + 1))]
    )
    fit_design = design[training]
    if fit_design.shape[0] <= fit_design.shape[1]:
        raise ValueError("insufficient polynomial degrees of freedom")
    coef, _, rank, _ = np.linalg.lstsq(fit_design, arc.frequency_hz[training], rcond=None)
    if rank < fit_design.shape[1]:
        raise ValueError("rank-deficient polynomial")
    predicted = design @ coef
    residual = arc.frequency_hz - predicted
    rss = float(np.sum(residual[training] ** 2))
    n, k = fit_design.shape
    inverse = np.linalg.pinv(fit_design)
    covariance = inverse @ inverse.T * rss / (n - k)
    midpoint = (
        (float(arc.time_s.min()) + float(arc.time_s.max())) / 2
        if derivative_time_s is None
        else derivative_time_s
    )
    mx = (midpoint - reference) / scale
    derivative_row = np.zeros(k)
    for power in range(1, degree + 1):
        derivative_row[len(names) + power - 1] = power * mx ** (power - 1) / scale
    return {
        "degree": degree,
        "predicted_hz": predicted,
        "residual_hz": residual,
        "bic": n * np.log(max(rss / n, 1e-20)) + k * np.log(n),
        "rate_hz_s": float(derivative_row @ coef),
        "rate_se_hz_s": float(np.sqrt(max(derivative_row @ covariance @ derivative_row, 0))),
        "training_rms_hz": float(segment_rms(residual, arc.segment, training)),
        "condition": float(np.linalg.cond(fit_design)),
    }


def polynomial_comparison(arc: Arc) -> dict:
    training, heldout = split_segments(arc)
    inner_train, inner_validation = split_segments(arc, 2 / 3, within=training)
    rows, full_rows = [], []
    for degree in (1, 2, 3):
        outer = polynomial_fit(arc, degree, training)
        try:
            inner = polynomial_fit(arc, degree, inner_train)
        except ValueError:
            inner = None
        full = polynomial_fit(arc, degree, np.ones(arc.time_s.size, dtype=bool))
        rows.append(
            {
                "degree": degree,
                "training_bic": float(outer["bic"]),
                "training_rms_hz": outer["training_rms_hz"],
                "inner_validation_rms_hz": float(
                    segment_rms(inner["residual_hz"], arc.segment, inner_validation)
                )
                if inner
                else None,
                "heldout_rms_hz": float(segment_rms(outer["residual_hz"], arc.segment, heldout)),
            }
        )
        full_rows.append(
            {
                "degree": degree,
                "rms_hz": float(np.sqrt(np.mean(full["residual_hz"] ** 2))),
                "bic": float(full["bic"]),
                "rate_hz_s": full["rate_hz_s"],
                "rate_se_hz_s": full["rate_se_hz_s"],
            }
        )
    criterion = (
        "inner_validation_rms_hz"
        if all(row["inner_validation_rms_hz"] is not None for row in rows)
        else "training_bic"
    )
    selected = min(rows, key=lambda row: (row[criterion], row["degree"]))
    return {
        "models": rows,
        "full_models": full_rows,
        "selection_criterion": criterion,
        "selected_degree": selected["degree"],
        "selected_heldout_rms_hz": selected["heldout_rms_hz"],
    }


def interpolate_bank(models: np.ndarray, grid_s: np.ndarray, query_s: np.ndarray) -> np.ndarray:
    spacing = float(grid_s[1] - grid_s[0])
    location = (query_s - grid_s[0]) / spacing
    left = np.floor(location).astype(int)
    if np.any(left < 0) or np.any(left + 1 >= len(grid_s)):
        raise ValueError("model grid does not cover requested observations")
    fraction = location - left
    return models[:, left] * (1 - fraction) + models[:, left + 1] * fraction


def match_catalogue(
    arc: Arc,
    models: np.ndarray,
    grid_s: np.ndarray,
    taus: np.ndarray,
    numbers: np.ndarray,
    max_tau: float = 2.0,
) -> tuple[dict, dict]:
    """Select identity and tau on training only; score all fixed choices on heldout."""
    training, heldout = split_segments(arc)
    train_profile = np.empty((len(taus), len(numbers)))
    test_profile = np.empty_like(train_profile)
    curvature_profile = np.empty_like(train_profile)
    # Curvature score projects away one common slope as well as track offsets.
    tx = arc.time_s - np.mean(arc.time_s[training])
    tx = remove_offsets(tx, arc.segment, training)
    for i, tau in enumerate(taus):
        prediction = interpolate_bank(models, grid_s, arc.time_s + tau)
        residual = remove_offsets(arc.frequency_hz - prediction, arc.segment, training)
        train_profile[i] = segment_rms(residual, arc.segment, training)
        test_profile[i] = segment_rms(residual, arc.segment, heldout)
        slope = np.sum(residual[:, training] * tx[training], axis=1) / np.sum(tx[training] ** 2)
        curvature_profile[i] = segment_rms(residual - slope[:, None] * tx, arc.segment, training)

    def summarize(bound: float) -> dict:
        permitted = np.flatnonzero(np.abs(taus) <= bound + 1e-9)
        best_tau = permitted[np.argmin(train_profile[permitted], axis=0)]
        indices = np.arange(len(numbers))
        train = train_profile[best_tau, indices]
        test = test_profile[best_tau, indices]
        order = np.argsort(train, kind="stable")
        winner, runner = order[:2]
        selected_tau = float(taus[best_tau[winner]])
        return {
            "norad": int(numbers[winner]),
            "tau_s": selected_tau,
            "at_boundary": bound > 0 and abs(selected_tau) >= bound - 1e-9,
            "training_rms_hz": float(train[winner]),
            "heldout_rms_hz": float(test[winner]),
            "heldout_rank": int(1 + np.count_nonzero(test < test[winner])),
            "runner_gap_hz": float(train[runner] - train[winner]),
            "near_count": int(np.count_nonzero(train <= train[winner] * 1.1 + 5)),
            "top_candidates": [
                {
                    "norad": int(numbers[j]),
                    "tau_s": float(taus[best_tau[j]]),
                    "training_rms_hz": float(train[j]),
                    "heldout_rms_hz": float(test[j]),
                }
                for j in order[:10]
            ],
        }

    midpoint = np.array([(arc.time_s.min() + arc.time_s.max()) / 2])
    # Rate measured solely in training; model rate uses central finite difference.
    observed_rate = polynomial_fit(arc, 3, training)["rate_hz_s"]
    rates = (
        interpolate_bank(models, grid_s, midpoint + 0.25)
        - interpolate_bank(models, grid_s, midpoint - 0.25)
    )[:, 0] / 0.5
    errors = np.abs(rates - observed_rate)
    curv = np.min(curvature_profile[np.abs(taus) <= max_tau], axis=0)
    result = {
        "catalogue_count": len(numbers),
        "primary": summarize(max_tau),
        "nominal": summarize(0),
        "wide": summarize(float(np.max(np.abs(taus)))),
        "rate_only": {
            "norad": int(numbers[np.argmin(errors)]),
            "error_hz_s": float(np.min(errors)),
            "near_count": int(np.count_nonzero(errors <= errors.min() + 100)),
        },
        "curvature_only": {
            "norad": int(numbers[np.argmin(curv)]),
            "training_rms_hz": float(curv.min()),
            "near_count": int(np.count_nonzero(curv <= curv.min() * 1.1 + 5)),
        },
    }
    return result, {
        "train_profile": train_profile,
        "test_profile": test_profile,
        "numbers": numbers,
        "taus": taus,
    }


def screen_candidate(match: dict, polynomial: dict, duration_s: float) -> bool:
    """Frozen exploratory screen; this is never a calibrated satellite identity."""
    primary = match["primary"]
    return bool(
        duration_s >= 15
        and primary["heldout_rank"] == 1
        and primary["heldout_rms_hz"] <= 200
        and primary["runner_gap_hz"] >= 50
        and primary["near_count"] == 1
        and not primary["at_boundary"]
        and primary["heldout_rms_hz"] <= polynomial["selected_heldout_rms_hz"]
    )


def doppler_from_ecef(
    position_km: np.ndarray,
    velocity_km_s: np.ndarray,
    observer_km: np.ndarray,
    rf_hz: float = 11.2e9,
) -> np.ndarray:
    relative = position_km - observer_km
    rate_km_s = np.sum(relative * velocity_km_s, axis=-1) / np.linalg.norm(relative, axis=-1)
    return -rf_hz / 299792.458 * rate_km_s


def fit_position(
    observed: np.ndarray,
    segment: np.ndarray,
    positions_km: np.ndarray,
    velocities_km_s: np.ndarray,
    base_km: np.ndarray,
    enu: np.ndarray,
    initial_enu_km: np.ndarray,
    *,
    training: np.ndarray,
    dimensions: int = 2,
    nuisance: np.ndarray | None = None,
    nuisance_bound: float | None = None,
    robust: bool = False,
    max_iterations: int = 40,
) -> dict:
    """Conditional Doppler positioning with profiled offsets and optional tau tangent.

    Identity/ephemeris inputs must be independently frozen by the caller. An
    optional nuisance column per satellite approximates orbit-time error locally;
    its inclusion diagnoses the position/orbit degeneracy, not precise orbit OD.
    """
    names = np.unique(segment)
    design = np.column_stack([segment == name for name in names]).astype(float)
    if nuisance is not None:
        design = np.column_stack([design, nuisance])
    inverse = np.linalg.pinv(design[training])

    def residual_at(point: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        observer = base_km + point @ enu[:dimensions]
        prediction = doppler_from_ecef(positions_km, velocities_km_s, observer)
        raw = observed - prediction
        parameters = inverse @ raw[training]
        if nuisance is not None and nuisance_bound is not None:
            parameters[len(names) :] = np.clip(
                parameters[len(names) :], -nuisance_bound, nuisance_bound
            )
            remainder = raw - nuisance @ parameters[len(names) :]
            for j, name in enumerate(names):
                parameters[j] = np.mean(remainder[training & (segment == name)])
        return raw - design @ parameters, parameters

    state = np.asarray(initial_enu_km, dtype=float).copy()[:dimensions]
    converged = False
    for _iteration in range(max_iterations):
        residual, _ = residual_at(state)
        jacobian = np.column_stack(
            [
                (
                    residual_at(state + np.eye(dimensions)[j] * 0.01)[0]
                    - residual_at(state - np.eye(dimensions)[j] * 0.01)[0]
                )
                / 0.02
                for j in range(dimensions)
            ]
        )
        weights = np.ones(np.count_nonzero(training))
        if robust:
            scale = max(float(np.median(np.abs(residual[training])) * 1.4826), 10.0)
            weights = np.minimum(1.0, 1.5 * scale / np.maximum(np.abs(residual[training]), 1e-9))
        weighted_jacobian = jacobian[training] * np.sqrt(weights)[:, None]
        target = -residual[training] * np.sqrt(weights)
        old_cost = np.sum(weights * residual[training] ** 2)
        accepted = False
        regularization_scale = max(float(np.linalg.norm(weighted_jacobian, ord=2)), 1e-9)
        for ridge in (0, 1e-3, 0.01, 0.1, 1, 10):
            regularized = np.vstack(
                [weighted_jacobian, np.eye(dimensions) * regularization_scale * ridge]
            )
            delta = np.linalg.lstsq(regularized, np.r_[target, np.zeros(dimensions)], rcond=None)[0]
            delta *= min(1.0, 20.0 / max(float(np.linalg.norm(delta)), 1e-9))
            for damping in (1.0, 0.5, 0.25, 0.125, 0.0625, 0.015625):
                candidate = np.clip(state + damping * delta, -100, 100)
                candidate_residual, _ = residual_at(candidate)
                if np.sum(weights * candidate_residual[training] ** 2) <= old_cost:
                    state = candidate
                    accepted = True
                    break
            if accepted:
                break
        if accepted and np.linalg.norm(delta) < 1e-5:
            converged = True
            break
        if not accepted:
            break
    residual, nuisance_parameters = residual_at(state)
    singular = np.linalg.svd(jacobian[training], compute_uv=False)
    return {
        "enu_km": state.tolist(),
        "horizontal_error_m": float(np.linalg.norm(state[:2]) * 1000),
        "training_rms_hz": float(np.sqrt(np.mean(residual[training] ** 2))),
        "heldout_rms_hz": float(np.sqrt(np.mean(residual[~training] ** 2)))
        if np.any(~training)
        else None,
        "iterations": _iteration + 1,
        "converged": converged,
        "singular_values_hz_per_km": singular.tolist(),
        "condition": float(singular.max() / max(singular.min(), 1e-15)),
        "nuisance_parameters": nuisance_parameters.tolist(),
    }
