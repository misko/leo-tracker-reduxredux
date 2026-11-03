"""Reset-aware shared-prediction Gauss-Newton prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from capture_reset_fit import (
    canonicalize_capture_jumps,
    capture_reset_model_penalty,
    capture_reset_offsets,
    initialize_from_child_fits,
)
from coherent_fit import FixedBankLikelihood, anchor_partition, frozen_identity_masses
from gauss_newton import (
    _free_variables,
    _newton_stationarity,
    _project,
    _projected_gradient,
)
from grouped_likelihood import DEFAULT_ALIAS_HZ
from prediction_plan import SharedPredictionPlan
from staged_fit import candidate_ladder, frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


@dataclass
class _ResetState:
    vector: np.ndarray
    parameters: np.ndarray
    capture_jumps_hz: np.ndarray
    objective: float
    gradient: np.ndarray
    hessian: np.ndarray
    likelihood: dict


_NUMERICAL_FALLBACK_REASONS = frozenset(
    {
        "budget_exhausted",
        "iteration_limit",
        "no_acceptable_step",
        "nonfinite_step",
        "singular_curvature",
        "tiny_accepted_step_without_gradient_convergence",
    }
)


def _validate_capture_data(data):
    capture_count = len(data.child_sessions)
    capture_index = np.asarray(data.capture_index, dtype=int)
    if capture_count < 2:
        raise ValueError("reset-aware GN requires at least two captures")
    if capture_index.shape != np.asarray(data.times).shape:
        raise ValueError("capture_index must align with observation times")
    if np.any(capture_index < 0) or np.any(capture_index >= capture_count):
        raise ValueError("capture_index falls outside child_sessions")
    return capture_count


def apply_capture_offsets(data, prediction, capture_jumps_hz, satellite_count):
    """Add explicit row-indexed capture/RX offsets to a prediction matrix."""

    prediction = np.asarray(prediction, dtype=float)
    expected = (len(data.times), int(satellite_count))
    if prediction.shape != expected:
        raise ValueError("prediction matrix does not match rows and satellites")
    offsets = capture_reset_offsets(data, capture_jumps_hz, np.arange(len(data.times), dtype=int))
    return prediction + offsets[:, None]


def capture_indicator_fisher_terms(
    data,
    plan,
    expanded_jacobian,
    prediction_gradient,
    prediction_precision,
):
    """Return exact reset gradient, Fisher block, and base/reset cross block."""

    capture_count = _validate_capture_data(data)
    reset_count = 2 * (capture_count - 1)
    row_count = len(data.times)
    satellite_count = len(plan.satellites)
    prediction_gradient = np.asarray(prediction_gradient, dtype=float)
    prediction_precision = np.asarray(prediction_precision, dtype=float)
    expected = (row_count, satellite_count)
    if prediction_gradient.shape != expected or prediction_precision.shape != expected:
        raise ValueError("likelihood derivatives must match rows and selected satellites")
    if np.any(~np.isfinite(prediction_gradient)) or np.any(~np.isfinite(prediction_precision)):
        raise FloatingPointError("likelihood derivatives must be finite")
    if np.any(prediction_precision < 0):
        raise ValueError("prediction precision must be non-negative")
    base = expanded_jacobian.base
    candidate_count = base.candidate_count
    unique_count = len(plan.unique_rows)
    shared = np.asarray(base.shared, dtype=float).reshape(unique_count, satellite_count, 6)
    tau = np.asarray(base.tau, dtype=float).reshape(unique_count, satellite_count)
    inverse = np.asarray(plan.inverse, dtype=int)
    if inverse.shape != (row_count,):
        raise ValueError("shared prediction expansion does not match observation rows")
    capture = np.asarray(data.capture_index, dtype=int)
    receiver = np.asarray(data.receiver, dtype=int)
    reset_index = np.where(capture == 0, -1, 2 * (capture - 1) + receiver)
    reset_gradient = np.zeros(reset_count, dtype=float)
    reset_hessian = np.zeros((reset_count, reset_count), dtype=float)
    cross = np.zeros((6 + candidate_count, reset_count), dtype=float)
    satellites = np.asarray(plan.satellites, dtype=int)
    for index in range(reset_count):
        rows = np.flatnonzero(reset_index == index)
        if not len(rows):
            continue
        weights = prediction_precision[rows]
        source_rows = inverse[rows]
        reset_gradient[index] = -float(np.sum(prediction_gradient[rows]))
        reset_hessian[index, index] = float(np.sum(weights))
        cross[:6, index] = np.sum(weights[..., None] * shared[source_rows], axis=(0, 1))
        cross[6 + satellites, index] = np.sum(weights * tau[source_rows], axis=0)
    return reset_gradient, reset_hessian, cross


def numerical_failure_allows_fallback(trial):
    """Return whether a sealed largest-bank trial permits numerical fallback."""

    if trial.get("success"):
        return False
    return trial.get("convergence_reason") in _NUMERICAL_FALLBACK_REASONS


def independent_fresh_bank_starts(initialized, bank_count):
    """Return independent copies of one child-derived initializer per bank."""

    if not isinstance(bank_count, int) or bank_count <= 0:
        raise ValueError("bank_count must be a positive integer")
    parameters = np.asarray(initialized["parameters"], dtype=float)
    jumps = canonicalize_capture_jumps(initialized["capture_jumps_hz"])
    if parameters.ndim != 1 or np.any(~np.isfinite(parameters)):
        raise ValueError("fresh parameters must be a finite vector")
    return [(parameters.copy(), jumps.copy()) for _ in range(bank_count)]


def refine_largest_same_bank_fallback(
    refiner,
    data,
    direct_trial,
    satellites,
    support,
    likelihood,
    *,
    warm_budget_s=5.0,
    final_budget_s=20.0,
):
    """Warm and retry only one numerically failed largest candidate bank."""

    if not numerical_failure_allows_fallback(direct_trial):
        raise ValueError("largest-bank fallback requires an allowed numerical failure")
    parameters = np.asarray(direct_trial["parameters"], dtype=float).copy()
    jumps = canonicalize_capture_jumps(direct_trial["capture_jumps_hz"])
    attempts = []
    for sigma_hz in (2000.0, 1000.0, 500.0):
        trial = refiner(
            data,
            parameters,
            jumps,
            satellites,
            support,
            likelihood,
            sigma_hz=sigma_hz,
            budget_s=warm_budget_s,
        )
        trial["attempt_role"] = "same_bank_warmup"
        trial["sigma_hz"] = sigma_hz
        attempts.append(trial)
        parameters = np.asarray(trial["parameters"], dtype=float).copy()
        jumps = canonicalize_capture_jumps(trial["capture_jumps_hz"])
    final = refiner(
        data,
        parameters,
        jumps,
        satellites,
        support,
        likelihood,
        sigma_hz=200.0,
        budget_s=final_budget_s,
    )
    final["attempt_role"] = "same_bank_final"
    final["sigma_hz"] = 200.0
    attempts.append(final)
    return attempts


def refine_capture_reset_gauss_newton(
    data,
    initial_parameters,
    initial_jumps_hz,
    satellites,
    support,
    prepared,
    *,
    sigma_hz=200.0,
    tau_sigma_s=1.0,
    tau_bound_s=3.0,
    slope_bound_hz_s=50.0,
    budget_s=20.0,
):
    """Refine one reset model bank with unchanged GNv2 stationarity semantics."""

    capture_count = _validate_capture_data(data)
    candidate_count = len(data.numbers)
    initial_parameters = np.asarray(initial_parameters, dtype=float)
    initial_jumps_hz = canonicalize_capture_jumps(initial_jumps_hz)
    satellites = np.asarray(satellites, dtype=int)
    support = np.asarray(support, dtype=float)
    if initial_parameters.shape != (6 + candidate_count,) or np.any(
        ~np.isfinite(initial_parameters)
    ):
        raise ValueError("initial parameters do not match the candidate bank")
    if initial_jumps_hz.shape != (capture_count, 2):
        raise ValueError("initial jumps do not match capture count")
    if satellites.ndim != 1 or not len(satellites):
        raise ValueError("satellites must be a nonempty vector")
    if (
        len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= candidate_count)
    ):
        raise ValueError("satellites must be unique valid candidate indices")
    if support.shape != satellites.shape or np.any(~np.isfinite(support)) or np.any(support <= 0):
        raise ValueError("support must be positive and match satellites")
    for value, name in (
        (sigma_hz, "sigma_hz"),
        (tau_sigma_s, "tau_sigma_s"),
        (tau_bound_s, "tau_bound_s"),
        (slope_bound_hz_s, "slope_bound_hz_s"),
        (budget_s, "budget_s"),
    ):
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")

    active = np.r_[np.arange(6), 6 + satellites]
    parameter_scales = np.r_[
        20.0,
        20.0,
        1000.0,
        10.0,
        1000.0,
        10.0,
        np.ones(len(satellites)),
    ]
    reset_scales = np.full(2 * (capture_count - 1), 1000.0)
    scales = np.concatenate((parameter_scales, reset_scales))
    bounds = [
        (-10.0, 10.0),
        (-10.0, 10.0),
        (None, None),
        (-slope_bound_hz_s / 10.0, slope_bound_hz_s / 10.0),
        (None, None),
        (-slope_bound_hz_s / 10.0, slope_bound_hz_s / 10.0),
    ]
    bounds += [(-tau_bound_s, tau_bound_s)] * len(satellites)
    half_alias_khz = DEFAULT_ALIAS_HZ / 2000
    bounds += [(-half_alias_khz, half_alias_khz)] * len(reset_scales)
    satellite_weights = support / np.sum(support)
    plan = SharedPredictionPlan(data, satellites)
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None

    def evaluate(vector, *, check_time=True):
        nonlocal best, evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("Reset-aware Gauss-Newton refinement budget exhausted")
        split = len(active)
        parameters = initial_parameters.copy()
        parameters[active] = vector[:split] * parameter_scales
        jumps = np.zeros((capture_count, 2), dtype=float)
        jumps[1:] = (vector[split:] * reset_scales).reshape(capture_count - 1, 2)
        predicted, visible, jacobian = plan.predict(parameters)
        predicted = apply_capture_offsets(
            data,
            predicted.reshape(len(data.times), len(satellites)),
            jumps,
            len(satellites),
        )
        visible = visible.reshape(predicted.shape)
        evaluations += 1
        result = prepared.evaluate(
            predicted,
            visible,
            sigma_hz=sigma_hz,
            satellite_weights=satellite_weights,
            background_mass=0.2,
            return_gradient=True,
            return_precision=True,
        )
        prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
        prediction_precision = np.asarray(result["prediction_precision"], dtype=float)
        if prediction_gradient.shape != predicted.shape or prediction_precision.shape != (
            predicted.shape
        ):
            raise ValueError("prepared derivatives must match prediction shape")
        physical_gradient = -jacobian.transpose_multiply(prediction_gradient.ravel())
        physical_hessian = np.asarray(
            jacobian.normal_matrix(prediction_precision.ravel()), dtype=float
        )
        reset_gradient, reset_hessian, cross = capture_indicator_fisher_terms(
            data,
            plan,
            jacobian,
            prediction_gradient,
            prediction_precision,
        )
        tau_indices = 6 + satellites
        tau = parameters[tau_indices]
        prior = 0.5 * np.sum((tau / tau_sigma_s) ** 2)
        physical_gradient[tau_indices] += tau / tau_sigma_s**2
        physical_hessian[tau_indices, tau_indices] += 1.0 / tau_sigma_s**2
        objective = float(-result["total_log_likelihood"] + prior)
        gradient = np.concatenate((physical_gradient[active], reset_gradient)) * scales
        active_hessian = physical_hessian[np.ix_(active, active)]
        active_cross = cross[active]
        hessian = np.block(
            [
                [active_hessian, active_cross],
                [active_cross.T, reset_hessian],
            ]
        )
        hessian = hessian * scales[:, None] * scales[None, :]
        hessian = 0.5 * (hessian + hessian.T)
        if (
            not np.isfinite(objective)
            or np.any(~np.isfinite(gradient))
            or np.any(~np.isfinite(hessian))
        ):
            raise FloatingPointError("objective derivatives must be finite")
        likelihood = dict(result)
        likelihood.pop("prediction_gradient", None)
        likelihood.pop("prediction_precision", None)
        state = _ResetState(
            vector=np.asarray(vector, dtype=float).copy(),
            parameters=parameters,
            capture_jumps_hz=jumps,
            objective=objective,
            gradient=gradient,
            hessian=hessian,
            likelihood=likelihood,
        )
        if best is None or objective < best.objective:
            best = state
        return state

    vector = np.concatenate(
        (
            initial_parameters[active] / parameter_scales,
            initial_jumps_hz[1:].ravel() / reset_scales,
        )
    )
    vector = _project(vector, bounds)
    current = evaluate(vector, check_time=False)
    initial_objective = current.objective
    positive_diagonal = np.diag(current.hessian)
    positive_diagonal = positive_diagonal[positive_diagonal > 0]
    damping = max(
        1e-6,
        1e-3 * (float(np.median(positive_diagonal)) if len(positive_diagonal) else 1.0),
    )
    iterations = 0
    accepted_steps = 0
    rejected_steps = 0
    last_accepted_step_inf_norm = None
    last_accepted_loss_decrease = None
    success = False
    reason = "iteration_limit"

    try:
        while iterations < 200:
            if time.monotonic() > deadline:
                raise TimeoutError("Reset-aware Gauss-Newton refinement budget exhausted")
            projected_gradient = _projected_gradient(current.vector, current.gradient, bounds)
            if np.max(np.abs(projected_gradient)) <= 1e-4:
                success = True
                reason = "projected_gradient"
                break
            free = _free_variables(current.vector, current.gradient, bounds)
            stationarity = _newton_stationarity(
                current.objective, current.gradient, current.hessian, free, damping
            )
            if stationarity["low_damping_positive_newton_converged"]:
                success = True
                reason = "low_damping_positive_newton_decrement"
                break
            iterations += 1
            system = current.hessian[np.ix_(free, free)] + damping * np.eye(np.sum(free))
            try:
                step = np.zeros_like(current.vector)
                step[free] = np.linalg.solve(system, -current.gradient[free])
            except np.linalg.LinAlgError:
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "singular_curvature"
                    break
                continue
            if np.any(~np.isfinite(step)):
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "nonfinite_step"
                    break
                continue
            maximum = float(np.max(np.abs(step)))
            if maximum > 1.0:
                step /= maximum
            accepted = None
            accepted_step = None
            for fraction in (1.0, 0.5, 0.25, 0.125):
                candidate_vector = _project(current.vector + fraction * step, bounds)
                actual_step = candidate_vector - current.vector
                if not np.any(actual_step):
                    continue
                candidate = evaluate(candidate_vector)
                if candidate.objective < current.objective:
                    accepted = candidate
                    accepted_step = actual_step
                    break
            if accepted is None:
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "no_acceptable_step"
                    break
                continue
            previous_objective = current.objective
            current = accepted
            accepted_steps += 1
            damping = max(damping / 3.0, 1e-12)
            step_norm = float(np.max(np.abs(accepted_step)))
            improvement = previous_objective - current.objective
            last_accepted_step_inf_norm = step_norm
            last_accepted_loss_decrease = float(improvement)
            if step_norm <= 1e-6 and improvement <= 1e-8 * (1.0 + abs(previous_objective)):
                accepted_projected_gradient = _projected_gradient(
                    current.vector, current.gradient, bounds
                )
                if np.max(np.abs(accepted_projected_gradient)) <= 1e-4:
                    success = True
                    reason = "projected_gradient_after_tiny_step"
                else:
                    accepted_free = _free_variables(current.vector, current.gradient, bounds)
                    accepted_stationarity = _newton_stationarity(
                        current.objective,
                        current.gradient,
                        current.hessian,
                        accepted_free,
                        damping,
                    )
                    if accepted_stationarity["low_damping_positive_newton_converged"]:
                        success = True
                        reason = "low_damping_positive_newton_decrement_after_tiny_step"
                    else:
                        reason = "tiny_accepted_step_without_gradient_convergence"
                break
    except TimeoutError:
        reason = "budget_exhausted"
    except Exception as error:
        reason = f"evaluation_error:{type(error).__name__}:{error}"

    final_evaluation_error = None
    try:
        evaluate(best.vector, check_time=False)
        final = best
    except Exception as error:
        final = best
        success = False
        final_evaluation_error = f"{type(error).__name__}:{error}"
        if reason in ("projected_gradient", "projected_gradient_after_tiny_step"):
            reason = "final_evaluation_failed_after_convergence"
        if hasattr(prepared, "last_result"):
            prepared.last_result = dict(best.likelihood)
    projected_gradient = _projected_gradient(final.vector, final.gradient, bounds)
    final_free = _free_variables(final.vector, final.gradient, bounds)
    stationarity = _newton_stationarity(
        final.objective,
        final.gradient,
        final.hessian,
        final_free,
        damping,
    )
    likelihood = final.likelihood
    penalty = capture_reset_model_penalty(
        len(likelihood["group_values"]), len(satellites), capture_count
    )
    return {
        "parameters": final.parameters,
        "capture_jumps_hz": canonicalize_capture_jumps(final.capture_jumps_hz),
        "success": success,
        "message": reason,
        "status": "converged" if success else "nonconverged",
        "convergence_reason": reason,
        "algorithm_version": "complete-data-fisher-capture-reset-gn/v1",
        "gn_semantics": "complete-data-fisher-gn/v2",
        "final_evaluation_error": final_evaluation_error,
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": final.objective,
        "initial_objective": initial_objective,
        "selection_score": final.objective + penalty["total_penalty"],
        "model_penalty": penalty,
        "satellite_weights": satellite_weights,
        "satellite_support": likelihood["satellite_support"],
        "null_support": likelihood["null_support"],
        "groups": len(likelihood["group_values"]),
        "tau_sigma_s": float(tau_sigma_s),
        "tau_bound_s": float(tau_bound_s),
        "slope_bound_hz_s": float(slope_bound_hz_s),
        "jump_bound_hz": DEFAULT_ALIAS_HZ / 2,
        "elapsed_s": time.monotonic() - started,
        "evaluations": evaluations,
        "iterations": iterations,
        "accepted_steps": accepted_steps,
        "rejected_steps": rejected_steps,
        "last_accepted_step_inf_norm": last_accepted_step_inf_norm,
        "last_accepted_loss_decrease": last_accepted_loss_decrease,
        "damping": float(damping),
        "free_parameter_count": int(np.sum(final_free)),
        "zero_width_bound_count": 0,
        "projected_gradient_inf_norm": float(np.max(np.abs(projected_gradient))),
        "stationarity_thresholds": {
            "projected_gradient_inf_norm": 1e-4,
            "modeled_newton_relative_loss_decrease": 1e-10,
            "undamped_newton_step_inf_norm": 1e-5,
            "damping_to_free_min_eigenvalue": 1e-6,
            "positive_free_curvature_required": True,
        },
        **stationarity,
        "gradient_method": "Analytic orbit/RX/tau plus exact capture-indicator gradient",
        "curvature_method": "Complete-data/Fisher exact base/reset cross blocks plus tau prior",
        "shared_predictions": True,
        "capture_features_use_explicit_row_index": True,
        "best_finite_preserved": True,
    }


def fit_sealed_capture_reset_gn(data, sealed_reset_fit, *, budget_s_per_bank=20.0):
    """Refine every sealed reset trial independently with reset-aware GN."""

    if "fit" in sealed_reset_fit and "trials" not in sealed_reset_fit:
        sealed_reset_fit = sealed_reset_fit["fit"]
    rough = sealed_reset_fit["rough"]
    capture_count = _validate_capture_data(data)
    ladder = candidate_ladder(
        rough["assignments"], sizes=tuple(size * capture_count for size in (4, 8, 12))
    )
    sealed_trials = sealed_reset_fit["trials"]
    if len(ladder) != len(sealed_trials):
        raise ValueError("sealed reset trials do not match the frozen ladder")
    anchors = sealed_reset_fit["anchors"]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[np.asarray(anchor["groups"], dtype=int) for anchor in anchors],
    )
    trials = []
    started = time.monotonic()
    for (satellites, support), sealed in zip(ladder, sealed_trials, strict=True):
        if not np.array_equal(satellites, np.asarray(sealed["satellite_indices"], dtype=int)):
            raise ValueError("sealed trial satellite bank differs from frozen ladder")
        masses = {
            key: np.asarray(value, dtype=float) if isinstance(value, list) else value
            for key, value in sealed["identity_masses"].items()
        }
        likelihood = FixedBankLikelihood(prepared, masses)
        trial = refine_capture_reset_gauss_newton(
            data,
            sealed["parameters"],
            sealed["capture_jumps_hz"],
            satellites,
            support,
            likelihood,
            budget_s=budget_s_per_bank,
        )
        trial.pop("satellite_weights")
        trial["identity_masses"] = masses
        trial["sealed_reset_objective"] = float(sealed["objective"])
        trial["objective_delta_from_sealed"] = float(trial["objective"] - sealed["objective"])
        trial["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(trial)
    return {
        "rough": rough,
        "initializer": sealed_reset_fit["initializer"],
        "anchors": anchors,
        "full_bank": sealed_reset_fit["full_bank"],
        "keep_track_identity": True,
        "optimizer": "capture-reset-gauss-newton",
        "shared_predictions": True,
        "sealed_trial_start": True,
        "trials": trials,
        **select_trials(trials),
        "elapsed_s": time.monotonic() - started,
        "scope": "Independent reset-aware GNv2 refinements of every sealed capture-reset bank. "
        "Shared orbit predictions retain explicit row-indexed capture indicators. No reference "
        "coordinates or evaluation artifacts are accepted or read.",
    }


def fit_fresh_capture_reset_gn(
    data,
    rough,
    child_fit_receipts,
    *,
    direct_budget_s=20.0,
    warm_budget_s=5.0,
    final_budget_s=20.0,
):
    """Fit frozen banks from one fresh child initializer with bounded fallback."""

    capture_count = _validate_capture_data(data)
    initialized = initialize_from_child_fits(data, child_fit_receipts)
    anchors = anchor_partition(data, max_anchors=12 * capture_count)
    ladder = candidate_ladder(
        rough["assignments"], sizes=tuple(size * capture_count for size in (4, 8, 12))
    )
    full_bank = ladder[-1][0]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[np.asarray(anchor["groups"], dtype=int) for anchor in anchors],
    )
    starts = independent_fresh_bank_starts(initialized, len(ladder))
    trials = []
    bank_attempts = []
    started = time.monotonic()
    for index, ((satellites, support), (parameters, jumps)) in enumerate(
        zip(ladder, starts, strict=True)
    ):
        masses = frozen_identity_masses(anchors, full_bank, satellites)
        likelihood = FixedBankLikelihood(prepared, masses)
        direct = refine_capture_reset_gauss_newton(
            data,
            parameters,
            jumps,
            satellites,
            support,
            likelihood,
            budget_s=direct_budget_s,
        )
        direct["attempt_role"] = "direct_fresh"
        direct["sigma_hz"] = 200.0
        attempts = [direct]
        incumbent = direct
        is_largest = index == len(ladder) - 1
        if not direct["success"] and not numerical_failure_allows_fallback(direct):
            raise RuntimeError(
                f"direct GN failed for a non-numerical reason: {direct['convergence_reason']}"
            )
        if is_largest and numerical_failure_allows_fallback(direct):
            attempts.extend(
                refine_largest_same_bank_fallback(
                    refine_capture_reset_gauss_newton,
                    data,
                    direct,
                    satellites,
                    support,
                    likelihood,
                    warm_budget_s=warm_budget_s,
                    final_budget_s=final_budget_s,
                )
            )
            final = attempts[-1]
            if not final["success"] and not numerical_failure_allows_fallback(final):
                raise RuntimeError(
                    f"fallback GN failed for a non-numerical reason: {final['convergence_reason']}"
                )
            incumbent = (
                final
                if final["success"]
                else min((direct, final), key=lambda trial: trial["objective"])
            )
        for attempt in attempts:
            attempt.pop("satellite_weights", None)
        incumbent["identity_masses"] = masses
        incumbent["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(incumbent)
        bank_attempts.append(
            {
                "satellite_indices": np.asarray(satellites, dtype=int),
                "catalog_numbers": np.asarray(data.numbers)[satellites],
                "satellite_count": len(satellites),
                "fallback_triggered": len(attempts) > 1,
                "attempts": attempts,
                "incumbent_attempt_index": attempts.index(incumbent),
            }
        )
    return {
        "rough": rough,
        "initializer": initialized,
        "anchors": anchors,
        "full_bank": full_bank,
        "keep_track_identity": True,
        "optimizer": "capture-reset-fresh-gauss-newton",
        "shared_predictions": True,
        "cross_bank_seed": False,
        "largest_bank_fallback_policy": {
            "trigger": "allowed numerical failure only",
            "warm_sigma_hz": [2000.0, 1000.0, 500.0],
            "warm_budget_s_each": float(warm_budget_s),
            "final_sigma_hz": 200.0,
            "final_budget_s": float(final_budget_s),
        },
        "bank_attempts": bank_attempts,
        "trials": trials,
        **select_trials(trials),
        "elapsed_s": time.monotonic() - started,
        "scope": "Each frozen bank starts independently from the same sealed child rough/RX "
        "initializer. Only an allowed numerical failure on the largest bank triggers same-bank "
        "GN annealing. Priors and full-bank-derived identity masses remain fixed within every "
        "bank and its attempts. No reference coordinates or evaluation artifacts are read.",
    }


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_frozen_gn_pilot(
    root,
    unit_id,
    *,
    run_id="capture-reset-gn-v1",
    sealed_run_id="capture-reset-v1",
    budget_s_per_bank=20.0,
):
    """Run one sealed no-truth reset-GN pilot and persist provenance."""

    from joint_inputs import load_joint_data
    from rough_smoke import serializable

    root = Path(root).resolve()
    selection_path = root / "selection.json"
    selection = json.loads(selection_path.read_text())
    matches = [
        (dataset, unit)
        for dataset, population in selection["datasets"].items()
        for unit in population["units"]
        if unit["unit_id"] == unit_id
    ]
    if len(matches) != 1:
        raise ValueError("unit must appear exactly once in frozen selection")
    dataset, unit = matches[0]
    sealed_path = root / "runs" / sealed_run_id / unit_id / "fit.json"
    input_bindings = {
        "selection.json": _digest(selection_path),
        f"units/{unit_id}/bundle.json": _digest(root / "units" / unit_id / "bundle.json"),
        f"units/{unit_id}/bundle.npz": _digest(root / "units" / unit_id / "bundle.npz"),
        f"runs/{sealed_run_id}/{unit_id}/fit.json": _digest(sealed_path),
    }
    source_hashes = {
        path.name: _digest(path)
        for path in sorted(root.glob("*.py"))
        if not path.name.startswith("test_")
    }
    output = root / "runs" / run_id / unit_id
    output.mkdir(parents=True, exist_ok=False)
    attempt = {
        "schema": "multiscan-capture-reset-gn-attempt/v1",
        "unit_id": unit_id,
        "dataset": dataset,
        "run_id": run_id,
        "sealed_run_id": sealed_run_id,
        "created_utc_ns": time.time_ns(),
        "input_bindings": input_bindings,
        "source_hashes": source_hashes,
        "limits": {
            "budget_s_per_bank": float(budget_s_per_bank),
            "numerical_threads": 1,
        },
        "reference_truth_read": False,
        "evaluation_artifact_read": False,
    }
    (output / "attempt.json").write_text(json.dumps(attempt, indent=2) + "\n")
    started = time.monotonic()
    try:
        data = load_joint_data(root / "units" / unit_id)
        sealed_receipt = json.loads(sealed_path.read_text())
        fitted = fit_sealed_capture_reset_gn(
            data,
            sealed_receipt["fit"],
            budget_s_per_bank=budget_s_per_bank,
        )
    except Exception as error:
        failure = {
            "schema": "multiscan-capture-reset-gn-failure/v1",
            "unit_id": unit_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_s": time.monotonic() - started,
            "attempt_sha256": _digest(output / "attempt.json"),
            "reference_truth_read": False,
            "evaluation_artifact_read": False,
        }
        (output / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        raise
    receipt = {
        "schema": "multiscan-capture-reset-gn-fit/v1",
        "unit": unit,
        "dataset": dataset,
        "run_id": run_id,
        "stage": "capture_reset_gn",
        "attempt_sha256": _digest(output / "attempt.json"),
        "input_bindings": input_bindings,
        "source_hashes": source_hashes,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "reference_truth_read": False,
        "evaluation_artifact_read": False,
        "scope": "Frozen raw unit and sealed capture-reset fit only; no truth-based selection "
        "or evaluation read.",
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    return {
        "unit_id": unit_id,
        "fit_path": str(fit_path),
        "fit_sha256": _digest(fit_path),
        "elapsed_s": receipt["elapsed_s"],
        "success": bool(fitted["success"]),
        "selection_resolved": bool(fitted["selection_resolved"]),
        "trial_statuses": [trial["status"] for trial in fitted["trials"]],
    }


def run_fresh_gn_pilot(
    root,
    unit_id,
    *,
    run_id="capture-reset-fresh-v1",
    direct_budget_s=20.0,
    warm_budget_s=5.0,
    final_budget_s=20.0,
):
    """Run one fresh child-initialized reset-GN fit without evaluation access."""

    from joint_inputs import load_joint_data
    from rough_smoke import serializable

    root = Path(root).resolve()
    selection_path = root / "selection.json"
    selection = json.loads(selection_path.read_text())
    matches = [
        (dataset, unit)
        for dataset, population in selection["datasets"].items()
        for unit in population["units"]
        if unit["unit_id"] == unit_id
    ]
    if len(matches) != 1:
        raise ValueError("unit must appear exactly once in frozen selection")
    dataset, unit = matches[0]
    if unit["size"] < 2:
        raise ValueError("fresh capture-reset GN requires a multi-capture unit")
    single_units = {
        single["session_ids"][0]: single["unit_id"]
        for single in selection["datasets"][dataset]["units"]
        if single["size"] == 1
    }
    rough_path = root / "runs" / "rough-v1" / unit_id / "fit.json"
    input_bindings = {
        "selection.json": _digest(selection_path),
        f"units/{unit_id}/bundle.json": _digest(root / "units" / unit_id / "bundle.json"),
        f"units/{unit_id}/bundle.npz": _digest(root / "units" / unit_id / "bundle.npz"),
        f"runs/rough-v1/{unit_id}/fit.json": _digest(rough_path),
    }
    child_units = []
    child_fit_receipts = {}
    for session_id in unit["session_ids"]:
        child_unit = single_units.get(session_id)
        if child_unit is None:
            raise ValueError("each child capture must have a frozen single unit")
        child_path = root / "runs" / "coherent-v1" / child_unit / "fit.json"
        child_units.append(child_unit)
        child_fit_receipts[session_id] = json.loads(child_path.read_text())
        input_bindings[f"runs/coherent-v1/{child_unit}/fit.json"] = _digest(child_path)
    source_hashes = {
        path.name: _digest(path)
        for path in sorted(root.glob("*.py"))
        if not path.name.startswith("test_")
    }
    output = root / "runs" / run_id / unit_id
    output.mkdir(parents=True, exist_ok=False)
    attempt = {
        "schema": "multiscan-capture-reset-fresh-gn-attempt/v1",
        "unit_id": unit_id,
        "dataset": dataset,
        "run_id": run_id,
        "created_utc_ns": time.time_ns(),
        "child_units": child_units,
        "input_bindings": input_bindings,
        "source_hashes": source_hashes,
        "limits": {
            "direct_budget_s_per_bank": float(direct_budget_s),
            "largest_warm_sigma_hz": [2000.0, 1000.0, 500.0],
            "largest_warm_budget_s_each": float(warm_budget_s),
            "largest_final_budget_s": float(final_budget_s),
            "numerical_threads": 1,
        },
        "fallback_trigger": "largest-bank allowed numerical failure only",
        "cross_bank_seed": False,
        "reference_truth_read": False,
        "evaluation_artifact_read": False,
    }
    (output / "attempt.json").write_text(json.dumps(attempt, indent=2) + "\n")
    started = time.monotonic()
    try:
        data = load_joint_data(root / "units" / unit_id)
        rough_receipt = json.loads(rough_path.read_text())
        fitted = fit_fresh_capture_reset_gn(
            data,
            rough_receipt["fit"],
            child_fit_receipts,
            direct_budget_s=direct_budget_s,
            warm_budget_s=warm_budget_s,
            final_budget_s=final_budget_s,
        )
    except Exception as error:
        failure = {
            "schema": "multiscan-capture-reset-fresh-gn-failure/v1",
            "unit_id": unit_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_s": time.monotonic() - started,
            "attempt_sha256": _digest(output / "attempt.json"),
            "reference_truth_read": False,
            "evaluation_artifact_read": False,
        }
        (output / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        raise
    receipt = {
        "schema": "multiscan-capture-reset-fresh-gn-fit/v1",
        "unit": unit,
        "dataset": dataset,
        "run_id": run_id,
        "stage": "capture_reset_fresh_gn",
        "attempt_sha256": _digest(output / "attempt.json"),
        "input_bindings": input_bindings,
        "source_hashes": source_hashes,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "reference_truth_read": False,
        "evaluation_artifact_read": False,
        "scope": "Frozen raw unit, sealed joint rough fit, and sealed child coherent fits only. "
        "No truth-based selection and no evaluation artifact read.",
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    return {
        "unit_id": unit_id,
        "fit_path": str(fit_path),
        "fit_sha256": _digest(fit_path),
        "elapsed_s": receipt["elapsed_s"],
        "success": bool(fitted["success"]),
        "selection_resolved": bool(fitted["selection_resolved"]),
        "trial_statuses": [trial["status"] for trial in fitted["trials"]],
        "largest_fallback_triggered": bool(fitted["bank_attempts"][-1]["fallback_triggered"]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--run-id", default="capture-reset-gn-v1")
    parser.add_argument("--sealed-run-id", default="capture-reset-v1")
    parser.add_argument("--budget-s-per-bank", type=float, default=20.0)
    parser.add_argument("--fresh-child-initializer", action="store_true")
    parser.add_argument("--warm-budget-s", type=float, default=5.0)
    parser.add_argument("--final-budget-s", type=float, default=20.0)
    args = parser.parse_args()
    if args.fresh_child_initializer:
        result = run_fresh_gn_pilot(
            args.root,
            args.unit_id,
            run_id=args.run_id,
            direct_budget_s=args.budget_s_per_bank,
            warm_budget_s=args.warm_budget_s,
            final_budget_s=args.final_budget_s,
        )
    else:
        result = run_frozen_gn_pilot(
            args.root,
            args.unit_id,
            run_id=args.run_id,
            sealed_run_id=args.sealed_run_id,
            budget_s_per_bank=args.budget_s_per_bank,
        )
    print(json.dumps(result))


__all__ = [
    "apply_capture_offsets",
    "capture_indicator_fisher_terms",
    "fit_fresh_capture_reset_gn",
    "fit_sealed_capture_reset_gn",
    "independent_fresh_bank_starts",
    "numerical_failure_allows_fallback",
    "refine_capture_reset_gauss_newton",
    "refine_largest_same_bank_fallback",
    "run_fresh_gn_pilot",
    "run_frozen_gn_pilot",
]


if __name__ == "__main__":
    main()
