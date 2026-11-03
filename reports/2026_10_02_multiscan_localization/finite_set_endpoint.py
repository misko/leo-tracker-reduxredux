"""Oracle-only finite-set endpoint continuation from a sealed homotopy node 7."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from finite_set_fit import GroupMedianGeometryData, build_likelihood_arms
from finite_set_fixed_position import _decompose_arm, _evaluate_state, freeze_selected_arms
from finite_set_homotopy import _support_receipt
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from rough_smoke import load_module, serializable
from selection import ROOT


DEFAULT_RUN_ID = "finite-set-fixed-position-endpoint-v1"
DEFAULT_BUDGET_S = 20.0
NUMERICAL_DEPENDENCIES = (
    "finite_set_endpoint.py",
    "finite_set_homotopy.py",
    "finite_set_fixed_position.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "gauss_newton.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "grouped_likelihood.py",
    "track_likelihood.py",
    "staged_fit.py",
)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _snapshot(paths):
    return {str(Path(path).resolve()): _digest(path) for path in paths}


def _assert_snapshot(snapshot):
    changed = [path for path, value in snapshot.items() if _digest(path) != value]
    if changed:
        raise RuntimeError(f"endpoint provenance changed before seal: {', '.join(changed)}")


def _sealed_node7(homotopy, source_sha256, unit_id, selected_bank):
    if (
        homotopy.get("schema") != "finite-set-fixed-position-homotopy-oracle/v1"
        or homotopy.get("oracle") is not True
        or homotopy.get("eligible_for_cohort") is not False
        or homotopy.get("unit_id") != unit_id
        or homotopy.get("source_fit_sha256") != source_sha256
    ):
        raise ValueError("homotopy receipt does not bind the sealed source")
    arm = homotopy["fit"]["arms"]["finite_set"]
    if not np.array_equal(np.asarray(arm["selected_bank"], dtype=int), selected_bank):
        raise ValueError("homotopy finite-set bank differs from the sealed source leader")
    matches = [node for node in arm["nodes"] if node.get("node_index") == 7]
    if len(matches) != 1:
        raise ValueError("homotopy must contain exactly one node 7")
    node = matches[0]
    if (
        node.get("fraction_from_free_to_known") != 0.875
        or node.get("attempted") is not True
        or node.get("fit_returned") is not True
    ):
        raise ValueError("homotopy node 7 must be a returned fixed fit")
    parameters = np.asarray(node["parameters"], dtype=float)
    position = np.asarray(node["position_km"], dtype=float)
    if parameters.ndim != 1 or not np.array_equal(parameters[:2], position):
        raise ValueError("homotopy node 7 did not preserve its fixed position")
    return node, parameters.copy()


def fit_finite_endpoint(
    data,
    source,
    homotopy,
    abrupt,
    *,
    source_sha256,
    budget_s=DEFAULT_BUDGET_S,
    refiner=refine_gauss_newton,
    arm_builder=build_likelihood_arms,
    plan_factory=SharedPredictionPlan,
):
    """Run one fixed finite-set endpoint fit from sealed homotopy node 7."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= DEFAULT_BUDGET_S:
        raise ValueError("budget_s must lie in (0, 20]")
    geometry = data if isinstance(data, GroupMedianGeometryData) else GroupMedianGeometryData(data)
    full_bank, frozen = freeze_selected_arms(source, len(geometry.numbers))
    selected = frozen["finite_set"]
    satellites = selected["satellites"]
    unit_id = source["unit"]["unit_id"]
    node7, initial = _sealed_node7(homotopy, source_sha256, unit_id, satellites)
    known_position = np.asarray(homotopy["known_position_km"], dtype=float)
    if known_position.shape != (2,) or np.any(~np.isfinite(known_position)):
        raise ValueError("homotopy known endpoint is invalid")
    if (
        abrupt.get("oracle") is not True
        or abrupt.get("eligible_for_cohort") is not False
        or abrupt.get("unit_id") != unit_id
        or abrupt.get("source_fit_sha256") != source_sha256
        or not np.array_equal(np.asarray(abrupt["oracle_position_km"]), known_position)
    ):
        raise ValueError("abrupt diagnostic does not bind the same known endpoint")
    abrupt_arm = abrupt["fit"]["arms"]["finite_set"]
    if not np.array_equal(np.asarray(abrupt_arm["selected_bank"], dtype=int), satellites):
        raise ValueError("abrupt finite-set bank differs from the sealed source leader")

    likelihood = arm_builder(geometry, len(satellites), len(full_bank))["finite_set"]
    free = _evaluate_state(
        geometry,
        selected["parameters"],
        satellites,
        likelihood,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        plan_factory=plan_factory,
    )
    if not np.isclose(free["objective"], selected["objective"], rtol=1e-9, atol=1e-6):
        raise ValueError("sealed finite-set free objective does not reproduce")

    started = time.monotonic()
    fitted = refiner(
        geometry,
        initial.copy(),
        satellites,
        np.ones(len(satellites)),
        likelihood,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        tau_bound_s=3.0,
        slope_bound=50.0,
        budget_s=float(budget_s),
        fixed_position_km=known_position.copy(),
    )
    parameters = np.asarray(fitted["parameters"], dtype=float)
    if not np.array_equal(parameters[:2], known_position):
        raise AssertionError("endpoint continuation moved the known fixed position")
    if not np.array_equal(np.asarray(fitted["satellite_indices"], dtype=int), satellites):
        raise AssertionError("endpoint continuation changed the frozen bank")
    endpoint = _evaluate_state(
        geometry,
        parameters,
        satellites,
        likelihood,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        plan_factory=plan_factory,
    )
    elapsed = time.monotonic() - started
    if not np.isclose(endpoint["objective"], fitted["objective"], rtol=1e-9, atol=1e-6):
        raise ValueError("endpoint continuation objective does not reproduce")

    abrupt_fixed = abrupt_arm["fixed_reference"]
    abrupt_support = np.asarray(abrupt_fixed["satellite_support"], dtype=float)
    endpoint_support = np.asarray(endpoint["result"]["satellite_support"], dtype=float)
    decomposition = _decompose_arm(
        geometry, "finite_set", satellites, free, endpoint
    )
    return {
        "selected_bank": satellites.copy(),
        "selected_catalog_numbers": np.asarray(geometry.numbers)[satellites],
        "node7_initial_parameters": initial,
        "node7_initial_position_km": np.asarray(node7["position_km"], dtype=float),
        "known_position_km": known_position,
        "fit_calls": 1,
        "free_fit_calls": 0,
        "same_bank_free_node7_endpoint": True,
        "source_free": {
            "parameters": selected["parameters"],
            "objective": free["objective"],
            "success": selected["success"],
            "status": selected["status"],
            "selection_resolved": selected["selection_resolved"],
            "support": _support_receipt("finite_set", free),
        },
        "endpoint": {
            "optimizer": fitted,
            "parameters": parameters,
            "success": bool(fitted["success"]),
            "status": str(fitted["status"]),
            "convergence_reason": str(
                fitted.get("convergence_reason", fitted.get("message", ""))
            ),
            "elapsed_including_receipt_evaluation_s": elapsed,
            "configured_fit_budget_s": float(budget_s),
            "cooperative_budget_overrun_s": float(max(0.0, elapsed - budget_s)),
            "support": _support_receipt("finite_set", endpoint),
            "free_to_endpoint_decomposition": decomposition,
        },
        "abrupt_comparison": {
            "abrupt_success": bool(abrupt_fixed["success"]),
            "abrupt_status": str(abrupt_fixed["status"]),
            "abrupt_objective": float(abrupt_fixed["objective"]),
            "endpoint_minus_abrupt_objective": float(
                endpoint["objective"] - abrupt_fixed["objective"]
            ),
            "abrupt_total_signal_support": float(np.sum(abrupt_support)),
            "endpoint_total_signal_support": float(np.sum(endpoint_support)),
            "endpoint_minus_abrupt_satellite_support": endpoint_support - abrupt_support,
        },
        "cross_arm_absolute_nll_comparisons": False,
        "scope": (
            "One finite-set fixed endpoint continuation from the immutable homotopy node 7 "
            "nuisance state. No eight-node rerun, free fit, bank change, model change, or pipeline "
            "reseed occurs. The bounded endpoint is a local fit and is not a global optimum claim "
            "when unresolved."
        ),
    }


def run_endpoint(
    source_fit_path,
    homotopy_path,
    abrupt_path,
    output_path,
    *,
    budget_s=DEFAULT_BUDGET_S,
):
    source_fit_path = Path(source_fit_path)
    homotopy_path = Path(homotopy_path)
    abrupt_path = Path(abrupt_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    source_sha256 = _digest(source_fit_path)
    source = json.loads(source_fit_path.read_text())
    unit_id = source["unit"]["unit_id"]
    if unit_id not in {"DS10-S01", "DS11-S02"} or source["unit"].get("size") != 1:
        raise ValueError("endpoint continuation is restricted to the finite-set single pilots")

    full_bank, frozen = freeze_selected_arms(source, 64)
    frozen_before_oracle_read = {
        "full_bank": full_bank.copy(),
        "finite_set_bank": frozen["finite_set"]["satellites"].copy(),
        "finite_set_parameters_sha256": frozen["finite_set"]["parameters_sha256"],
    }
    homotopy_sha256 = _digest(homotopy_path)
    abrupt_sha256 = _digest(abrupt_path)
    homotopy = json.loads(homotopy_path.read_text())
    abrupt = json.loads(abrupt_path.read_text())

    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    bundle = load_module(f"finite_set_endpoint_bundle_{unit_id}", bundle_path)
    session_id = source["unit"]["session_ids"][0]
    bundle_directory = ROOT / "scans" / session_id
    data = bundle.Data(bundle_directory)
    source_paths = [ROOT / name for name in NUMERICAL_DEPENDENCIES] + [bundle_path]
    source_snapshot = _snapshot(source_paths)
    artifact_paths = [
        source_fit_path,
        source_fit_path.with_name("evaluation.json"),
        homotopy_path,
        abrupt_path,
        bundle_directory / "bundle.json",
        bundle_directory / "bundle.npz",
    ]
    artifact_snapshot = _snapshot(artifact_paths)
    started = time.monotonic()
    fitted = fit_finite_endpoint(
        data,
        source,
        homotopy,
        abrupt,
        source_sha256=source_sha256,
        budget_s=budget_s,
    )
    _assert_snapshot(source_snapshot)
    _assert_snapshot(artifact_snapshot)
    payload = {
        "schema": "finite-set-fixed-position-endpoint-oracle/v1",
        "generated_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "oracle": True,
        "eligible_for_cohort": False,
        "unit_id": unit_id,
        "run_id": DEFAULT_RUN_ID,
        "source_fit": str(source_fit_path),
        "source_fit_sha256": source_sha256,
        "homotopy": str(homotopy_path),
        "homotopy_sha256": homotopy_sha256,
        "abrupt_diagnostic": str(abrupt_path),
        "abrupt_diagnostic_sha256": abrupt_sha256,
        "source_selection_frozen_before_oracle_read": frozen_before_oracle_read,
        "source_hashes_prefit": source_snapshot,
        "bound_artifact_hashes_prefit": artifact_snapshot,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "fit": fitted,
        "elapsed_s": time.monotonic() - started,
        "free_fits_run": False,
        "original_homotopy_receipt_modified": False,
        "scope": fitted["scope"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serializable(payload), indent=2) + "\n")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--source-fit", required=True, type=Path)
    parser.add_argument("--homotopy", required=True, type=Path)
    parser.add_argument("--abrupt-diagnostic", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget-s", type=float, default=DEFAULT_BUDGET_S)
    args = parser.parse_args()
    if not args.oracle:
        parser.error("--oracle is required because this command uses a known-position endpoint")
    if not 0 < args.budget_s <= DEFAULT_BUDGET_S:
        parser.error("budget-s must lie in (0, 20]")
    result = run_endpoint(
        args.source_fit,
        args.homotopy,
        args.abrupt_diagnostic,
        args.output,
        budget_s=args.budget_s,
    )
    fit = result["fit"]
    decomposition = fit["endpoint"]["free_to_endpoint_decomposition"]
    print(
        json.dumps(
            {
                "output": str(args.output),
                "unit_id": result["unit_id"],
                "source_fit_sha256": result["source_fit_sha256"],
                "success": fit["endpoint"]["success"],
                "status": fit["endpoint"]["status"],
                "fixed_minus_free_objective": decomposition["fixed_minus_free_objective"],
                "endpoint_minus_abrupt_objective": fit["abrupt_comparison"][
                    "endpoint_minus_abrupt_objective"
                ],
                "eligible_for_cohort": False,
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = ["fit_finite_endpoint", "run_endpoint"]
