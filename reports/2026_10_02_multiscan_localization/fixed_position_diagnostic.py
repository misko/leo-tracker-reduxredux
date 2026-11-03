"""Truth-free fixed-position nuisance fit plus an explicitly oracle-only CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from prediction_jacobian import paired_prediction_jacobian
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import frozen_row_weights
from track_likelihood import prepare_track_grouped_likelihood


def _fit_payload(sourcefit):
    if not isinstance(sourcefit, dict):
        raise TypeError("sourcefit must be a decoded fit receipt")
    return sourcefit["fit"] if "fit" in sourcefit else sourcefit


def fit_nuisance_at_position(data, sourcefit, position_km, budget_s=45):
    """Fit RX lines and selected timing offsets at one fixed supplied position.

    This function never reads reference coordinates.  The selected bank,
    anchors, masses, and initialization all come from ``sourcefit``.
    """

    from scipy.optimize import minimize

    if not np.isfinite(budget_s) or budget_s <= 0:
        raise ValueError("budget_s must be positive and finite")
    fit = _fit_payload(sourcefit)
    if not fit.get("keep_track_identity", False):
        raise ValueError("sourcefit must retain coherent track identity")
    leader = fit["score_leader"]
    satellites = np.asarray(leader["satellite_indices"], dtype=int)
    if satellites.ndim != 1 or not len(satellites) or len(np.unique(satellites)) != len(satellites):
        raise ValueError("source score leader has an invalid satellite bank")
    if np.any(satellites < 0) or np.any(satellites >= len(data.numbers)):
        raise ValueError("source score leader satellite falls outside data")
    source_parameters = np.asarray(leader["parameters"], dtype=float)
    if source_parameters.shape != (6 + len(data.numbers),) or np.any(~np.isfinite(source_parameters)):
        raise ValueError("source score leader parameters do not match data")
    position_km = np.asarray(position_km, dtype=float)
    if position_km.shape != (2,) or np.any(~np.isfinite(position_km)):
        raise ValueError("position_km must be one finite east/north pair")
    masses = leader["identity_masses"]
    anchors = fit["anchors"]
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[np.asarray(anchor["groups"]) for anchor in anchors],
    )

    initial = source_parameters.copy()
    initial[:2] = position_km
    initial[6:] = 0.0
    initial[6 + satellites] = source_parameters[6 + satellites]
    active = np.r_[np.arange(2, 6), 6 + satellites]
    scales = np.r_[1000.0, 10.0, 1000.0, 10.0, np.ones(len(satellites))]
    bounds = [
        (None, None),
        (-5.0, 5.0),
        (None, None),
        (-5.0, 5.0),
        *([(-3.0, 3.0)] * len(satellites)),
    ]
    rows = np.repeat(np.arange(len(data.times)), len(satellites))
    paired_satellites = np.tile(satellites, len(data.times))
    deadline = time.monotonic() + float(budget_s)
    best = [float("inf"), initial[active] / scales]
    evaluations = 0

    def evaluate(vector, check_time=True):
        nonlocal evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("Fixed-position nuisance budget exhausted")
        parameters = initial.copy()
        parameters[active] = np.asarray(vector) * scales
        if not np.array_equal(parameters[:2], position_km):
            raise AssertionError("fixed position changed during nuisance evaluation")
        predicted, visible, jacobian = paired_prediction_jacobian(
            data, parameters, rows, paired_satellites
        )
        likelihood = prepared.evaluate(
            predicted.reshape(-1, len(satellites)),
            visible.reshape(-1, len(satellites)),
            sigma_hz=200.0,
            raw_satellite_mass=np.asarray(masses["raw_satellite_mass"], dtype=float),
            raw_background_mass=float(masses["raw_background_mass"]),
            anchor_satellite_mass=np.asarray(masses["anchor_satellite_mass"], dtype=float),
            anchor_unknown_mass=np.asarray(masses["anchor_unknown_mass"], dtype=float),
            track_contamination=0.2,
            return_gradient=True,
        )
        evaluations += 1
        tau = parameters[6 + satellites]
        prior = 0.5 * float(np.sum(tau**2))
        value = -float(likelihood["total_log_likelihood"]) + prior
        full_gradient = -jacobian.transpose_multiply(
            likelihood.pop("prediction_gradient").ravel()
        )
        full_gradient[6 + satellites] += tau
        if value < best[0]:
            best[:] = [value, np.asarray(vector).copy()]
        return value, full_gradient[active] * scales, parameters, full_gradient, likelihood, prior

    def objective_and_gradient(vector):
        value, gradient, _, _, _, _ = evaluate(vector)
        return value, gradient

    started = time.monotonic()
    optimizer_success = False
    optimizer_message = ""
    iterations = None
    try:
        fitted = minimize(
            objective_and_gradient,
            initial[active] / scales,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 500, "maxfun": 1000, "ftol": 1e-9},
        )
        optimizer_success = bool(fitted.success)
        optimizer_message = str(fitted.message)
        iterations = int(fitted.nit)
        evaluate(fitted.x, check_time=False)
    except TimeoutError as error:
        optimizer_message = str(error)
    vector = best[1]
    objective, gradient, parameters, full_gradient, likelihood, prior = evaluate(
        vector, check_time=False
    )
    projected_gradient = gradient.copy()
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None and vector[index] <= lower and gradient[index] > 0:
            projected_gradient[index] = 0.0
        if upper is not None and vector[index] >= upper and gradient[index] < 0:
            projected_gradient[index] = 0.0
    return {
        "parameters": parameters,
        "position_km": parameters[:2].copy(),
        "position_fixed": True,
        "selected_satellite_indices": satellites,
        "selected_catalog_numbers": np.asarray(data.numbers)[satellites],
        "objective": float(objective),
        "total_log_likelihood": float(likelihood["total_log_likelihood"]),
        "tau_prior": float(prior),
        "source_leader_objective": float(leader["objective"]),
        "success": optimizer_success,
        "status": "converged" if optimizer_success else "nonconverged",
        "message": optimizer_message,
        "free_parameters": int(4 + len(satellites)),
        "evaluations": evaluations,
        "iterations": iterations,
        "elapsed_s": time.monotonic() - started,
        "projected_gradient_inf_norm": float(np.max(np.abs(projected_gradient))),
        "fixed_position_gradient": full_gradient[:2].copy(),
        "satellite_support": likelihood["satellite_support"],
        "null_support": float(likelihood["null_support"]),
        "track_unknown_responsibility": likelihood["track_unknown_responsibility"],
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
        "track_contamination": 0.2,
    }


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _position_error_km(common, point, reference):
    estimated = common.ecef(*common.coordinates(np.asarray(point, dtype=float)))
    expected = common.ecef(reference["latitude_deg"], reference["longitude_deg"])
    return float(np.linalg.norm(estimated - expected))


def _inverse_reference_position(common, reference, initial):
    from scipy.optimize import least_squares

    cosine = np.cos(np.deg2rad(reference["latitude_deg"]))

    def residual(point):
        latitude, longitude = common.coordinates(point)
        longitude_error = (longitude - reference["longitude_deg"] + 180.0) % 360.0 - 180.0
        return np.asarray(
            [latitude - reference["latitude_deg"], cosine * longitude_error], dtype=float
        )

    fitted = least_squares(
        residual,
        np.asarray(initial, dtype=float),
        bounds=([-200.0, -200.0], [200.0, 200.0]),
        xtol=1e-13,
        ftol=1e-13,
        gtol=1e-13,
        max_nfev=100,
    )
    if not fitted.success or np.linalg.norm(fitted.fun, ord=np.inf) > 1e-9:
        raise RuntimeError(f"Reference-coordinate inversion failed: {fitted.message}")
    return fitted.x


def run_oracle(source_fit_path, output_path, budget_s):
    """Run one explicitly truth-conditioned diagnostic after sealing source selection."""

    source_fit_path = Path(source_fit_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    if not 0 < budget_s <= 45:
        raise ValueError("oracle nuisance budget must lie in (0, 45]")

    source_fit_sha256 = _digest(source_fit_path)
    source_receipt = json.loads(source_fit_path.read_text())
    if source_receipt.get("stage") != "coherent":
        raise ValueError("oracle source must be a sealed coherent fit")
    unit = source_receipt["unit"]
    if unit.get("unit_id") != "DS10-S01" or unit.get("size") != 1:
        raise ValueError("this bounded oracle CLI is restricted to DS10-S01")
    fit = source_receipt["fit"]
    selected_leader = fit["score_leader"]
    selected_satellites = np.asarray(selected_leader["satellite_indices"], dtype=int).copy()
    selected_parameters = np.asarray(selected_leader["parameters"], dtype=float).copy()

    source_evaluation_path = source_fit_path.with_name("evaluation.json")
    source_evaluation = json.loads(source_evaluation_path.read_text())
    if source_evaluation.get("fit_sha256") != source_fit_sha256:
        raise ValueError("source evaluation does not bind the sealed fit")
    session_id = unit["session_ids"][0]
    reference_path = ROOT / "scans" / session_id / "evaluation.json"
    reference_receipt = json.loads(reference_path.read_text())
    reference = reference_receipt["reference_site"]

    bundle = load_module(
        "fixed_position_oracle_bundle",
        ROOT.parent / "2026_10_02_localization_benchmark/bundle.py",
    )
    data = bundle.Data(ROOT / "scans" / session_id)
    oracle_position = _inverse_reference_position(
        bundle._COMMON, reference, selected_parameters[:2]
    )
    if not np.array_equal(
        np.asarray(fit["score_leader"]["satellite_indices"], dtype=int),
        selected_satellites,
    ):
        raise AssertionError("selected bank changed after oracle reference read")

    started = time.monotonic()
    fixed = fit_nuisance_at_position(
        data, source_receipt, oracle_position, budget_s=budget_s
    )
    elapsed = time.monotonic() - started
    payload = {
        "schema": "multiscan-fixed-position-oracle-diagnostic/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "oracle": True,
        "eligible_for_cohort": False,
        "unit_id": unit["unit_id"],
        "dataset": source_receipt["dataset"],
        "source_run_id": source_receipt["run_id"],
        "selection_rule": "sealed source score_leader before oracle reference read",
        "selected_satellite_indices": selected_satellites,
        "selected_catalog_numbers": np.asarray(data.numbers)[selected_satellites],
        "source_fit": str(source_fit_path),
        "source_fit_sha256": source_fit_sha256,
        "source_evaluation_sha256": _digest(source_evaluation_path),
        "reference_evaluation_sha256": _digest(reference_path),
        "selection_sha256": source_receipt["selection_sha256"],
        "input_hashes": source_receipt["inputs"],
        "oracle_position_km": oracle_position,
        "free_position_km": selected_parameters[:2],
        "free_objective": float(selected_leader["objective"]),
        "fixed_objective": float(fixed["objective"]),
        "fixed_minus_free_objective": float(
            fixed["objective"] - selected_leader["objective"]
        ),
        "free_reference_error_km": _position_error_km(
            bundle._COMMON, selected_parameters[:2], reference
        ),
        "fixed_reference_error_km": _position_error_km(
            bundle._COMMON, fixed["position_km"], reference
        ),
        "fixed_fit": fixed,
        "fit_calls": 1,
        "elapsed_s": elapsed,
        "scope": (
            "ORACLE diagnostic conditioned on evaluation reference coordinates after a sealed "
            "unbiased fit and score-leader bank selection. Not eligible for cohort results, "
            "model selection, tuning, or validation. Free and fixed results are local fits; "
            "neither is claimed globally optimal."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serializable(payload), indent=2) + "\n")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--source-fit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget-s", type=float, default=45.0)
    args = parser.parse_args()
    if not args.oracle:
        parser.error("--oracle is required because this command reads reference coordinates")
    result = run_oracle(args.source_fit, args.output, args.budget_s)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "source_fit_sha256": result["source_fit_sha256"],
                "free_objective": result["free_objective"],
                "fixed_objective": result["fixed_objective"],
                "fixed_minus_free_objective": result["fixed_minus_free_objective"],
                "free_reference_error_km": result["free_reference_error_km"],
                "fixed_reference_error_km": result["fixed_reference_error_km"],
                "eligible_for_cohort": False,
            }
        )
    )


if __name__ == "__main__":
    main()
