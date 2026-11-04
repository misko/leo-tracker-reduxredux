"""Exact pre-RF phase forecast mathematics, independent of historical workers."""

import math

import numpy as np
from sgp4.api import Satrec

from leo.sky.frames import julian_day_from_utc_ns


def causal_phase_sigma(alignment_s, age_s, epoch_gap_s):
    """Conservative disagreement proxy, not a calibrated probability interval."""
    if not np.isfinite([alignment_s, age_s, epoch_gap_s]).all() or age_s < 0 or epoch_gap_s <= 0:
        raise ValueError("finite causal ages and strictly ordered epochs required")
    return float(np.clip(np.hypot(1.0, alignment_s * age_s / epoch_gap_s), 1.0, 15.0))


def transition(a, b, c):
    target = c["collected_utc_ns"]
    if not (
        a["collected_utc_ns"] <= b["collected_utc_ns"] <= target
        and a["epoch"] < b["epoch"] < c["epoch"] <= target
    ):
        return None
    gap = (b["epoch"] - a["epoch"]) / 1e9
    if gap < 1:
        return None
    jd, fr = julian_day_from_utc_ns(np.array([target]))
    states = [Satrec.twoline2rv(*v["lines"]).sgp4(float(jd[0]), float(fr[0])) for v in (a, b, c)]
    if any(s[0] for s in states):
        return None
    pa, pb, pc = [np.asarray(s[1]) for s in states]
    velocity = np.asarray(states[1][2])
    norm = float(velocity @ velocity)
    old = float((pa - pb) @ velocity / norm)
    innovation = float((pc - pb) @ velocity / norm)
    age = (target - b["epoch"]) / 1e9
    prediction = -np.clip(age / gap, 0, 2) * old
    return dict(
        validation_time_ns=target,
        old_middle_alignment_s=old,
        next_innovation_s=innovation,
        unit_forecast_s=float(prediction),
        age_s=age,
        epoch_gap_s=gap,
        predicted_sigma_s=causal_phase_sigma(old, age, gap),
    )


def select(rows):
    candidates = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    if not rows:
        return dict(shrinkage=0.0, scores=[0.0] * 5, candidates=candidates, transitions=0)
    target = np.array([r["next_innovation_s"] for r in rows])
    prediction = np.array([r["unit_forecast_s"] for r in rows])
    sigma = np.array([r["predicted_sigma_s"] for r in rows])
    limit = np.minimum(15.0, 3 * sigma)
    scores = [
        float(np.sum(np.log1p(((target - np.clip(v * prediction, -limit, limit)) / sigma) ** 2)))
        for v in candidates
    ]
    chosen = int(np.argmin(scores))
    # Require an improvement above a one-parameter BIC-style log N cost.
    improvement = 2 * (scores[0] - scores[chosen])
    if improvement <= np.log(len(rows)):
        chosen = 0
    return dict(
        shrinkage=float(candidates[chosen]),
        scores=scores,
        candidates=candidates,
        transitions=len(rows),
        robust_improvement=improvement,
        penalty_log_N=float(np.log(len(rows))),
        not_calibrated_probability_model=True,
    )


def evaluate(rows, rho):
    if not rows:
        return dict(count=0)
    target = np.array([r["next_innovation_s"] for r in rows])
    pred = np.array([r["unit_forecast_s"] for r in rows])
    sigma = np.array([r["predicted_sigma_s"] for r in rows])
    limit = np.minimum(15.0, 3 * sigma)
    error = target - np.clip(rho * pred, -limit, limit)
    return dict(
        count=len(rows),
        median_absolute_error_s=float(np.median(abs(error))),
        RMS_s=float(np.sqrt(np.mean(error**2))),
        median_abs_standardized_error=float(np.median(abs(error / sigma))),
        fraction_within_one_sigma=float(np.mean(abs(error) < sigma)),
    )


def distribution_cost(errors, sigma, multiplier, nu):
    scale = np.asarray(sigma) * multiplier
    z = np.asarray(errors) / scale
    if nu is None:
        return np.log(2 * np.pi) + 2 * np.log(scale) + z * z
    return (
        np.log((nu - 2) * np.pi)
        + 2 * np.log(scale)
        + 2 * math.lgamma(nu / 2)
        - 2 * math.lgamma((nu + 1) / 2)
        + (nu + 1) * np.log1p(z * z / (nu - 2))
    )


def select_distribution(rows):
    if len(rows) < 30:
        return dict(shrinkage=0.0, multiplier=1.0, nu=None, fallback=True)
    target = np.array([r["next_innovation_s"] for r in rows])
    pred = np.array([r["unit_forecast_s"] for r in rows])
    sigma = np.array([r["predicted_sigma_s"] for r in rows])
    limit = np.minimum(15.0, 3 * sigma)
    best = None
    for rho in (0.0, 0.25, 0.5, 0.75, 1.0):
        error = target - np.clip(rho * pred, -limit, limit)
        for nu in (None, 3.0, 4.0, 8.0, 16.0):
            for multiplier in np.unique(np.r_[1.0, np.geomspace(0.1, 4.0, 51)]):
                score = float(distribution_cost(error, sigma, multiplier, nu).sum())
                if best is None or score < best["cost"]:
                    best = dict(shrinkage=rho, multiplier=float(multiplier), nu=nu, cost=score)
    baseline = float(distribution_cost(target, sigma, 1.0, None).sum())
    best.update(
        baseline_cost=baseline,
        transitions=len(rows),
        penalty=3 * np.log(len(rows)),
        fallback=baseline - best["cost"] <= 3 * np.log(len(rows)),
    )
    if best["fallback"]:
        best.update(shrinkage=0.0, multiplier=1.0, nu=None)
    return best


def evaluate_distribution(rows, parameters):
    if not rows:
        return dict(count=0)
    target = np.array([r["next_innovation_s"] for r in rows])
    pred = np.array([r["unit_forecast_s"] for r in rows])
    sigma = np.array([r["predicted_sigma_s"] for r in rows])
    limit = np.minimum(15.0, 3 * sigma)
    error = target - np.clip(parameters["shrinkage"] * pred, -limit, limit)
    return dict(
        count=len(rows),
        negative_twice_log_density=float(
            distribution_cost(error, sigma, parameters["multiplier"], parameters["nu"]).sum()
        ),
        median_absolute_error_s=float(np.median(abs(error))),
        standard_deviation_parameterization=True,
    )


def forecast(history):
    """Preserve the original internal temporal prior-calibration split.

    This is a mathematical extraction, not a new randomized validation study.
    All update targets precede the RF scan; no radio or GPS residual is an input.
    """
    cutoff = history["cutoff_utc_ns"]
    rows = []
    for number, versions in history["past_versions"].items():
        if not all(v["epoch"] <= cutoff and v["collected_utc_ns"] <= cutoff for v in versions):
            raise ValueError("Phase history contains post-scan elements")
        for index in range(2, len(versions)):
            row = transition(*versions[index - 2 : index + 1])
            if row:
                rows.append(dict(norad=int(number), **row))
    times = sorted({r["validation_time_ns"] for r in rows})
    boundary = times[max(0, int(len(times) * 0.7) - 1)] if times else cutoff
    training = [r for r in rows if r["validation_time_ns"] <= boundary]
    validation = [r for r in rows if r["validation_time_ns"] > boundary]
    prefix, full = select(training), select(rows)
    result = dict(
        case=history["case"],
        strictly_pre_RF=True,
        GPS_or_radio_used=False,
        temporal_split_boundary_ns=boundary,
        prefix_selection=prefix,
        all_past_selection=full,
        heldout_past_baseline=evaluate(validation, 0),
        heldout_past_forecast=evaluate(validation, prefix["shrinkage"]),
        all_past_baseline=evaluate(rows, 0),
        all_past_forecast=evaluate(rows, full["shrinkage"]),
        TLE_updates_are_proxies_not_orbit_truth=True,
        transitions=rows,
    )
    prefix_distribution = select_distribution(training)
    all_distribution = select_distribution(rows)
    result.update(
        prefix_distribution=prefix_distribution,
        all_past_distribution=all_distribution,
        distribution_validation=evaluate_distribution(validation, prefix_distribution),
        original_distribution_validation=evaluate_distribution(
            validation, dict(shrinkage=0.0, multiplier=1.0, nu=None)
        ),
    )
    return result
