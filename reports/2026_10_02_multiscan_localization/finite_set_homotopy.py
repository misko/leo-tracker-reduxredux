"""Oracle-only fixed-position homotopy for the paired finite-set pilot arms."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from finite_set_fit import GroupMedianGeometryData, build_likelihood_arms
from finite_set_fixed_position import (
    ARMS,
    _arm_group_arrays,
    _decompose_arm,
    _evaluate_state,
    freeze_selected_arms,
)
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from rough_smoke import load_module, serializable
from selection import ROOT


DEFAULT_NODE_COUNT = 8
DEFAULT_ARM_BUDGET_S = 20.0
DEFAULT_ABRUPT_RUN_ID = "finite-set-fixed-position-oracle-v1"
DEFAULT_RUN_ID = "finite-set-fixed-position-homotopy-v1"
NUMERICAL_DEPENDENCIES = (
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
        raise RuntimeError(f"homotopy provenance changed before seal: {', '.join(changed)}")


def _support_receipt(arm, state):
    groups = _arm_group_arrays(arm, state["result"])
    support = np.sum(groups["satellite_support"], axis=0)
    return {
        "satellite_support": support,
        "total_signal_support": float(np.sum(support)),
        "total_null": float(np.sum(groups["null"])),
        "null_semantics": groups["null_semantics"],
        "group_count": int(len(groups["group_values"])),
        "position_gradient": state["full_gradient"][:2],
        "position_gradient_norm": float(np.linalg.norm(state["full_gradient"][:2])),
        "total_log_likelihood": state["total_log_likelihood"],
        "tau_prior": state["tau_prior"],
        "objective": state["objective"],
    }


def _failed_node(index, fraction, position, allocation, remaining, warm_source, error):
    return {
        "node_index": index,
        "fraction_from_free_to_known": fraction,
        "position_km": position,
        "attempted": True,
        "fit_returned": False,
        "success": False,
        "status": "failed",
        "convergence_reason": "exception",
        "error": f"{type(error).__name__}: {error}",
        "allocated_fit_budget_s": allocation,
        "remaining_arm_deadline_before_node_s": remaining,
        "warm_start_source": warm_source,
    }


def _unattempted_node(index, fraction, position, remaining, warm_source):
    return {
        "node_index": index,
        "fraction_from_free_to_known": fraction,
        "position_km": position,
        "attempted": False,
        "fit_returned": False,
        "success": False,
        "status": "limit_reached",
        "convergence_reason": "shared_arm_deadline_exhausted_before_node",
        "error": None,
        "allocated_fit_budget_s": 0.0,
        "remaining_arm_deadline_before_node_s": max(0.0, remaining),
        "warm_start_source": warm_source,
    }


def fit_fixed_position_homotopy(
    data,
    source,
    known_position_km,
    *,
    node_count=DEFAULT_NODE_COUNT,
    total_budget_s_per_arm=DEFAULT_ARM_BUDGET_S,
    refiner=refine_gauss_newton,
    arm_builder=build_likelihood_arms,
    plan_factory=SharedPredictionPlan,
    clock=time.monotonic,
):
    """Continue nuisance fits through fixed nodes from each free leader to truth.

    This function accepts a supplied endpoint but never reads reference data and
    never runs or seeds a free-position fit.
    """

    if not isinstance(node_count, (int, np.integer)) or node_count != 8:
        raise ValueError("node_count must remain frozen at 8")
    if (
        not np.isfinite(total_budget_s_per_arm)
        or not 0 < total_budget_s_per_arm <= DEFAULT_ARM_BUDGET_S
    ):
        raise ValueError("total_budget_s_per_arm must lie in (0, 20]")
    known_position_km = np.asarray(known_position_km, dtype=float)
    if known_position_km.shape != (2,) or np.any(~np.isfinite(known_position_km)):
        raise ValueError("known_position_km must contain one finite east/north pair")

    geometry = data if isinstance(data, GroupMedianGeometryData) else GroupMedianGeometryData(data)
    full_bank, frozen = freeze_selected_arms(source, len(geometry.numbers))
    arm_results = {}
    for arm in ARMS:
        selected = frozen[arm]
        satellites = selected["satellites"]
        likelihood = arm_builder(geometry, len(satellites), len(full_bank))[arm]
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
            raise ValueError(f"{arm} sealed free objective does not reproduce")

        free_position = selected["parameters"][:2].copy()
        arm_started = clock()
        deadline = arm_started + float(total_budget_s_per_arm)
        warm_parameters = selected["parameters"].copy()
        warm_source = "sealed_v2_free_leader_nuisance"
        nodes = []
        endpoint_state = None
        endpoint_fit = None
        for node_offset in range(node_count):
            node_index = node_offset + 1
            fraction = node_index / node_count
            position = free_position + fraction * (known_position_km - free_position)
            remaining_nodes = node_count - node_offset
            remaining = deadline - clock()
            if remaining <= 0:
                nodes.append(
                    _unattempted_node(
                        node_index, fraction, position.copy(), remaining, warm_source
                    )
                )
                continue
            allocation = remaining / remaining_nodes
            node_started = clock()
            try:
                fitted = refiner(
                    geometry,
                    warm_parameters.copy(),
                    satellites,
                    np.ones(len(satellites)),
                    likelihood,
                    sigma_hz=200.0,
                    tau_sigma_s=1.0,
                    tau_bound_s=3.0,
                    slope_bound=50.0,
                    budget_s=float(allocation),
                    fixed_position_km=position.copy(),
                )
                parameters = np.asarray(fitted["parameters"], dtype=float)
                if not np.array_equal(parameters[:2], position):
                    raise AssertionError("homotopy node moved its fixed position")
                if not np.array_equal(
                    np.asarray(fitted["satellite_indices"], dtype=int), satellites
                ):
                    raise AssertionError("homotopy node changed its frozen bank")
                state = _evaluate_state(
                    geometry,
                    parameters,
                    satellites,
                    likelihood,
                    sigma_hz=200.0,
                    tau_sigma_s=1.0,
                    plan_factory=plan_factory,
                )
                if not np.isclose(state["objective"], fitted["objective"], rtol=1e-9, atol=1e-6):
                    raise ValueError("homotopy node objective does not reproduce")
                node_finished = clock()
                node = {
                    "node_index": node_index,
                    "fraction_from_free_to_known": fraction,
                    "position_km": position.copy(),
                    "attempted": True,
                    "fit_returned": True,
                    "success": bool(fitted["success"]),
                    "status": str(fitted["status"]),
                    "convergence_reason": str(
                        fitted.get("convergence_reason", fitted.get("message", ""))
                    ),
                    "error": None,
                    "allocated_fit_budget_s": float(allocation),
                    "remaining_arm_deadline_before_node_s": float(remaining),
                    "elapsed_including_receipt_evaluation_s": float(node_finished - node_started),
                    "remaining_arm_deadline_after_node_s": float(deadline - node_finished),
                    "cooperative_deadline_overrun_s": float(max(0.0, node_finished - deadline)),
                    "warm_start_source": warm_source,
                    "parameters": parameters.copy(),
                    "optimizer": fitted,
                    "support": _support_receipt(arm, state),
                }
                nodes.append(node)
                if np.all(np.isfinite(parameters)):
                    warm_parameters = parameters.copy()
                    warm_source = f"fixed_node_{node_index}_best_finite_nuisance"
                if node_index == node_count:
                    endpoint_state = state
                    endpoint_fit = fitted
            except Exception as error:
                node_finished = clock()
                failed = _failed_node(
                    node_index,
                    fraction,
                    position.copy(),
                    float(allocation),
                    float(remaining),
                    warm_source,
                    error,
                )
                failed["elapsed_including_receipt_evaluation_s"] = float(
                    node_finished - node_started
                )
                failed["remaining_arm_deadline_after_node_s"] = float(
                    deadline - node_finished
                )
                failed["cooperative_deadline_overrun_s"] = float(
                    max(0.0, node_finished - deadline)
                )
                nodes.append(failed)

        arm_finished = clock()
        if len(nodes) != node_count:
            raise AssertionError("homotopy did not preserve all fixed nodes")
        endpoint = None
        if endpoint_state is not None:
            endpoint = {
                "fit": endpoint_fit,
                "support": _support_receipt(arm, endpoint_state),
                "free_to_endpoint_decomposition": _decompose_arm(
                    geometry, arm, satellites, free, endpoint_state
                ),
            }
        arm_results[arm] = {
            "selected_bank": satellites.copy(),
            "selected_catalog_numbers": np.asarray(geometry.numbers)[satellites],
            "source_free": {
                "parameters": selected["parameters"],
                "objective": free["objective"],
                "success": selected["success"],
                "status": selected["status"],
                "convergence_reason": selected["convergence_reason"],
                "selection_resolved": selected["selection_resolved"],
                "support": _support_receipt(arm, free),
            },
            "nodes": nodes,
            "endpoint": endpoint,
            "all_nodes_represented": len(nodes) == node_count,
            "attempted_node_count": int(sum(node["attempted"] for node in nodes)),
            "returned_node_count": int(sum(node["fit_returned"] for node in nodes)),
            "converged_node_count": int(sum(node["success"] for node in nodes)),
            "arm_elapsed_s": float(arm_finished - arm_started),
            "shared_arm_deadline_s": float(total_budget_s_per_arm),
            "cooperative_deadline_overrun_s": float(max(0.0, arm_finished - deadline)),
        }

    return {
        "known_position_km": known_position_km.copy(),
        "full_bank": full_bank,
        "node_fractions": np.arange(1, node_count + 1, dtype=float) / node_count,
        "arms": arm_results,
        "free_fit_calls": 0,
        "position_fixed_at_every_attempted_node": True,
        "same_bank_within_each_arm": True,
        "cross_arm_absolute_nll_comparisons": False,
        "total_budget_s_per_arm": float(total_budget_s_per_arm),
        "maximum_two_arm_fit_budget_s": float(2 * total_budget_s_per_arm),
        "deadline_semantics": (
            "Cooperative shared monotonic deadline per arm. Before each node, remaining wall time "
            "is divided by remaining nodes and supplied as that node's fit budget. Final receipt "
            "evaluation and cooperative optimizer return can overrun; every overrun is recorded."
        ),
        "geometry": geometry.geometry_receipt,
    }


def _abrupt_endpoint_comparison(arm, homotopy, abrupt):
    endpoint = homotopy["arms"][arm]["endpoint"]
    abrupt_arm = abrupt["fit"]["arms"][arm]
    abrupt_fixed = abrupt_arm["fixed_reference"]
    if not np.array_equal(
        np.asarray(homotopy["arms"][arm]["selected_bank"], dtype=int),
        np.asarray(abrupt_arm["selected_bank"], dtype=int),
    ):
        raise ValueError(f"{arm} abrupt diagnostic used a different bank")
    if endpoint is None:
        return {
            "endpoint_returned": False,
            "abrupt_status": abrupt_fixed["status"],
            "abrupt_success": abrupt_fixed["success"],
        }
    endpoint_fit = endpoint["fit"]
    abrupt_support = np.asarray(abrupt_fixed["satellite_support"], dtype=float)
    endpoint_support = np.asarray(endpoint["support"]["satellite_support"], dtype=float)
    return {
        "endpoint_returned": True,
        "same_known_position": bool(
            np.array_equal(
                np.asarray(endpoint_fit["fixed_position_km"], dtype=float),
                np.asarray(abrupt["oracle_position_km"], dtype=float),
            )
        ),
        "homotopy_status": endpoint_fit["status"],
        "homotopy_success": endpoint_fit["success"],
        "abrupt_status": abrupt_fixed["status"],
        "abrupt_success": abrupt_fixed["success"],
        "homotopy_objective": float(endpoint_fit["objective"]),
        "abrupt_objective": float(abrupt_fixed["objective"]),
        "homotopy_minus_abrupt_objective": float(
            endpoint_fit["objective"] - abrupt_fixed["objective"]
        ),
        "homotopy_total_signal_support": float(np.sum(endpoint_support)),
        "abrupt_total_signal_support": float(np.sum(abrupt_support)),
        "homotopy_minus_abrupt_satellite_support": endpoint_support - abrupt_support,
    }


def run_oracle_homotopy(
    source_fit_path,
    abrupt_diagnostic_path,
    output_path,
    *,
    total_budget_s_per_arm=DEFAULT_ARM_BUDGET_S,
):
    """Run the fixed-node oracle continuation after source and endpoint sealing."""

    source_fit_path = Path(source_fit_path)
    abrupt_diagnostic_path = Path(abrupt_diagnostic_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    source_sha256 = _digest(source_fit_path)
    source = json.loads(source_fit_path.read_text())
    unit = source["unit"]
    unit_id = unit["unit_id"]
    if unit_id not in {"DS10-S01", "DS11-S02"} or unit.get("size") != 1:
        raise ValueError("homotopy is restricted to the two finite-set single pilots")

    full_bank, frozen = freeze_selected_arms(source, 64)
    frozen_before_oracle_read = {
        arm: {
            "satellites": frozen[arm]["satellites"].copy(),
            "parameters_sha256": frozen[arm]["parameters_sha256"],
        }
        for arm in ARMS
    }
    abrupt_sha256 = _digest(abrupt_diagnostic_path)
    abrupt = json.loads(abrupt_diagnostic_path.read_text())
    if (
        abrupt.get("oracle") is not True
        or abrupt.get("eligible_for_cohort") is not False
        or abrupt.get("unit_id") != unit_id
        or abrupt.get("source_fit_sha256") != source_sha256
    ):
        raise ValueError("abrupt oracle diagnostic does not bind the sealed source")
    known_position = np.asarray(abrupt["oracle_position_km"], dtype=float)
    if known_position.shape != (2,) or np.any(~np.isfinite(known_position)):
        raise ValueError("abrupt oracle position is invalid")
    if not np.array_equal(full_bank, np.asarray(source["fit"]["full_bank"], dtype=int)):
        raise AssertionError("source full bank changed after oracle read")
    for arm in ARMS:
        current = freeze_selected_arms(source, 64)[1][arm]
        if (
            not np.array_equal(current["satellites"], frozen_before_oracle_read[arm]["satellites"])
            or current["parameters_sha256"]
            != frozen_before_oracle_read[arm]["parameters_sha256"]
        ):
            raise AssertionError("source selection changed after oracle read")

    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    bundle = load_module(f"finite_set_homotopy_bundle_{unit_id}", bundle_path)
    session_id = unit["session_ids"][0]
    bundle_directory = ROOT / "scans" / session_id
    data = bundle.Data(bundle_directory)
    source_paths = [ROOT / name for name in NUMERICAL_DEPENDENCIES] + [bundle_path]
    source_snapshot = _snapshot(source_paths)
    artifact_paths = [
        source_fit_path,
        source_fit_path.with_name("evaluation.json"),
        abrupt_diagnostic_path,
        bundle_directory / "bundle.json",
        bundle_directory / "bundle.npz",
    ]
    artifact_snapshot = _snapshot(artifact_paths)
    started = time.monotonic()
    fitted = fit_fixed_position_homotopy(
        data,
        source,
        known_position,
        total_budget_s_per_arm=total_budget_s_per_arm,
    )
    comparisons = {
        arm: _abrupt_endpoint_comparison(arm, fitted, abrupt) for arm in ARMS
    }
    _assert_snapshot(source_snapshot)
    _assert_snapshot(artifact_snapshot)
    payload = {
        "schema": "finite-set-fixed-position-homotopy-oracle/v1",
        "generated_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "oracle": True,
        "eligible_for_cohort": False,
        "unit_id": unit_id,
        "run_id": DEFAULT_RUN_ID,
        "source_fit": str(source_fit_path),
        "source_fit_sha256": source_sha256,
        "abrupt_diagnostic": str(abrupt_diagnostic_path),
        "abrupt_diagnostic_sha256": abrupt_sha256,
        "source_selections_frozen_before_oracle_read": frozen_before_oracle_read,
        "source_hashes_prefit": source_snapshot,
        "bound_artifact_hashes_prefit": artifact_snapshot,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "known_position_km": known_position,
        "fit": fitted,
        "abrupt_endpoint_comparison": comparisons,
        "elapsed_s": time.monotonic() - started,
        "free_fits_run": False,
        "cross_arm_absolute_nll_comparisons": False,
        "scope": (
            "Explicit oracle-only fixed-position continuation. Each arm retains its sealed v2 "
            "score-leader bank and begins from that leader's nuisance state. Eight predetermined "
            "fixed nodes run from the sealed free position toward the known position; only a fixed "
            "node may warm the next fixed node. No result seeds a free fit, no node is selected by "
            "reference error, and arm likelihood values are never compared across sample spaces. "
            "The endpoint remains a bounded local fit and is not claimed globally optimal when "
            "unresolved."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serializable(payload), indent=2) + "\n")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--source-fit", required=True, type=Path)
    parser.add_argument("--abrupt-diagnostic", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--total-budget-s-per-arm", type=float, default=DEFAULT_ARM_BUDGET_S)
    args = parser.parse_args()
    if not args.oracle:
        parser.error("--oracle is required because this command uses a known-position endpoint")
    if not 0 < args.total_budget_s_per_arm <= DEFAULT_ARM_BUDGET_S:
        parser.error("total-budget-s-per-arm must lie in (0, 20]")
    result = run_oracle_homotopy(
        args.source_fit,
        args.abrupt_diagnostic,
        args.output,
        total_budget_s_per_arm=args.total_budget_s_per_arm,
    )
    summary = {
        "output": str(args.output),
        "unit_id": result["unit_id"],
        "source_fit_sha256": result["source_fit_sha256"],
        "elapsed_s": result["elapsed_s"],
        "eligible_for_cohort": False,
        "arms": {},
    }
    for arm in ARMS:
        fit = result["fit"]["arms"][arm]
        comparison = result["abrupt_endpoint_comparison"][arm]
        summary["arms"][arm] = {
            "attempted_nodes": fit["attempted_node_count"],
            "converged_nodes": fit["converged_node_count"],
            "deadline_overrun_s": fit["cooperative_deadline_overrun_s"],
            "endpoint_returned": comparison["endpoint_returned"],
            "homotopy_minus_abrupt_objective": comparison.get(
                "homotopy_minus_abrupt_objective"
            ),
        }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()


__all__ = ["fit_fixed_position_homotopy", "run_oracle_homotopy"]
