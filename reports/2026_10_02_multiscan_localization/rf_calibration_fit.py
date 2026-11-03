"""Opt-in receiver RF-calibration prototype with frozen scientific inputs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood, frozen_identity_masses
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from profile_seed import _validate_source_provenance
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import candidate_ladder, frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


COEFFICIENT_PRIOR_SIGMA_HZ_GHZ = 250.0
COEFFICIENT_BOUND_HZ_GHZ = 1000.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receiver_rf_centers(data):
    centers = np.empty(2)
    receiver = np.asarray(data.receiver)
    rf = np.asarray(data.rf, dtype=float)
    for index in (0, 1):
        values = rf[receiver == index]
        if len(values) == 0 or np.any(~np.isfinite(values)):
            raise ValueError(f"RX{index} has no finite RF observations")
        centers[index] = 0.5 * (np.min(values) + np.max(values))
    return centers


def receiver_rf_design(data, centers):
    centers = np.asarray(centers, dtype=float)
    if centers.shape != (2,) or np.any(~np.isfinite(centers)):
        raise ValueError("centers must contain one finite value per receiver")
    receiver = np.asarray(data.receiver, dtype=int)
    if np.any((receiver < 0) | (receiver > 1)):
        raise ValueError("receiver values must be zero or one")
    design = np.zeros((len(receiver), 2))
    design[np.arange(len(receiver)), receiver] = (
        np.asarray(data.rf, dtype=float) - centers[receiver]
    ) / 1e9
    return design


def rf_correction_hz(design, coefficients_hz_ghz):
    design = np.asarray(design, dtype=float)
    coefficients = np.asarray(coefficients_hz_ghz, dtype=float)
    if design.ndim != 2 or design.shape[1] != 2 or coefficients.shape != (2,):
        raise ValueError("RF design and coefficients have incompatible shapes")
    return design @ coefficients


def _coefficient_value_gradient(
    base_prediction,
    visible,
    design,
    coefficients,
    prepared,
    masses,
    *,
    prior_sigma=COEFFICIENT_PRIOR_SIGMA_HZ_GHZ,
):
    correction = rf_correction_hz(design, coefficients)
    predicted = np.asarray(base_prediction) + correction[:, None]
    result = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=200.0,
        **masses,
        track_contamination=0.2,
        return_gradient=True,
    )
    prediction_gradient = result["prediction_gradient"]
    row_gradient = np.sum(prediction_gradient, axis=1)
    gradient = -(design.T @ row_gradient) + coefficients / prior_sigma**2
    prior = 0.5 * float(np.sum((coefficients / prior_sigma) ** 2))
    value = float(-result["total_log_likelihood"] + prior)
    return value, gradient, result, prior


def fit_coefficients(
    base_prediction,
    visible,
    design,
    initial,
    prepared,
    masses,
    *,
    budget_s,
):
    from scipy.optimize import minimize

    if not np.isfinite(budget_s) or budget_s <= 0:
        raise ValueError("coefficient budget must be positive and finite")
    initial = np.asarray(initial, dtype=float)
    if initial.shape != (2,) or np.any(~np.isfinite(initial)):
        raise ValueError("initial coefficients must be two finite values")
    deadline = time.monotonic() + float(budget_s)
    evaluations = 0
    best = [float("inf"), np.clip(initial, -COEFFICIENT_BOUND_HZ_GHZ, COEFFICIENT_BOUND_HZ_GHZ)]

    def objective(vector, check_time=True):
        nonlocal evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("RF coefficient budget exhausted")
        evaluations += 1
        value, gradient, _, _ = _coefficient_value_gradient(
            base_prediction, visible, design, vector, prepared, masses
        )
        if value < best[0]:
            best[:] = [value, np.asarray(vector).copy()]
        return value, gradient

    success = False
    message = ""
    iterations = None
    try:
        fitted = minimize(
            objective,
            best[1],
            method="L-BFGS-B",
            jac=True,
            bounds=[(-COEFFICIENT_BOUND_HZ_GHZ, COEFFICIENT_BOUND_HZ_GHZ)] * 2,
            options={"maxiter": 100, "maxfun": 200, "ftol": 1e-12, "gtol": 1e-7},
        )
        success = bool(fitted.success)
        message = str(fitted.message)
        iterations = int(fitted.nit)
    except TimeoutError as error:
        message = str(error)
    coefficients = best[1]
    value, gradient, result, prior = _coefficient_value_gradient(
        base_prediction, visible, design, coefficients, prepared, masses
    )
    projected = gradient.copy()
    for index in range(2):
        if coefficients[index] <= -COEFFICIENT_BOUND_HZ_GHZ and gradient[index] > 0:
            projected[index] = 0.0
        if coefficients[index] >= COEFFICIENT_BOUND_HZ_GHZ and gradient[index] < 0:
            projected[index] = 0.0
    return {
        "coefficients_hz_ghz": coefficients,
        "success": success,
        "status": "converged" if success else "nonconverged",
        "message": message,
        "objective_without_tau_prior": value,
        "coefficient_prior": prior,
        "projected_gradient_inf_norm": float(np.max(np.abs(projected))),
        "evaluations": evaluations,
        "iterations": iterations,
        "likelihood": result,
    }


def _seed_for_bank(seed_fit, satellites):
    if seed_fit.get("trials"):
        matches = [
            trial
            for trial in seed_fit["trials"]
            if np.array_equal(np.asarray(trial["satellite_indices"]), satellites)
        ]
        if len(matches) == 1:
            return np.asarray(matches[0]["parameters"], dtype=float).copy()
    if "selected" in seed_fit:
        selected = seed_fit["selected"]["fit"]
    else:
        selected = seed_fit["score_leader"]
    parameters = np.asarray(selected["parameters"], dtype=float).copy()
    parameters[6:] = 0.0
    parameters[6 + satellites] = np.asarray(selected["parameters"])[6 + satellites]
    return parameters


def _adjusted_data(data, correction):
    adjusted = copy.copy(data)
    adjusted.measured = np.asarray(data.measured) - correction
    return adjusted


def _evaluate_combined(data, prepared, masses, satellites, parameters, design, coefficients):
    plan = SharedPredictionPlan(data, satellites)
    predicted, visible, _ = plan.predict(parameters)
    predicted = predicted.reshape(len(data.times), len(satellites))
    visible = visible.reshape(predicted.shape)
    coefficient_value, _, result, coefficient_prior = _coefficient_value_gradient(
        predicted, visible, design, coefficients, prepared, masses
    )
    tau = parameters[6 + satellites]
    tau_prior = 0.5 * float(np.sum(tau**2))
    return {
        "objective": float(coefficient_value + tau_prior),
        "total_log_likelihood": float(result["total_log_likelihood"]),
        "tau_prior": tau_prior,
        "coefficient_prior": coefficient_prior,
        "satellite_support": result["satellite_support"],
        "null_support": float(result["null_support"]),
        "track_unknown_responsibility": result["track_unknown_responsibility"],
    }


def fit_rf_calibration(
    data,
    proposal,
    seed,
    *,
    case_budget_s=90.0,
    max_cycles=6,
):
    """Fit frozen banks with two receiver RF coefficients by block alternation."""

    if not np.isfinite(case_budget_s) or not 0 < case_budget_s <= 90:
        raise ValueError("case_budget_s must lie in (0, 90]")
    if not isinstance(max_cycles, (int, np.integer)) or not 1 <= max_cycles <= 6:
        raise ValueError("max_cycles must lie in [1, 6]")
    proposal_fit = proposal["fit"] if "fit" in proposal else proposal
    seed_fit = seed["fit"] if "fit" in seed else seed
    capture_count = len(getattr(data, "child_sessions", [getattr(data, "session_id", None)]))
    ladder = candidate_ladder(
        proposal_fit["rough"]["assignments"],
        sizes=tuple(size * capture_count for size in (4, 8, 12)),
    )
    full_bank = ladder[-1][0]
    if not np.array_equal(np.asarray(proposal_fit["full_bank"]), full_bank):
        raise ValueError("proposal full bank differs from its frozen rough ladder")
    anchors = proposal_fit["anchors"]
    centers = receiver_rf_centers(data)
    design = receiver_rf_design(data, centers)
    row_weights = frozen_row_weights(data)
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=row_weights,
        anchors=[anchor["groups"] for anchor in anchors],
    )
    started = time.monotonic()
    deadline = started + float(case_budget_s)
    trials = []
    for satellites, support in ladder:
        branch_started = time.monotonic()
        masses = frozen_identity_masses(anchors, full_bank, satellites)
        sealed_mass_trials = [
            trial
            for trial in proposal_fit.get("trials", [])
            if np.array_equal(np.asarray(trial["satellite_indices"]), satellites)
        ]
        if len(sealed_mass_trials) != 1:
            raise ValueError("proposal does not contain one matching frozen-mass trial")
        sealed_masses = sealed_mass_trials[0]["identity_masses"]
        if set(masses) != set(sealed_masses):
            raise ValueError("regenerated mass fields differ from the sealed proposal")
        for key, value in masses.items():
            if not np.array_equal(np.asarray(value), np.asarray(sealed_masses[key])):
                raise ValueError(f"regenerated {key} differs from the sealed proposal")
        parameters = _seed_for_bank(seed_fit, satellites)
        coefficients = np.zeros(2)
        best = None
        cycles = []
        for cycle_index in range(max_cycles):
            remaining = deadline - time.monotonic()
            remaining_blocks = (len(ladder) - len(trials)) * (max_cycles - cycle_index)
            if remaining <= 0.25:
                break
            correction = rf_correction_hz(design, coefficients)
            adjusted_data = _adjusted_data(data, correction)
            adjusted_prepared = prepare_track_grouped_likelihood(
                adjusted_data.measured,
                adjusted_data.group,
                row_weights=row_weights,
                anchors=[anchor["groups"] for anchor in anchors],
            )
            gn_budget = min(6.0, max(0.25, remaining / max(1, remaining_blocks)))
            gn = refine_gauss_newton(
                adjusted_data,
                parameters,
                satellites,
                support,
                FixedBankLikelihood(adjusted_prepared, masses),
                sigma_hz=200.0,
                budget_s=gn_budget,
            )
            parameters = np.asarray(gn["parameters"], dtype=float).copy()
            plan = SharedPredictionPlan(data, satellites)
            base_prediction, visible, _ = plan.predict(parameters)
            base_prediction = base_prediction.reshape(len(data.times), len(satellites))
            visible = visible.reshape(base_prediction.shape)
            coefficient_budget = min(2.0, max(0.25, deadline - time.monotonic()))
            coefficient_fit = fit_coefficients(
                base_prediction,
                visible,
                design,
                coefficients,
                prepared,
                masses,
                budget_s=coefficient_budget,
            )
            previous_coefficients = coefficients.copy()
            coefficients = coefficient_fit["coefficients_hz_ghz"].copy()
            combined = _evaluate_combined(
                data, prepared, masses, satellites, parameters, design, coefficients
            )
            cycle = {
                "cycle": cycle_index,
                "objective": combined["objective"],
                "gn_success": gn["success"],
                "gn_status": gn["status"],
                "gn_reason": gn["convergence_reason"],
                "gn_objective": gn["objective"],
                "gn_evaluations": gn["evaluations"],
                "gn_iterations": gn["iterations"],
                "gn_damping": gn["damping"],
                "coefficient_success": coefficient_fit["success"],
                "coefficient_status": coefficient_fit["status"],
                "coefficient_message": coefficient_fit["message"],
                "coefficient_projected_gradient_inf_norm": coefficient_fit[
                    "projected_gradient_inf_norm"
                ],
                "coefficient_evaluations": coefficient_fit["evaluations"],
                "coefficient_iterations": coefficient_fit["iterations"],
                "coefficients_hz_ghz": coefficients.copy(),
                "coefficient_step_inf_norm": float(
                    np.max(np.abs(coefficients - previous_coefficients))
                ),
            }
            cycles.append(cycle)
            state = (combined["objective"], parameters.copy(), coefficients.copy(), combined, gn)
            if best is None or state[0] < best[0]:
                best = state
        if best is None:
            raise TimeoutError("case budget exhausted before a bank produced a finite state")
        objective, parameters, coefficients, combined, gn = best
        groups = len(prepared.group_values)
        entry_penalty = 0.5 * len(satellites) * np.log(groups)
        coefficient_dof_penalty = np.log(groups)
        alternation_converged = bool(
            cycles
            and cycles[-1]["gn_success"]
            and cycles[-1]["coefficient_success"]
            and cycles[-1]["coefficient_step_inf_norm"] <= 1e-3
        )
        trials.append(
            {
                "parameters": parameters,
                "coefficients_hz_ghz": coefficients,
                "coefficients_ppm": coefficients * 0.001,
                "success": alternation_converged,
                "status": "converged" if alternation_converged else "nonconverged",
                "message": "block_coordinate_converged"
                if alternation_converged
                else "block_coordinate_limit",
                "convergence_reason": "block_coordinate_converged"
                if alternation_converged
                else "block_coordinate_limit",
                "satellite_indices": satellites,
                "catalog_numbers": np.asarray(data.numbers)[satellites],
                "satellite_count": len(satellites),
                "objective": objective,
                "selection_score": objective + entry_penalty + coefficient_dof_penalty,
                "entry_penalty": float(entry_penalty),
                "coefficient_dof_penalty": float(coefficient_dof_penalty),
                "coefficient_prior": combined["coefficient_prior"],
                "tau_prior": combined["tau_prior"],
                "total_log_likelihood": combined["total_log_likelihood"],
                "satellite_support": combined["satellite_support"],
                "null_support": combined["null_support"],
                "groups": groups,
                "identity_masses": masses,
                "cycles": cycles,
                "elapsed_s": time.monotonic() - branch_started,
            }
        )
    return {
        "rough": proposal_fit["rough"],
        "anchors": anchors,
        "full_bank": full_bank,
        "rf_centers_hz": centers,
        "coefficient_prior_sigma_hz_ghz": COEFFICIENT_PRIOR_SIGMA_HZ_GHZ,
        "coefficient_bound_hz_ghz": COEFFICIENT_BOUND_HZ_GHZ,
        "coefficient_count": 2,
        "trials": trials,
        **select_trials(trials),
        "scope": (
            "Opt-in RF-calibration hypothesis test. Candidate banks, anchors, masses, rows, and "
            "sealed nuisance starts are frozen. Two centered receiver RF coefficients are fit "
            "without reference coordinates; posterior channel residuals motivate but do not "
            "independently validate the model."
        ),
    }


def run_case(proposal_path, seed_path, run_id, case_budget_s):
    proposal_path = Path(proposal_path)
    seed_path = Path(seed_path)
    proposal = json.loads(proposal_path.read_text())
    seed = json.loads(seed_path.read_text())
    if proposal.get("stage") != "dense_anchor":
        raise ValueError("proposal must be a sealed dense-anchor fit")
    if seed.get("stage") not in ("dense_anchor", "profile_zoom", "annealed"):
        raise ValueError("unsupported sealed seed stage")
    if proposal["unit"] != seed["unit"]:
        raise ValueError("proposal and seed units differ")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    _validate_source_provenance(proposal)
    unit = proposal["unit"]
    if unit["size"] != 1 or unit["unit_id"] not in ("DS10-S01", "DS11-S02"):
        raise ValueError("RF calibration v1 is restricted to the two frozen pilots")
    output = ROOT / "runs" / run_id / unit["unit_id"]
    output.mkdir(parents=True, exist_ok=False)
    bundle = load_module(
        "rf_calibration_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    data = bundle.Data(ROOT / "scans" / unit["session_ids"][0])
    started = time.monotonic()
    fitted = fit_rf_calibration(
        data, proposal, seed, case_budget_s=case_budget_s, max_cycles=6
    )
    receipt = {
        "schema": "multiscan-rf-calibration-fit/v1",
        "stage": "rf_calibration",
        "unit": unit,
        "dataset": proposal["dataset"],
        "run_id": run_id,
        "proposal_fit": str(proposal_path),
        "proposal_fit_sha256": digest(proposal_path),
        "seed_fit": str(seed_path),
        "seed_fit_sha256": digest(seed_path),
        "selection_sha256": proposal["selection_sha256"],
        "inputs": proposal["inputs"],
        "source_hashes": {
            path.name: digest(path)
            for path in sorted(ROOT.glob("*.py"))
            if not path.name.startswith("test_")
        },
        "configuration": {
            "case_budget_s": float(case_budget_s),
            "max_cycles": 6,
            "sigma_hz": 200.0,
            "coefficient_prior_sigma_hz_ghz": COEFFICIENT_PRIOR_SIGMA_HZ_GHZ,
            "coefficient_bound_hz_ghz": COEFFICIENT_BOUND_HZ_GHZ,
            "extra_dof": 2,
        },
        "reference_read_before_seal": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    fit_sha256 = digest(fit_path)
    reference = json.loads(
        (ROOT / "scans" / unit["session_ids"][0] / "evaluation.json").read_text()
    )["reference_site"]
    errors = []
    expected = bundle._COMMON.ecef(reference["latitude_deg"], reference["longitude_deg"])
    for trial in fitted["trials"]:
        estimated = bundle._COMMON.ecef(*bundle._COMMON.coordinates(trial["parameters"][:2]))
        errors.append(
            {
                "satellite_count": trial["satellite_count"],
                "objective": trial["objective"],
                "selection_score": trial["selection_score"],
                "success": trial["success"],
                "status": trial["status"],
                "coefficients_hz_ghz": trial["coefficients_hz_ghz"],
                "reference_error_km": float(np.linalg.norm(estimated - expected)),
            }
        )
    evaluation = {
        "schema": "multiscan-rf-calibration-evaluation/v1",
        "unit_id": unit["unit_id"],
        "fit_sha256": fit_sha256,
        "trial_reference_errors": errors,
        "objective_selected_satellite_count": fitted["score_leader"]["satellite_count"],
        "selection_resolved": fitted["selection_resolved"],
        "eligible_for_cohort": False,
        "scope": "Post-seal reference evaluation only; no reference-derived fitting or selection.",
    }
    (output / "evaluation.json").write_text(json.dumps(serializable(evaluation), indent=2) + "\n")
    return receipt, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal-fit", required=True, type=Path)
    parser.add_argument("--seed-fit", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case-budget-s", type=float, default=90.0)
    args = parser.parse_args()
    receipt, evaluation = run_case(
        args.proposal_fit, args.seed_fit, args.run_id, args.case_budget_s
    )
    print(
        json.dumps(
            serializable({
                "unit_id": receipt["unit"]["unit_id"],
                "fit_sha256": evaluation["fit_sha256"],
                "rf_centers_hz": receipt["fit"]["rf_centers_hz"],
                "trial_reference_errors": evaluation["trial_reference_errors"],
            })
        )
    )


if __name__ == "__main__":
    main()
