"""Sequential, incumbent-preserving satellite timing profiles at fixed geometry."""

from __future__ import annotations

import time

import numpy as np
from prediction_plan import SharedPredictionPlan


def _predict(data, parameters, satellites):
    predicted, visible, _ = SharedPredictionPlan(data, satellites).predict(parameters)
    shape = (len(data.times), len(satellites))
    return np.asarray(predicted).reshape(shape), np.asarray(visible).reshape(shape)


def timing_grid(incumbent, *, bound_s=3.0, step_s=0.1):
    if (
        not np.isfinite(incumbent) or not np.isfinite(bound_s)
        or not np.isfinite(step_s) or bound_s <= 0 or step_s <= 0
        or abs(incumbent) > bound_s
    ):
        raise ValueError("timing grid requires finite positive limits and a feasible incumbent")
    count = int(np.ceil(2 * bound_s / step_s)) + 1
    if count > 1001:
        raise ValueError("timing grid exceeds bounded node count")
    values = np.unique(np.r_[np.linspace(-bound_s, bound_s, count), incumbent])
    return sorted(values.tolist(), key=lambda value: (abs(value - incumbent), value))


def profile_timing_offsets(
    data, source_parameters, satellites, prepared, *, cavity_factory,
    detection_probability, sigma_hz=200.0, clutter_rate=2.0,
    tau_sigma_s=1.0, tau_bound_s=3.0, step_s=0.1, budget_s=20.0,
    predictor=_predict,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= 30:
        raise ValueError("profile budget must lie in (0, 30]")
    if not np.isfinite(tau_sigma_s) or tau_sigma_s <= 0:
        raise ValueError("tau prior width must be positive and finite")
    satellites = np.asarray(satellites, dtype=int)
    parameters = np.asarray(source_parameters, dtype=float).copy()
    if (
        satellites.ndim != 1 or not len(satellites)
        or len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0) or np.any(6 + satellites >= len(parameters))
        or parameters.ndim != 1 or np.any(~np.isfinite(parameters))
    ):
        raise ValueError("parameters and selected satellite indices must be valid")
    grids = [timing_grid(parameters[6 + satellite], bound_s=tau_bound_s, step_s=step_s)
             for satellite in satellites]
    started = time.monotonic()
    deadline = started + budget_s
    plans = {}

    def predict_candidate(values, selected):
        if predictor is not _predict:
            return predictor(data, values, selected)
        key = tuple(selected)
        if key not in plans:
            plans[key] = SharedPredictionPlan(data, selected)
        means, mask, _ = plans[key].predict(values)
        shape = (len(data.times), len(selected))
        return np.asarray(means).reshape(shape), np.asarray(mask).reshape(shape)

    predicted, visible = predict_candidate(parameters, satellites)

    def prior(values):
        return 0.5 * float(np.sum((values[6 + satellites] / tau_sigma_s) ** 2))

    def full_objective(means, visibility, values):
        result = prepared.evaluate(
            means, visibility, sigma_hz=sigma_hz, detection_probability=detection_probability,
            clutter_rate=clutter_rate, implementation="batched",
        )
        return -float(result["total_log_likelihood"]) + prior(values)

    objective = full_objective(predicted, visible, parameters)
    initial_objective = objective
    profiles = []
    for column, satellite in enumerate(satellites):
        if time.monotonic() >= deadline:
            break
        scorer = cavity_factory(
            prepared, predicted, visible, column, sigma_hz=sigma_hz,
            detection_probability=detection_probability, clutter_rate=clutter_rate,
        )
        reproduced = -float(scorer.evaluate(
            predicted[:, column], visible[:, column],
        )["total_log_likelihood"]) + prior(parameters)
        if not np.isclose(reproduced, objective, rtol=0, atol=1e-6):
            raise ValueError("cavity score does not reproduce the current joint objective")
        incumbent_tau = float(parameters[6 + satellite])
        other_prior = prior(parameters) - 0.5 * (incumbent_tau / tau_sigma_s) ** 2
        best_tau = incumbent_tau
        best_score = objective
        best_mean = predicted[:, column].copy()
        best_visible = visible[:, column].copy()
        evaluated = []
        for tau in grids[column]:
            if time.monotonic() >= deadline:
                break
            candidate = parameters.copy()
            candidate[6 + satellite] = tau
            mean, mask = predict_candidate(candidate, np.asarray([satellite]))
            score = -float(scorer.evaluate(mean[:, 0], mask[:, 0])["total_log_likelihood"])
            score += other_prior + 0.5 * (tau / tau_sigma_s) ** 2
            if not np.isfinite(score):
                raise FloatingPointError("profile objective must be finite")
            evaluated.append({"tau_s": float(tau), "objective": float(score)})
            if score < best_score - 1e-7:
                best_tau, best_score = float(tau), float(score)
                best_mean, best_visible = mean[:, 0].copy(), mask[:, 0].copy()
        profiles.append({
            "satellite_index": int(satellite), "incumbent_tau_s": incumbent_tau,
            "selected_tau_s": best_tau, "initial_objective": objective,
            "selected_objective": best_score, "grid_node_count": len(grids[column]),
            "evaluated": evaluated, "complete": len(evaluated) == len(grids[column]),
        })
        parameters[6 + satellite] = best_tau
        predicted[:, column], visible[:, column] = best_mean, best_visible
        objective = best_score
    final_objective = full_objective(predicted, visible, parameters)
    if not np.isclose(final_objective, objective, rtol=0, atol=1e-6):
        raise ValueError("profiled objective does not reproduce full finite-set evaluation")
    if final_objective > initial_objective + 1e-6:
        raise ValueError("coordinate profiling lost its incumbent")
    complete = len(profiles) == len(satellites) and all(row["complete"] for row in profiles)
    return {
        "parameters": parameters, "initial_objective": initial_objective,
        "objective": final_objective, "complete": complete,
        "status": "complete_pass" if complete else "budget_exhausted",
        "profiles": profiles, "elapsed_s": time.monotonic() - started,
        "satellite_order": satellites, "step_s": step_s,
        "tau_bound_s": tau_bound_s, "tau_sigma_s": tau_sigma_s,
        "policy": "Sequential exact conditional profiles; all other parameters fixed; no truth",
    }
