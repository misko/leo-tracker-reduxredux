"""Evaluation-only position/uncertainty summaries; no fitting or storage I/O."""

from __future__ import annotations

import math

import numpy as np

LEVELS = (0.5, 0.9, 0.95)


def covariance_coverage(error_km, covariance_km2):
    """Score a two-dimensional local Gaussian ellipse in matching coordinates.

    This measures reported coverage, not whether a Gaussian approximation is
    appropriate. A singular or indefinite covariance is unavailable, never an
    artificially precise zero-radius fix.
    """
    error = np.asarray(error_km, dtype=float)
    if error.shape != (2,) or not np.all(np.isfinite(error)):
        raise ValueError("position error must be a finite two-vector")
    unavailable = {"status": "unavailable", "covered": None, "major_95_km": None}
    if covariance_km2 is None:
        return unavailable
    covariance = np.asarray(covariance_km2, dtype=float)
    if covariance.shape != (2, 2) or not np.all(np.isfinite(covariance)):
        raise ValueError("covariance must be a finite 2x2 matrix")
    if not np.allclose(covariance, covariance.T, atol=1e-12, rtol=1e-8):
        raise ValueError("covariance must be symmetric")
    values = np.linalg.eigvalsh(covariance)
    if values[0] <= 0:
        return unavailable
    distance = float(error @ np.linalg.solve(covariance, error))
    return {
        "status": "available",
        "mahalanobis_squared": distance,
        "covered": {str(level): bool(distance <= -2 * math.log1p(-level)) for level in LEVELS},
        "major_95_km": float(np.sqrt(-2 * math.log(0.05) * values[-1])),
    }


def _wilson(successes, count):
    z = 1.959963984540054
    p = successes / count
    divisor = 1 + z * z / count
    centre = (p + z * z / (2 * count)) / divisor
    half = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / divisor
    return [max(0.0, centre - half), min(1.0, centre + half)]


def summarize_trials(trials, *, independent=True):
    """Retain failures and missing uncertainty in explicit denominators.

    Set independent=False for overlapping data subsets. Conditional Gaussian
    coverage is accompanied by the fraction of all attempted trials that both
    return an uncertainty region and cover the reference position.
    """
    trials = list(trials)
    errors, uncertainty = [], []
    failures = 0
    for trial in trials:
        if not trial.get("converged", False) or trial.get("error_km") is None:
            failures += 1
            continue
        error = np.asarray(trial["error_km"], dtype=float)
        scored = covariance_coverage(error, trial.get("covariance_km2"))
        errors.append(float(np.linalg.norm(error) * 1000))
        if scored["status"] == "available":
            uncertainty.append(scored)
    coverage = {}
    for level in LEVELS:
        count = sum(row["covered"][str(level)] for row in uncertainty)
        coverage[str(level)] = {
            "covered": count,
            "uncertainty_denominator": len(uncertainty),
            "conditional_coverage": count / len(uncertainty) if uncertainty else None,
            "covered_fraction_all_trials": count / len(trials) if trials else None,
            "wilson_95_interval": _wilson(count, len(uncertainty))
            if independent and uncertainty else None,
        }
    return {
        "trials": len(trials),
        "failed_fixes": failures,
        "failed_fraction": failures / len(trials) if trials else None,
        "position_scored": len(errors),
        "uncertainty_scored": len(uncertainty),
        "independent_trials": independent,
        "error_m_quantiles": {
            str(level): float(np.quantile(errors, level)) if errors else None for level in LEVELS
        },
        "sub_km_fraction_scored": float(np.mean(np.asarray(errors) < 1000)) if errors else None,
        "coverage": coverage,
    }
