"""Prototype coherent fit with capture-specific receiver intercept resets."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood, anchor_partition, frozen_identity_masses
from grouped_likelihood import DEFAULT_ALIAS_HZ
from prediction_jacobian import paired_prediction_jacobian
from staged_fit import candidate_ladder, frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


def canonicalize_capture_jumps(jumps, alias_hz=DEFAULT_ALIAS_HZ):
    """Return one alias-fundamental representative with capture zero as gauge."""

    jumps = np.asarray(jumps, dtype=float)
    if jumps.ndim != 2 or jumps.shape[1] != 2 or np.any(~np.isfinite(jumps)):
        raise ValueError("capture jumps must be a finite capture-by-two array")
    half = float(alias_hz) / 2
    canonical = (jumps + half) % float(alias_hz) - half
    canonical[0] = 0.0
    return canonical


def _validate_capture_data(data):
    capture_index = np.asarray(data.capture_index, dtype=int)
    capture_count = len(data.child_sessions)
    if capture_count < 2:
        raise ValueError("capture-reset fitting requires at least two captures")
    if capture_index.shape != np.asarray(data.times).shape:
        raise ValueError("capture_index must align with observation times")
    if np.any(capture_index < 0) or np.any(capture_index >= capture_count):
        raise ValueError("capture_index falls outside child_sessions")
    if np.asarray(data.child_origins_utc_ns).shape != (capture_count,):
        raise ValueError("child origins must align with child_sessions")
    return capture_count


def _child_initial(receipt, session_id):
    unit = receipt.get("unit", {})
    sessions = tuple(unit.get("session_ids", ()))
    if unit.get("size") != 1 or sessions != (session_id,):
        raise ValueError("child fit receipt does not match the requested single capture")
    fitted = receipt.get("fit", {})
    parameters = np.asarray(fitted.get("rx_initial"), dtype=float)
    rough_position = np.asarray(fitted.get("rough", {}).get("position_km"), dtype=float)
    if parameters.ndim != 1 or len(parameters) < 6 or np.any(~np.isfinite(parameters)):
        raise ValueError("child fit lacks a finite receiver-line initialization")
    if rough_position.shape != (2,) or np.any(~np.isfinite(rough_position)):
        raise ValueError("child fit lacks a finite rough position")
    return parameters, rough_position


def initialize_from_child_fits(data, child_fit_receipts, *, child_reference_time_s=150.0):
    """Transform sealed child rough/RX initializers into the joint unit clock."""

    capture_count = _validate_capture_data(data)
    if set(child_fit_receipts) != set(data.child_sessions):
        raise ValueError("child fit receipts must exactly match child_sessions")
    child_parameters = []
    rough_positions = []
    for session_id in data.child_sessions:
        parameters, rough_position = _child_initial(child_fit_receipts[session_id], session_id)
        child_parameters.append(parameters)
        rough_positions.append(rough_position)
    child_parameters = np.asarray(child_parameters)
    rough_positions = np.asarray(rough_positions)
    reference_time = float(getattr(data, "reference_time_s", 150.0))
    child_reference_times = (
        (np.asarray(data.child_origins_utc_ns, dtype=np.int64) - int(data.origin_utc_ns)) / 1e9
        + float(child_reference_time_s)
    )
    parameters = np.zeros(6 + len(data.numbers), dtype=float)
    parameters[:2] = np.median(rough_positions, axis=0)
    jumps = np.zeros((capture_count, 2), dtype=float)
    for receiver in (0, 1):
        slope_column = 3 + 2 * receiver
        intercept_column = 2 + 2 * receiver
        slope = float(np.median(child_parameters[:, slope_column]))
        intercept = float(
            child_parameters[0, intercept_column]
            - slope * (child_reference_times[0] - reference_time)
        )
        parameters[intercept_column] = intercept
        parameters[slope_column] = slope
        baseline = intercept + slope * (child_reference_times - reference_time)
        jumps[:, receiver] = child_parameters[:, intercept_column] - baseline
    jumps = canonicalize_capture_jumps(jumps)
    return {
        "parameters": parameters,
        "capture_jumps_hz": jumps,
        "child_reference_times_in_unit_s": child_reference_times,
        "child_rough_positions_km": rough_positions,
        "child_receiver_initials": child_parameters[:, :6],
        "position_policy": "coordinate-wise median of sealed child rough positions",
        "slope_policy": "per-receiver median of sealed child RX-line slopes",
        "gauge": "capture index zero has both RX jumps fixed to zero",
        "jump_domain": "alias fundamental interval [-alias/2, alias/2)",
    }


def capture_reset_offsets(data, capture_jumps_hz, rows):
    """Return additive prediction offsets for paired observation rows."""

    capture_count = _validate_capture_data(data)
    jumps = np.asarray(capture_jumps_hz, dtype=float)
    rows = np.asarray(rows, dtype=int)
    if jumps.shape != (capture_count, 2) or np.any(~np.isfinite(jumps)):
        raise ValueError("capture jumps do not match the data captures and receivers")
    if not np.array_equal(jumps[0], np.zeros(2)):
        raise ValueError("capture zero must define the zero-jump gauge")
    if np.any(rows < 0) or np.any(rows >= len(data.times)):
        raise ValueError("rows fall outside observations")
    capture = np.asarray(data.capture_index, dtype=int)[rows]
    receiver = np.asarray(data.receiver, dtype=int)[rows]
    return jumps[capture, receiver]


def paired_capture_reset_prediction(data, parameters, capture_jumps_hz, rows, satellites):
    """Return paired predictions with capture resets and the base sparse Jacobian."""

    prediction, visible, jacobian = paired_prediction_jacobian(
        data, parameters, rows, satellites
    )
    return prediction + capture_reset_offsets(data, capture_jumps_hz, rows), visible, jacobian


def capture_reset_gradient(data, rows, prediction_gradient):
    """Transpose-multiply the capture/RX indicator Jacobian."""

    capture_count = _validate_capture_data(data)
    rows = np.asarray(rows, dtype=int)
    prediction_gradient = np.asarray(prediction_gradient, dtype=float)
    if rows.shape != prediction_gradient.shape:
        raise ValueError("prediction gradient must match paired rows")
    capture = np.asarray(data.capture_index, dtype=int)[rows]
    receiver = np.asarray(data.receiver, dtype=int)[rows]
    indices = 2 * capture + receiver
    return np.bincount(
        indices.ravel(),
        weights=prediction_gradient.ravel(),
        minlength=2 * capture_count,
    ).reshape(capture_count, 2)


def capture_reset_model_penalty(group_count, satellite_count, capture_count):
    """Return the BIC-style penalty including two reset parameters per later capture."""

    if group_count <= 0 or satellite_count <= 0 or capture_count < 1:
        raise ValueError("penalty counts must be positive")
    extra_parameter_count = 2 * (capture_count - 1)
    baseline = 0.5 * satellite_count * np.log(group_count)
    extra = 0.5 * extra_parameter_count * np.log(group_count)
    return {
        "baseline_penalty": float(baseline),
        "extra_parameter_count": extra_parameter_count,
        "extra_capture_reset_penalty": float(extra),
        "total_penalty": float(baseline + extra),
    }


def refine_capture_reset_bank(
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
    budget_s=45.0,
):
    """Refine one frozen candidate bank with shared slopes and capture RX resets."""

    from scipy.optimize import minimize

    capture_count = _validate_capture_data(data)
    satellites = np.asarray(satellites, dtype=int)
    support = np.asarray(support, dtype=float)
    initial_parameters = np.asarray(initial_parameters, dtype=float)
    initial_jumps_hz = canonicalize_capture_jumps(initial_jumps_hz)
    active = np.r_[np.arange(6), 6 + satellites]
    parameter_scales = np.r_[20, 20, 1000, 10, 1000, 10, np.ones(len(satellites))]
    jump_scales = np.full(2 * (capture_count - 1), 1000.0)
    weights = support / np.sum(support)
    rows = np.repeat(np.arange(len(data.times)), len(satellites))
    paired_satellites = np.tile(satellites, len(data.times))
    base_bounds = [
        (-10, 10),
        (-10, 10),
        (None, None),
        (-slope_bound_hz_s / 10, slope_bound_hz_s / 10),
        (None, None),
        (-slope_bound_hz_s / 10, slope_bound_hz_s / 10),
    ]
    base_bounds += [(-tau_bound_s, tau_bound_s)] * len(satellites)
    half_alias_khz = DEFAULT_ALIAS_HZ / 2000
    bounds = base_bounds + [(-half_alias_khz, half_alias_khz)] * len(jump_scales)
    initial_vector = np.concatenate(
        (
            initial_parameters[active] / parameter_scales,
            initial_jumps_hz[1:].ravel() / jump_scales,
        )
    )
    best = [float("inf"), initial_vector.copy()]
    deadline = time.monotonic() + float(budget_s)
    evaluations = 0

    def evaluate(vector, check_time=True):
        nonlocal evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("Capture-reset refinement budget exhausted")
        parameters = initial_parameters.copy()
        split = len(active)
        parameters[active] = vector[:split] * parameter_scales
        jumps = np.zeros((capture_count, 2), dtype=float)
        jumps[1:] = (vector[split:] * jump_scales).reshape(capture_count - 1, 2)
        predicted, visible, jacobian = paired_capture_reset_prediction(
            data, parameters, jumps, rows, paired_satellites
        )
        evaluations += 1
        result = prepared.evaluate(
            predicted.reshape(-1, len(satellites)),
            visible.reshape(-1, len(satellites)),
            sigma_hz=sigma_hz,
            satellite_weights=weights,
            background_mass=0.2,
            return_gradient=True,
        )
        prediction_gradient = result.pop("prediction_gradient")
        prior = 0.5 * np.sum((parameters[6 + satellites] / tau_sigma_s) ** 2)
        value = -result["total_log_likelihood"] + prior
        parameter_gradient = -jacobian.transpose_multiply(prediction_gradient.ravel())
        parameter_gradient[6 + satellites] += (
            parameters[6 + satellites] / tau_sigma_s**2
        )
        jump_gradient = -capture_reset_gradient(
            data, rows, prediction_gradient.ravel()
        )[1:].ravel()
        gradient = np.concatenate(
            (
                parameter_gradient[active] * parameter_scales,
                jump_gradient * jump_scales,
            )
        )
        if value < best[0]:
            best[:] = [float(value), vector.copy()]
        return float(value), result, parameters, jumps, gradient

    def objective_and_gradient(vector):
        value, _, _, _, gradient = evaluate(vector)
        return value, gradient

    started = time.monotonic()
    try:
        fitted = minimize(
            objective_and_gradient,
            initial_vector,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 500, "maxfun": 1000, "ftol": 1e-9},
        )
        vector = fitted.x
        success = bool(fitted.success)
        message = str(fitted.message)
        iterations = int(fitted.nit)
    except TimeoutError as error:
        vector = best[1]
        success = False
        message = str(error)
        iterations = None
    objective, likelihood, parameters, jumps, gradient = evaluate(vector, check_time=False)
    jumps = canonicalize_capture_jumps(jumps)
    projected_gradient = gradient.copy()
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None and vector[index] <= lower and gradient[index] > 0:
            projected_gradient[index] = 0
        if upper is not None and vector[index] >= upper and gradient[index] < 0:
            projected_gradient[index] = 0
    penalty = capture_reset_model_penalty(
        len(likelihood["group_values"]), len(satellites), capture_count
    )
    return {
        "parameters": parameters,
        "capture_jumps_hz": jumps,
        "success": success,
        "message": message,
        "status": "converged" if success else "nonconverged",
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": objective,
        "selection_score": objective + penalty["total_penalty"],
        "model_penalty": penalty,
        "satellite_weights": weights,
        "satellite_support": likelihood["satellite_support"],
        "null_support": likelihood["null_support"],
        "groups": len(likelihood["group_values"]),
        "tau_sigma_s": tau_sigma_s,
        "tau_bound_s": tau_bound_s,
        "slope_bound_hz_s": slope_bound_hz_s,
        "jump_bound_hz": DEFAULT_ALIAS_HZ / 2,
        "elapsed_s": time.monotonic() - started,
        "evaluations": evaluations,
        "iterations": iterations,
        "projected_gradient_inf_norm": float(np.max(np.abs(projected_gradient))),
        "gradient_method": "Analytic orbit/RX gradient plus capture/RX indicator gradient",
    }


def fit_capture_reset(
    data,
    rough,
    child_fit_receipts,
    *,
    total_budget_s=165.0,
    per_bank_budget_s=50.0,
):
    """Fit every frozen coherent candidate bank with capture intercept resets."""

    capture_count = _validate_capture_data(data)
    initialized = initialize_from_child_fits(data, child_fit_receipts)
    anchors = anchor_partition(data, max_anchors=12 * capture_count)
    ladder = candidate_ladder(
        rough["assignments"],
        sizes=tuple(size * capture_count for size in (4, 8, 12)),
    )
    full_bank = ladder[-1][0]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in anchors],
    )
    trials = []
    started = time.monotonic()
    deadline = started + float(total_budget_s)
    for satellites, support in ladder:
        remaining = max(1.0, deadline - time.monotonic())
        masses = frozen_identity_masses(anchors, full_bank, satellites)
        likelihood = FixedBankLikelihood(prepared, masses)
        trial = refine_capture_reset_bank(
            data,
            initialized["parameters"],
            initialized["capture_jumps_hz"],
            satellites,
            support,
            likelihood,
            budget_s=min(float(per_bank_budget_s), remaining),
        )
        trial.pop("satellite_weights")
        trial["identity_masses"] = masses
        trial["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(trial)
    return {
        "rough": rough,
        "initializer": initialized,
        "anchors": anchors,
        "full_bank": full_bank,
        "keep_track_identity": True,
        "trials": trials,
        **select_trials(trials),
        "elapsed_s": time.monotonic() - started,
        "scope": "Whole-track coherent proxy with common position, common per-RX slopes, "
        "global satellite timing shifts, and two free RX intercept resets per capture after "
        "the zero-gauge first capture. Resets are alias-bounded without a calibrated prior. "
        "The model penalty adds two parameters per later capture. No reference coordinates "
        "are accepted or read.",
    }


def compare_continuous_baseline(reset_fit, continuous_fit):
    """Compare reset trials with a sealed forced-continuous fit on matching banks."""

    if "fit" in continuous_fit:
        continuous_fit = continuous_fit["fit"]
    baseline_by_bank = {
        tuple(int(value) for value in trial["catalog_numbers"]): trial
        for trial in continuous_fit["trials"]
    }
    comparisons = []
    for trial in reset_fit["trials"]:
        bank = tuple(int(value) for value in trial["catalog_numbers"])
        baseline = baseline_by_bank.get(bank)
        row = {"catalog_numbers": bank, "satellite_count": len(bank)}
        if baseline is None:
            row["status"] = "no_matching_continuous_bank"
        else:
            row.update(
                status="matched",
                continuous_objective=float(baseline["objective"]),
                reset_objective=float(trial["objective"]),
                objective_delta_reset_minus_continuous=float(
                    trial["objective"] - baseline["objective"]
                ),
                continuous_selection_score=float(baseline["selection_score"]),
                reset_selection_score=float(trial["selection_score"]),
                selection_delta_reset_minus_continuous=float(
                    trial["selection_score"] - baseline["selection_score"]
                ),
                extra_capture_reset_penalty=float(
                    trial["model_penalty"]["extra_capture_reset_penalty"]
                ),
            )
        comparisons.append(row)
    return comparisons


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_frozen_pilot(
    root,
    unit_id,
    *,
    run_id="capture-reset-v1",
    total_budget_s=165.0,
    per_bank_budget_s=50.0,
):
    """Run one sealed frozen-input pilot without loading any evaluation artifact."""

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
        raise ValueError("capture-reset pilot requires a multi-capture unit")
    single_units = {
        single["session_ids"][0]: single["unit_id"]
        for single in selection["datasets"][dataset]["units"]
        if single["size"] == 1
    }
    child_units = []
    child_fit_receipts = {}
    input_bindings = {
        "selection.json": _digest(selection_path),
        f"units/{unit_id}/bundle.json": _digest(root / "units" / unit_id / "bundle.json"),
        f"units/{unit_id}/bundle.npz": _digest(root / "units" / unit_id / "bundle.npz"),
        f"runs/rough-v1/{unit_id}/fit.json": _digest(
            root / "runs" / "rough-v1" / unit_id / "fit.json"
        ),
        f"runs/coherent-v1/{unit_id}/fit.json": _digest(
            root / "runs" / "coherent-v1" / unit_id / "fit.json"
        ),
    }
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
        "schema": "multiscan-capture-reset-attempt/v1",
        "unit_id": unit_id,
        "dataset": dataset,
        "run_id": run_id,
        "created_utc_ns": time.time_ns(),
        "child_units": child_units,
        "input_bindings": input_bindings,
        "source_hashes": source_hashes,
        "limits": {
            "total_budget_s": float(total_budget_s),
            "per_bank_budget_s": float(per_bank_budget_s),
            "numerical_threads": 1,
        },
        "reference_truth_read": False,
        "evaluation_artifact_read": False,
    }
    (output / "attempt.json").write_text(json.dumps(attempt, indent=2) + "\n")
    started = time.monotonic()
    try:
        data = load_joint_data(root / "units" / unit_id)
        rough_receipt = json.loads(
            (root / "runs" / "rough-v1" / unit_id / "fit.json").read_text()
        )
        baseline_receipt = json.loads(
            (root / "runs" / "coherent-v1" / unit_id / "fit.json").read_text()
        )
        fitted = fit_capture_reset(
            data,
            rough_receipt["fit"],
            child_fit_receipts,
            total_budget_s=total_budget_s,
            per_bank_budget_s=per_bank_budget_s,
        )
        comparison = compare_continuous_baseline(fitted, baseline_receipt)
    except Exception as error:
        failure = {
            "schema": "multiscan-capture-reset-failure/v1",
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
        "schema": "multiscan-capture-reset-fit/v1",
        "unit": unit,
        "dataset": dataset,
        "run_id": run_id,
        "stage": "capture_reset",
        "attempt_sha256": _digest(output / "attempt.json"),
        "input_bindings": input_bindings,
        "source_hashes": source_hashes,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "continuous_baseline_comparison": comparison,
        "reference_truth_read": False,
        "evaluation_artifact_read": False,
        "scope": "Frozen raw inputs and sealed child/joint fit initializers only; no truth-based "
        "selection or evaluation read.",
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--run-id", default="capture-reset-v1")
    parser.add_argument("--total-budget-s", type=float, default=165.0)
    parser.add_argument("--per-bank-budget-s", type=float, default=50.0)
    args = parser.parse_args()
    print(
        json.dumps(
            run_frozen_pilot(
                args.root,
                args.unit_id,
                run_id=args.run_id,
                total_budget_s=args.total_budget_s,
                per_bank_budget_s=args.per_bank_budget_s,
            )
        )
    )


__all__ = [
    "canonicalize_capture_jumps",
    "capture_reset_gradient",
    "capture_reset_model_penalty",
    "capture_reset_offsets",
    "compare_continuous_baseline",
    "fit_capture_reset",
    "initialize_from_child_fits",
    "paired_capture_reset_prediction",
    "refine_capture_reset_bank",
    "run_frozen_pilot",
]


if __name__ == "__main__":
    main()
