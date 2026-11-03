"""Rough tracks, shared RX lines, then sparse grouped-GLRT refinement."""

import time

import numpy as np
from grouped_likelihood import DEFAULT_ALIAS_HZ, prepare_grouped_likelihood
from prediction_jacobian import paired_prediction_jacobian
from track_seed import fit_rough


def frozen_row_weights(data):
    features = np.column_stack(
        [
            data.group,
            data.times,
            data.rf,
            data.receiver,
            data.channel,
            np.mod(data.measured, DEFAULT_ALIAS_HZ),
        ]
    )
    _, inverse, counts = np.unique(features, axis=0, return_inverse=True, return_counts=True)
    return 1 / counts[inverse]


def candidate_ladder(assignments, sizes=(4, 8, 12)):
    support = {}
    for row in assignments:
        if row["accepted"] and row["source_groups"] >= 15 and row["span_s"] >= 15:
            satellite = row["satellite_index"]
            support[satellite] = support.get(satellite, 0) + row["source_groups"]
    if not support:
        raise ValueError("No satellite has an accepted track with 15 groups and 15 s span")
    ranked = sorted(support, key=lambda satellite: (-support[satellite], satellite))
    lengths = sorted({min(size, len(ranked)) for size in sizes})
    return [
        (
            np.asarray(ranked[:size], dtype=int),
            np.asarray([support[satellite] for satellite in ranked[:size]], dtype=float),
        )
        for size in lengths
    ]


def fit_receiver_lines(data, rough, slope_bound=50.0):
    from scipy.optimize import least_squares

    reference_time = getattr(data, "reference_time_s", 150.0)
    parameters = np.zeros(6 + len(data.numbers))
    parameters[:2] = rough["position_km"]
    for receiver in (0, 1):
        assignments = [
            row for row in rough["assignments"] if row["accepted"] and row["receiver"] == receiver
        ]
        if not assignments:
            raise ValueError(f"No accepted tracks for RX{receiver}")
        rows = np.concatenate([row["rows"] for row in assignments])
        satellites = np.concatenate(
            [np.full(len(row["rows"]), row["satellite_index"]) for row in assignments]
        )
        weights = np.concatenate(
            [
                np.full(len(row["rows"]), np.sqrt(min(len(row["rows"]), 100)) / len(row["rows"]))
                for row in assignments
            ]
        )
        predicted, visible = data.predict(parameters, rows=rows, satellites=satellites)
        times = data.times[rows] - reference_time
        values = data.measured[rows] - predicted
        values = (values + DEFAULT_ALIAS_HZ / 2) % DEFAULT_ALIAS_HZ - DEFAULT_ALIAS_HZ / 2
        if not np.any(visible):
            raise ValueError("No visible rough track predictions")
        histogram, edges = np.histogram(
            values[visible], bins=128, range=(-DEFAULT_ALIAS_HZ / 2, DEFAULT_ALIAS_HZ / 2)
        )
        peaks = np.argsort(-histogram, kind="stable")[:3]
        best = None

        def residual(vector, values=values, times=times, weights=weights, visible=visible):
            errors = values - vector[0] * 1000 - vector[1] * 10 * times
            errors = (errors + DEFAULT_ALIAS_HZ / 2) % DEFAULT_ALIAS_HZ - DEFAULT_ALIAS_HZ / 2
            return np.sqrt(weights[visible]) * errors[visible] / 200

        for peak in peaks:
            for slope in (-min(20.0, slope_bound), 0.0, min(20.0, slope_bound)):
                fitted = least_squares(
                    residual,
                    [(edges[peak] + edges[peak + 1]) / 2000, slope / 10],
                    bounds=([-np.inf, -slope_bound / 10], [np.inf, slope_bound / 10]),
                    loss="soft_l1",
                    max_nfev=80,
                )
                if fitted.success and (best is None or fitted.cost < best.cost):
                    best = fitted
        if best is None:
            raise RuntimeError(f"RX{receiver} line initialization did not converge")
        parameters[2 + 2 * receiver : 4 + 2 * receiver] = best.x * [1000, 10]
    return parameters


def refine_bank(
    data,
    initial,
    satellites,
    support,
    prepared,
    *,
    sigma_hz=200.0,
    tau_sigma_s=1.0,
    tau_bound_s=3.0,
    slope_bound=50.0,
    budget_s=45.0,
    share_predictions=False,
):
    from scipy.optimize import minimize

    active = np.r_[np.arange(6), 6 + satellites]
    scales = np.r_[20, 20, 1000, 10, 1000, 10, np.ones(len(satellites))]
    weights = support / np.sum(support)
    prediction_plan = None
    if share_predictions:
        from prediction_plan import SharedPredictionPlan

        prediction_plan = SharedPredictionPlan(data, satellites)
    else:
        rows = np.repeat(np.arange(len(data.times)), len(satellites))
        paired_satellites = np.tile(satellites, len(data.times))
    bounds = [
        (-10, 10),
        (-10, 10),
        (None, None),
        (-slope_bound / 10, slope_bound / 10),
        (None, None),
        (-slope_bound / 10, slope_bound / 10),
    ]
    bounds += [(-tau_bound_s, tau_bound_s)] * len(satellites)
    deadline = time.monotonic() + budget_s
    best = [float("inf"), initial[active] / scales]
    evaluations = 0

    def evaluate(vector, check_time=True):
        nonlocal evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("Sparse GLRT refinement budget exhausted")
        parameters = initial.copy()
        parameters[active] = vector * scales
        if prediction_plan is None:
            predicted, visible, jacobian = paired_prediction_jacobian(
                data, parameters, rows, paired_satellites
            )
        else:
            predicted, visible, jacobian = prediction_plan.predict(parameters)
        evaluations += 1
        result = prepared.evaluate(
            predicted.reshape(-1, len(satellites)),
            visible.reshape(-1, len(satellites)),
            sigma_hz=sigma_hz,
            satellite_weights=weights,
            background_mass=0.2,
            return_gradient=True,
        )
        prior = 0.5 * np.sum((parameters[6 + satellites] / tau_sigma_s) ** 2)
        value = -result["total_log_likelihood"] + prior
        gradient = -jacobian.transpose_multiply(result.pop("prediction_gradient").ravel())
        gradient[6 + satellites] += parameters[6 + satellites] / tau_sigma_s**2
        if value < best[0]:
            best[:] = [float(value), vector.copy()]
        return float(value), result, parameters, gradient[active] * scales

    def objective_and_gradient(vector):
        value, _, _, gradient = evaluate(vector)
        return value, gradient

    started = time.monotonic()
    try:
        fitted = minimize(
            objective_and_gradient,
            initial[active] / scales,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 500, "maxfun": 1000, "ftol": 1e-9},
        )
        vector = fitted.x
        success, message = bool(fitted.success), str(fitted.message)
        iterations = int(fitted.nit)
    except TimeoutError as error:
        vector = best[1]
        success, message = False, str(error)
        iterations = None
    objective, likelihood, parameters, gradient = evaluate(vector, check_time=False)
    projected_gradient = gradient.copy()
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None and vector[index] <= lower and gradient[index] > 0:
            projected_gradient[index] = 0
        if upper is not None and vector[index] >= upper and gradient[index] < 0:
            projected_gradient[index] = 0
    penalty = 0.5 * len(satellites) * np.log(len(likelihood["group_values"]))
    return {
        "parameters": parameters,
        "success": success,
        "message": message,
        "status": "converged" if success else "nonconverged",
        "satellite_indices": satellites,
        "catalog_numbers": data.numbers[satellites],
        "satellite_count": len(satellites),
        "objective": objective,
        "selection_score": objective + penalty,
        "entry_penalty": float(penalty),
        "satellite_weights": weights,
        "satellite_support": likelihood["satellite_support"],
        "null_support": likelihood["null_support"],
        "groups": len(likelihood["group_values"]),
        "tau_sigma_s": tau_sigma_s,
        "tau_bound_s": tau_bound_s,
        "elapsed_s": time.monotonic() - started,
        "evaluations": evaluations,
        "iterations": iterations,
        "projected_gradient_inf_norm": float(np.max(np.abs(projected_gradient))),
        "gradient_method": "Analytic likelihood and orbit derivatives; observer ECEF central 1m",
        "shared_predictions": bool(share_predictions),
    }


def select_trials(trials):
    finite = [trial for trial in trials if np.isfinite(trial["selection_score"])]
    if not finite:
        raise ValueError("No finite model-selection scores")
    successful = [trial for trial in finite if trial["success"]]
    score_leader = min(finite, key=lambda trial: trial["selection_score"])
    converged_leader = (
        min(successful, key=lambda trial: trial["selection_score"]) if successful else None
    )
    resolved = len(successful) == len(trials)
    return {
        "winner": score_leader,
        "score_leader": score_leader,
        "converged_leader": converged_leader,
        "selection_resolved": resolved,
        "success": resolved,
    }


def fit_staged(data, rough=None):
    rough = fit_rough(data) if rough is None else rough
    initial = fit_receiver_lines(data, rough)
    prepared = prepare_grouped_likelihood(
        data.measured, data.group, row_weights=frozen_row_weights(data)
    )
    trials = [
        refine_bank(data, initial, satellites, support, prepared)
        for satellites, support in candidate_ladder(rough["assignments"])
    ]
    return {
        "rough": rough,
        "rx_initial": initial,
        "trials": trials,
        **select_trials(trials),
        "scope": "Grouped GLRT likelihood proxy; fixed rough "
        "satellite-weight proportions, explicit uniform background mass .2, "
        "Gaussian tau prior and .5*K*log(group_count) entry penalty. "
        "No reference coordinates are accepted by this solver.",
    }
