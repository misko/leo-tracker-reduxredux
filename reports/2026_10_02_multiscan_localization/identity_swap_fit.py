"""One-shot refit of the truth-free candidate-identity escape diagnostic."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def swapped_bank_and_initial(data, incumbent, prescribed_swap):
    selected = np.asarray(incumbent["satellite_indices"], dtype=int)
    removed = int(prescribed_swap["removed_index"])
    added = int(prescribed_swap["added_index"])
    locations = np.flatnonzero(selected == removed)
    if len(locations) != 1 or added in set(selected.tolist()):
        raise ValueError("prescribed swap does not replace one selected identity with one unused identity")
    if not 0 <= added < len(data.numbers):
        raise ValueError("inserted candidate lies outside the frozen candidate pool")
    slot = int(locations[0])
    swapped = selected.copy()
    swapped[slot] = added
    initial = np.asarray(incumbent["parameters"], dtype=float).copy()
    if initial.shape != (6 + len(data.numbers),) or np.any(~np.isfinite(initial)):
        raise ValueError("incumbent parameters do not match the candidate pool")
    removed_tau = float(initial[6 + removed])
    initial[6 + added] = 0.0
    return swapped, initial, slot, removed_tau


def _validate_incumbent_objective(data, prepared, incumbent, masses):
    satellites = np.asarray(incumbent["satellite_indices"], dtype=int)
    parameters = np.asarray(incumbent["parameters"], dtype=float)
    predicted, visible, _ = SharedPredictionPlan(data, satellites).predict(parameters)
    predicted = predicted.reshape(len(data.times), len(satellites))
    visible = visible.reshape(predicted.shape)
    result = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=200.0,
        **masses,
        track_contamination=0.2,
    )
    tau_prior = 0.5 * float(np.sum(parameters[6 + satellites] ** 2))
    objective = float(-result["total_log_likelihood"] + tau_prior)
    if not np.isclose(objective, incumbent["objective"], rtol=0.0, atol=1e-6):
        raise ValueError("sealed incumbent objective does not reproduce under frozen inputs")
    return objective


def fit_identity_swap(data, expanded, diagnostic_unit, *, budget_s=20.0):
    """Fit exactly one prescribed same-cardinality identity replacement."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= 20:
        raise ValueError("budget_s must lie in (0, 20]")
    expanded_fit = expanded["fit"] if "fit" in expanded else expanded
    incumbent_source = expanded_fit["score_leader"]
    if not incumbent_source["success"]:
        raise ValueError("sealed expanded-bank incumbent must be converged")
    prescribed = diagnostic_unit["best_swap"]
    if prescribed["penalized_score_improvement"] <= 0:
        raise ValueError("diagnostic did not prescribe a score-improving swap")
    swapped, initial, slot, removed_tau = swapped_bank_and_initial(
        data, incumbent_source, prescribed
    )
    if len(swapped) != diagnostic_unit["selected_count"]:
        raise ValueError("diagnostic and incumbent cardinalities differ")
    if not np.array_equal(
        np.asarray(incumbent_source["satellite_indices"], dtype=int),
        np.asarray(diagnostic_unit["selected_indices"], dtype=int),
    ):
        raise ValueError("diagnostic selected bank differs from expanded incumbent")
    anchors = expanded_fit["anchors"]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in anchors],
    )
    masses = {
        key: np.asarray(value, dtype=float)
        for key, value in incumbent_source["identity_masses"].items()
    }
    masses["raw_background_mass"] = float(
        incumbent_source["identity_masses"]["raw_background_mass"]
    )
    _validate_incumbent_objective(data, prepared, incumbent_source, masses)
    likelihood = FixedBankLikelihood(prepared, masses)
    swapped_trial = refine_gauss_newton(
        data,
        initial,
        swapped,
        np.ones(len(swapped)),
        likelihood,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        tau_bound_s=3.0,
        budget_s=float(budget_s),
    )
    swapped_trial.pop("satellite_weights")
    swapped_trial["branch"] = "prescribed_single_swap"
    swapped_trial["identity_masses"] = masses
    swapped_trial["removed_slot"] = slot
    swapped_trial["removed_index"] = int(prescribed["removed_index"])
    swapped_trial["removed_catalog_number"] = int(prescribed["removed_catalog_number"])
    swapped_trial["removed_tau_preserved_in_global_parameters_s"] = removed_tau
    swapped_trial["added_index"] = int(prescribed["added_index"])
    swapped_trial["added_catalog_number"] = int(prescribed["added_catalog_number"])
    swapped_trial["added_tau_initial_s"] = 0.0
    swapped_trial["diagnostic_fixed_parameter_score_improvement"] = float(
        prescribed["penalized_score_improvement"]
    )
    swapped_trial["support_argument_role"] = (
        "Positive placeholder required by Gauss-Newton; FixedBankLikelihood uses frozen masses."
    )
    swapped_trial["likelihood_diagnostics"] = {
        key: value
        for key, value in likelihood.last_result.items()
        if "track" in key or key.endswith("group_count")
    }
    incumbent = copy.deepcopy(incumbent_source)
    incumbent["branch"] = "sealed_expanded_incumbent"
    incumbent["refit_performed"] = False
    incumbent["identity_masses"] = masses
    if not np.isclose(
        swapped_trial["entry_penalty"], incumbent["entry_penalty"], rtol=0.0, atol=1e-12
    ):
        raise ValueError("same-cardinality branches have different complexity penalties")
    trials = [incumbent, swapped_trial]
    selection = select_trials(trials)
    return {
        "anchors": anchors,
        "full_expanded_bank": expanded_fit["full_bank"],
        "incumbent_satellite_indices": incumbent["satellite_indices"],
        "swapped_satellite_indices": swapped,
        "prescribed_swap": prescribed,
        "trials": trials,
        **selection,
        "single_swap_only": True,
        "greedy_search_performed": False,
        "incumbent_refit_performed": False,
        "swapped_refit_count": 1,
        "common_complexity_penalty": float(incumbent["entry_penalty"]),
        "scope": (
            "Truth-free one-shot refit of the diagnostic's highest-scoring single identity swap. "
            "The sealed expanded-bank incumbent remains an unmodified comparison branch. The "
            "swapped branch preserves K, position/RX start, all incumbent global parameters, "
            "frozen row masses, anchors, identity-mass columns, sigma, tau prior, bounds, and "
            "complexity penalty; only the inserted tau is reset to zero before one GN fit."
        ),
    }


def run_case(diagnostic_path, unit_id, run_id, budget_s):
    diagnostic_path = Path(diagnostic_path)
    diagnostic = json.loads(diagnostic_path.read_text())
    if diagnostic.get("schema") != "candidate-identity-escape-diagnostic/v1":
        raise ValueError("unsupported candidate-identity diagnostic")
    if diagnostic.get("reference_coordinates_read") is not False or diagnostic.get("fits_performed") != 0:
        raise ValueError("diagnostic provenance is not truth-free and fit-free")
    matches = [unit for unit in diagnostic["units"] if unit["unit_id"] == unit_id]
    if len(matches) != 1:
        raise ValueError("diagnostic must contain exactly one requested unit")
    diagnostic_unit = matches[0]
    expanded_path = Path(diagnostic_unit["expanded_fit"])
    if digest(expanded_path) != diagnostic_unit["expanded_fit_sha256"]:
        raise ValueError("expanded source no longer matches the diagnostic binding")
    expanded = json.loads(expanded_path.read_text())
    if expanded.get("stage") != "expanded_bank" or expanded["unit"]["unit_id"] != unit_id:
        raise ValueError("diagnostic expanded source has the wrong stage or unit")
    dense_path = Path(diagnostic_unit["dense_source_fit"])
    if digest(dense_path) != diagnostic_unit["dense_source_fit_sha256"]:
        raise ValueError("dense source no longer matches the diagnostic binding")
    if expanded["source_fit_sha256"] != diagnostic_unit["dense_source_fit_sha256"]:
        raise ValueError("expanded receipt does not bind the diagnostic dense source")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    output = ROOT / "runs" / run_id / unit_id
    output.mkdir(parents=True, exist_ok=False)
    sources = {
        path.name: digest(path)
        for path in sorted(ROOT.glob("*.py"))
        if not path.name.startswith("test_")
    }
    bundle = load_module(
        "identity_swap_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    data = bundle.Data(ROOT / "scans" / expanded["unit"]["session_ids"][0])
    started = time.monotonic()
    fitted = fit_identity_swap(data, expanded, diagnostic_unit, budget_s=budget_s)
    receipt = {
        "schema": "multiscan-identity-swap-fit/v1",
        "stage": "identity_swap",
        "unit": expanded["unit"],
        "run_id": run_id,
        "diagnostic": str(diagnostic_path),
        "diagnostic_sha256": digest(diagnostic_path),
        "expanded_fit": str(expanded_path),
        "expanded_fit_sha256": digest(expanded_path),
        "dense_source_fit": str(dense_path),
        "dense_source_fit_sha256": digest(dense_path),
        "source_hashes": sources,
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "budget_s": float(budget_s),
            "optimizer": "complete-data-fisher-gn/v2",
            "swap_count_fitted": 1,
            "incumbent_refit": False,
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
        (ROOT / "scans" / expanded["unit"]["session_ids"][0] / "evaluation.json").read_text()
    )["reference_site"]
    expected = bundle._COMMON.ecef(reference["latitude_deg"], reference["longitude_deg"])
    branches = []
    for trial in fitted["trials"]:
        estimated = bundle._COMMON.ecef(*bundle._COMMON.coordinates(trial["parameters"][:2]))
        branches.append(
            {
                "branch": trial["branch"],
                "satellite_count": trial["satellite_count"],
                "objective": trial["objective"],
                "selection_score": trial["selection_score"],
                "success": trial["success"],
                "status": trial["status"],
                "reference_error_km": float(np.linalg.norm(estimated - expected)),
            }
        )
    evaluation = {
        "schema": "multiscan-identity-swap-evaluation/v1",
        "unit_id": unit_id,
        "fit_sha256": fit_sha256,
        "branch_reference_errors": branches,
        "objective_selected_branch": fitted["score_leader"]["branch"],
        "selection_resolved": fitted["selection_resolved"],
        "eligible_for_cohort": False,
        "scope": "Post-seal reference evaluation only; no reference-derived swap, fit, or selection.",
    }
    (output / "evaluation.json").write_text(json.dumps(serializable(evaluation), indent=2) + "\n")
    return receipt, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", required=True, type=Path)
    parser.add_argument("--unit-id", required=True, choices=("DS10-S01", "DS11-S02"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--budget-s", type=float, default=20.0)
    args = parser.parse_args()
    receipt, evaluation = run_case(args.diagnostic, args.unit_id, args.run_id, args.budget_s)
    print(
        json.dumps(
            serializable(
                {
                    "unit_id": receipt["unit"]["unit_id"],
                    "fit_sha256": evaluation["fit_sha256"],
                    "objective_selected_branch": evaluation["objective_selected_branch"],
                    "branch_reference_errors": evaluation["branch_reference_errors"],
                }
            )
        )
    )


if __name__ == "__main__":
    main()
