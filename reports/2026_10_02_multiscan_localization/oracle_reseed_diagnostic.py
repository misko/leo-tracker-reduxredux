"""Explicitly oracle-only fixed-position nuisance reseed diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import frozen_row_weights
from track_likelihood import prepare_track_grouped_likelihood


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fit_payload(receipt):
    return receipt["fit"] if "fit" in receipt else receipt


def _evaluate_diagnostics(data, prepared, masses, satellites, parameters):
    parameters = np.asarray(parameters, dtype=float)
    plan = SharedPredictionPlan(data, satellites)
    predicted, visible, jacobian = plan.predict(parameters)
    predicted = predicted.reshape(len(data.times), len(satellites))
    visible = visible.reshape(predicted.shape)
    result = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=200.0,
        **masses,
        track_contamination=0.2,
        return_gradient=True,
    )
    gradient = -jacobian.transpose_multiply(result["prediction_gradient"].ravel())
    tau_indices = 6 + satellites
    tau = parameters[tau_indices]
    gradient[tau_indices] += tau
    objective = float(-result["total_log_likelihood"] + 0.5 * np.sum(tau**2))
    raw_indices = prepared.raw_group_indices
    return {
        "objective": objective,
        "total_log_likelihood": float(result["total_log_likelihood"]),
        "tau_prior": float(0.5 * np.sum(tau**2)),
        "fixed_position_gradient": gradient[:2].copy(),
        "physical_gradient_inf_norm": float(np.max(np.abs(gradient))),
        "satellite_support": result["satellite_support"],
        "null_support": float(result["null_support"]),
        "raw_satellite_support": np.sum(
            result["group_satellite_responsibility"][raw_indices], axis=0
        ),
        "raw_null_support": float(
            np.sum(result["group_null_responsibility"][raw_indices])
        ),
        "track_identity_responsibility": result["track_identity_responsibility"],
        "track_unknown_responsibility": result["track_unknown_responsibility"],
    }


def fit_oracle_reseeds(data, source, zoom, prior_oracle, *, budget_s=45.0):
    """Run two oracle-fixed nuisance fits from sealed, explicitly supplied starts."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= 45:
        raise ValueError("budget_s must lie in (0, 45]")
    source_fit = _fit_payload(source)
    zoom_fit = _fit_payload(zoom)
    leader = source_fit["score_leader"]
    satellites = np.asarray(leader["satellite_indices"], dtype=int)
    if len(satellites) != 12 or len(np.unique(satellites)) != len(satellites):
        raise ValueError("oracle reseed diagnostic requires the sealed K12 bank")
    masses = leader["identity_masses"]
    oracle_position = np.asarray(prior_oracle["oracle_position_km"], dtype=float)
    if oracle_position.shape != (2,) or np.any(~np.isfinite(oracle_position)):
        raise ValueError("prior oracle artifact has an invalid fixed position")
    zoom_parameters = np.asarray(zoom_fit["selected"]["fit"]["parameters"], dtype=float)
    prior_parameters = np.asarray(prior_oracle["fixed_fit"]["parameters"], dtype=float)
    expected_shape = (6 + len(data.numbers),)
    if zoom_parameters.shape != expected_shape or prior_parameters.shape != expected_shape:
        raise ValueError("sealed nuisance starts do not match the candidate bank")
    if not np.array_equal(
        satellites, np.asarray(zoom_fit["selected"]["fit"]["satellite_indices"], dtype=int)
    ):
        raise ValueError("zoom-selected bank differs from the sealed source bank")
    if not np.array_equal(
        satellites, np.asarray(prior_oracle["selected_satellite_indices"], dtype=int)
    ):
        raise ValueError("prior oracle bank differs from the sealed source bank")

    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[np.asarray(anchor["groups"]) for anchor in source_fit["anchors"]],
    )
    starts = (
        ("sealed_profile_zoom_selected", zoom_parameters),
        ("sealed_previous_oracle_fixed", prior_parameters),
    )
    trials = []
    for name, initial in starts:
        likelihood = FixedBankLikelihood(prepared, masses)
        fitted = refine_gauss_newton(
            data,
            initial.copy(),
            satellites,
            np.ones(len(satellites)),
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            slope_bound=50.0,
            budget_s=float(budget_s),
            fixed_position_km=oracle_position,
        )
        diagnostics = _evaluate_diagnostics(
            data, prepared, masses, satellites, fitted["parameters"]
        )
        if abs(diagnostics["objective"] - fitted["objective"]) > 1e-7:
            raise ValueError("fixed fit objective does not match independent diagnostics")
        trials.append(
            {
                "initialization": name,
                "initial_parameters_sha256": hashlib.sha256(
                    np.asarray(initial, dtype="<f8").tobytes()
                ).hexdigest(),
                "fit": fitted,
                "diagnostics": diagnostics,
            }
        )
    best = min(trials, key=lambda trial: trial["fit"]["objective"])
    return {
        "oracle_position_km": oracle_position,
        "satellite_indices": satellites,
        "trials": trials,
        "best_initialization": best["initialization"],
        "best_fixed_objective": float(best["fit"]["objective"]),
        "previous_oracle_fixed_objective": float(prior_oracle["fixed_objective"]),
        "profile_zoom_free_objective": float(zoom_fit["selected"]["fit"]["objective"]),
        "best_fixed_minus_previous_oracle": float(
            best["fit"]["objective"] - prior_oracle["fixed_objective"]
        ),
        "best_fixed_minus_profile_zoom_free": float(
            best["fit"]["objective"] - zoom_fit["selected"]["fit"]["objective"]
        ),
        "fit_calls": 2,
        "eligible_for_cohort": False,
        "scope": (
            "Explicit oracle-only fixed-position nuisance diagnostic. Both starts and the bank, "
            "anchors, and masses come from sealed artifacts. No oracle-derived parameter is "
            "passed to a free-position fit or made eligible for cohort selection."
        ),
    }


def run_oracle_reseeds(source_path, zoom_path, prior_oracle_path, output_path, budget_s):
    source_path = Path(source_path)
    zoom_path = Path(zoom_path)
    prior_oracle_path = Path(prior_oracle_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    source = json.loads(source_path.read_text())
    zoom = json.loads(zoom_path.read_text())
    prior_oracle = json.loads(prior_oracle_path.read_text())
    source_sha256 = _digest(source_path)
    zoom_sha256 = _digest(zoom_path)
    prior_oracle_sha256 = _digest(prior_oracle_path)
    if source.get("stage") != "coherent" or source["unit"]["unit_id"] != "DS10-S01":
        raise ValueError("source must be the sealed DS10-S01 coherent fit")
    if zoom.get("stage") != "profile_zoom" or zoom["unit"] != source["unit"]:
        raise ValueError("zoom artifact does not bind the source unit")
    if zoom["source_fit_sha256"] != source_sha256:
        raise ValueError("zoom artifact does not bind the source fit")
    if prior_oracle.get("oracle") is not True or prior_oracle.get("eligible_for_cohort") is not False:
        raise ValueError("prior artifact must be explicitly oracle-only")
    if prior_oracle["source_fit_sha256"] != source_sha256:
        raise ValueError("prior oracle artifact does not bind the source fit")

    session_id = source["unit"]["session_ids"][0]
    bundle = load_module(
        "oracle_reseed_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    data = bundle.Data(ROOT / "scans" / session_id)
    result = fit_oracle_reseeds(
        data, source, zoom, prior_oracle, budget_s=budget_s
    )
    payload = {
        "schema": "multiscan-oracle-fixed-reseed-diagnostic/v1",
        "oracle": True,
        "eligible_for_cohort": False,
        "unit_id": source["unit"]["unit_id"],
        "dataset": source["dataset"],
        "bindings": {
            "source_fit": {"path": str(source_path), "sha256": source_sha256},
            "profile_zoom_fit": {"path": str(zoom_path), "sha256": zoom_sha256},
            "prior_oracle": {
                "path": str(prior_oracle_path),
                "sha256": prior_oracle_sha256,
            },
        },
        "configuration": {
            "budget_s_per_start": float(budget_s),
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
            "optimizer": "complete-data-fisher-gn/v2",
        },
        "source_hashes": {
            path.name: _digest(path)
            for path in sorted(ROOT.glob("*.py"))
            if not path.name.startswith("test_")
        },
        "result": result,
        "reference_evaluation_file_read": False,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serializable(payload), indent=2) + "\n")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--source-fit", required=True, type=Path)
    parser.add_argument("--zoom-fit", required=True, type=Path)
    parser.add_argument("--prior-oracle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget-s", type=float, default=45.0)
    args = parser.parse_args()
    if not args.oracle:
        parser.error("--oracle is required for this truth-conditioned diagnostic")
    payload = run_oracle_reseeds(
        args.source_fit,
        args.zoom_fit,
        args.prior_oracle,
        args.output,
        args.budget_s,
    )
    result = payload["result"]
    print(
        json.dumps(
            {
                "output": str(args.output),
                "best_initialization": result["best_initialization"],
                "best_fixed_objective": result["best_fixed_objective"],
                "best_fixed_minus_profile_zoom_free": result[
                    "best_fixed_minus_profile_zoom_free"
                ],
                "eligible_for_cohort": False,
            }
        )
    )


if __name__ == "__main__":
    main()
