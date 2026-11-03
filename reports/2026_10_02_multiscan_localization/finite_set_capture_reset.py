"""Grouped finite-set localization with capture-specific RX intercept resets."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from capture_reset_fit import (
    canonicalize_capture_jumps,
    capture_reset_model_penalty,
    initialize_from_child_fits,
)
from capture_reset_gn import apply_capture_offsets, refine_capture_reset_gauss_newton
from finite_set_fit import (
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-grouped-cohort-v1"
RUN_ID = "finite-set-capture-reset-v1"
SCHEMA = "finite-set-capture-reset/v1"
SUPPORTED_UNITS = ("DS10-D01", "DS11-D01")
RUNNER_NUMERICAL_DEPENDENCIES = (
    "capture_reset_fit.py",
    "capture_reset_gn.py",
    "coherent_fit.py",
)


def validate_group_capture_rx(data):
    """Require every finite-set group to have one capture and receiver geometry."""

    group = np.asarray(data.group)
    capture = np.asarray(data.capture_index, dtype=int)
    receiver = np.asarray(data.receiver, dtype=int)
    if group.ndim != 1 or capture.shape != group.shape or receiver.shape != group.shape:
        raise ValueError("group, capture_index, and receiver must align")
    if len(group) == 0:
        raise ValueError("grouped reset data must be nonempty")
    for value in np.unique(group):
        rows = group == value
        if len(np.unique(capture[rows])) != 1 or len(np.unique(receiver[rows])) != 1:
            raise ValueError(f"group {value!r} crosses capture or receiver identity")
    capture_count = len(data.child_sessions)
    if capture_count < 2 or set(np.unique(capture)) != set(range(capture_count)):
        raise ValueError("capture lineage must cover every child exactly")
    return {
        "group_count": int(len(np.unique(group))),
        "capture_count": capture_count,
        "groups_have_one_capture_and_receiver": True,
    }


def child_rx_only_seed(data, parent_parameters, child_fit_receipts):
    """Use child RX lines and jumps while preserving parent position and taus."""

    parent_parameters = np.asarray(parent_parameters, dtype=float)
    if parent_parameters.shape != (6 + len(data.numbers),) or np.any(
        ~np.isfinite(parent_parameters)
    ):
        raise ValueError("parent parameters do not match the union candidate bank")
    initialized = initialize_from_child_fits(data, child_fit_receipts)
    parameters = parent_parameters.copy()
    parameters[2:6] = np.asarray(initialized["parameters"], dtype=float)[2:6]
    if np.any(np.abs(parameters[[3, 5]]) > 50.0 + 1e-12):
        raise ValueError("child-derived common RX slope exceeds the frozen bound")
    jumps = canonicalize_capture_jumps(initialized["capture_jumps_hz"])
    return {
        "parameters": parameters,
        "capture_jumps_hz": jumps,
        "child_initializer": initialized,
        "position_and_tau_preserved": bool(
            np.array_equal(parameters[:2], parent_parameters[:2])
            and np.array_equal(parameters[6:], parent_parameters[6:])
        ),
        "policy": (
            "Parent position and all union-bank taus retained exactly; only shared RX line and "
            "capture jumps come from sealed child rough/RX initializers."
        ),
    }


def evaluate_reset_seed(
    data,
    parameters,
    capture_jumps_hz,
    satellites,
    likelihood,
    *,
    tau_sigma_s=1.0,
):
    """Evaluate the reset-model finite-set objective without optimization."""

    satellites = np.asarray(satellites, dtype=int)
    parameters = np.asarray(parameters, dtype=float)
    jumps = canonicalize_capture_jumps(capture_jumps_hz)
    plan = SharedPredictionPlan(data, satellites)
    predicted, visible, _ = plan.predict(parameters)
    shape = (len(data.times), len(satellites))
    predicted = apply_capture_offsets(data, predicted.reshape(shape), jumps, len(satellites))
    visible = np.asarray(visible).reshape(shape)
    result = likelihood.evaluate(
        predicted,
        visible,
        sigma_hz=200.0,
        satellite_weights=np.full(len(satellites), 1.0 / len(satellites)),
        background_mass=0.2,
    )
    prior = 0.5 * np.sum((parameters[6 + satellites] / tau_sigma_s) ** 2)
    return {
        "objective": float(-result["total_log_likelihood"] + prior),
        "group_count": int(len(result["group_values"])),
        "capture_jumps_hz": jumps,
    }


def retained_continuous_incumbent(source, nested, capture_count, reason):
    """Represent a nested continuous point honestly inside the reset model."""

    satellite_count = len(source["satellite_indices"])
    penalty = capture_reset_model_penalty(nested["group_count"], satellite_count, capture_count)
    return {
        "parameters": np.asarray(source["parameters"], dtype=float).copy(),
        "capture_jumps_hz": np.zeros((capture_count, 2)),
        "success": False,
        "message": reason,
        "status": "nonconverged",
        "convergence_reason": reason,
        "algorithm_version": "continuous-incumbent-in-reset-model/v1",
        "satellite_indices": np.asarray(source["satellite_indices"], dtype=int),
        "catalog_numbers": np.asarray(source["catalog_numbers"], dtype=int),
        "satellite_count": satellite_count,
        "objective": nested["objective"],
        "initial_objective": nested["objective"],
        "selection_score": nested["objective"] + penalty["total_penalty"],
        "model_penalty": penalty,
        "groups": nested["group_count"],
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
        "jump_bound_hz": float(1.0 / 4.4e-6 / 2),
        "continuous_incumbent_retained": True,
        "convergence_not_inherited_from_continuous_model": True,
    }


def fit_capture_reset_branches(
    data,
    parent_fit,
    child_fit_receipts,
    *,
    budget_s_per_bank=15.0,
    refiner=refine_capture_reset_gauss_newton,
):
    """Fit the parent's exact bank ladder under finite-set capture resets."""

    if not np.isfinite(budget_s_per_bank) or not 0 < budget_s_per_bank <= 15:
        raise ValueError("per-bank budget must lie in (0, 15]")
    geometry = validate_group_capture_rx(data)
    capture_count = geometry["capture_count"]
    full_bank = np.asarray(parent_fit["full_bank"], dtype=int)
    source_trials = parent_fit.get("trials")
    if full_bank.ndim != 1 or not len(full_bank) or not isinstance(source_trials, list):
        raise ValueError("parent fit lacks a finite-set bank ladder")
    banks = [tuple(trial.get("satellite_indices", ())) for trial in source_trials]
    if not source_trials or len(set(banks)) != len(banks) or tuple(full_bank) not in banks:
        raise ValueError("parent banks are empty, duplicated, or omit the full bank")
    trials = []
    attempts = []
    for source in source_trials:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        support = np.asarray(source.get("seed", {}).get("track_support"), dtype=float)
        invalid_support = np.any(~np.isfinite(support)) or np.any(support <= 0)
        if support.shape != satellites.shape or invalid_support:
            raise ValueError("parent trial lacks positive same-bank track support")
        parameters = np.asarray(source["parameters"], dtype=float)
        likelihood = build_likelihood_arms(
            data,
            len(satellites),
            len(full_bank),
        )["finite_set"]
        nested = evaluate_reset_seed(
            data,
            parameters,
            np.zeros((capture_count, 2)),
            satellites,
            likelihood,
        )
        if not np.isclose(nested["objective"], source["objective"], rtol=0, atol=1e-6):
            raise ValueError("zero-reset finite-set seed does not reproduce parent objective")
        child_seed = child_rx_only_seed(data, parameters, child_fit_receipts)
        child = evaluate_reset_seed(
            data,
            child_seed["parameters"],
            child_seed["capture_jumps_hz"],
            satellites,
            likelihood,
        )
        use_child = child["objective"] < nested["objective"]
        selected = child if use_child else nested
        initial_parameters = child_seed["parameters"] if use_child else parameters
        initial_jumps = (
            child_seed["capture_jumps_hz"] if use_child else np.zeros((capture_count, 2))
        )
        candidate = refiner(
            data,
            initial_parameters,
            initial_jumps,
            satellites,
            support,
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            slope_bound_hz_s=50.0,
            budget_s=float(budget_s_per_bank),
        )
        if not np.isclose(candidate["initial_objective"], selected["objective"], rtol=0, atol=1e-6):
            raise ValueError("reset GN does not reproduce the selected initializer")
        retain_source = candidate["objective"] > nested["objective"] + 1e-6
        if not retain_source and candidate["objective"] > selected["objective"] + 1e-6:
            raise ValueError("reset GN lost its selected initializer")
        trial = (
            retained_continuous_incumbent(
                source,
                nested,
                capture_count,
                "reset_candidate_worse_than_continuous_incumbent",
            )
            if retain_source
            else copy.deepcopy(candidate)
        )
        trial["source_continuous_objective"] = nested["objective"]
        trial["source_continuous_success"] = bool(source.get("success"))
        trial["initializer_selected"] = "child_rx_only" if use_child else "nested_zero_reset"
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": satellites,
                "satellite_count": len(satellites),
                "nested_zero_reset": nested,
                "child_rx_only": child,
                "child_seed_policy": child_seed["policy"],
                "selected_initializer": trial["initializer_selected"],
                "local_refinement": candidate,
                "continuous_incumbent_retained": retain_source,
            }
        )
    selection = select_trials(trials)
    return {
        "full_bank": full_bank,
        "trials": trials,
        "attempts": attempts,
        "selection": selection,
        "group_capture_rx_validation": geometry,
        "capture_count": capture_count,
        "parent_bank_order_preserved": True,
        "optimizer": "complete-data-fisher-capture-reset-gn/v1",
        "detection_probability_per_satellite": 0.8 / len(full_bank),
        "clutter_rate": 2.0,
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
        "scope": (
            "Exact sealed parent banks under grouped finite-set likelihood with two RX intercept "
            "resets per later capture. Each bank compares a nested zero-reset seed with one "
            "sealed child-RX seed under the same objective before reset-aware GN. Parent position "
            "and taus are preserved in the child seed. No timing profile or reference is used."
        ),
    }


def _find_unit(selection, unit_id):
    matches = [
        (dataset, unit)
        for dataset, population in selection["datasets"].items()
        for unit in population["units"]
        if unit["unit_id"] == unit_id
    ]
    if len(matches) != 1:
        raise ValueError("unit must appear exactly once in frozen selection")
    return matches[0]


def runner_numerical_dependency_paths(root=None):
    """Return the explicit numerical dependency closure added by this runner."""

    root = ROOT if root is None else Path(root)
    return tuple(root / name for name in RUNNER_NUMERICAL_DEPENDENCIES)


def audit_parent_source_hashes(source_hashes):
    """Require all parent sources except its unused orchestration module to match."""

    rows = []
    unexpected = []
    allowed_path = (ROOT / "finite_set_grouped_cohort.py").resolve()
    for path, expected in source_hashes.items():
        actual = digest(path)
        matches = actual == expected
        resolved = Path(path).resolve()
        allowed = not matches and resolved == allowed_path
        rows.append(
            {
                "path": str(resolved),
                "expected_sha256": expected,
                "current_sha256": actual,
                "matches": matches,
                "allowed_orchestration_drift": allowed,
                "drift_exception": ("legacy_parent_orchestration_not_reused" if allowed else None),
                "reused_by_new_numerical_fit": resolved != allowed_path,
            }
        )
        if not matches and not allowed:
            unexpected.append(str(Path(path).resolve()))
    if unexpected:
        raise RuntimeError(f"parent numerical provenance changed: {', '.join(unexpected)}")
    return rows


def validate_parent_binding(parent, unit, dataset, data, input_paths):
    """Validate the sealed parent fit, every inherited file, inputs, and geometry."""

    if (
        parent.get("schema") != "finite-set-grouped-cohort/v1"
        or parent.get("run_id") != SOURCE_RUN
        or parent.get("unit") != unit
        or parent.get("dataset") != dataset
        or parent.get("reference_read_before_seal") is not False
        or parent.get("evaluation_written") is not False
        or not parent.get("sealed_utc")
    ):
        raise ValueError("parent must be a sealed truth-free grouped finite-set fit")
    if parent.get("selection_sha256") != digest(ROOT / "selection.json"):
        raise ValueError("parent selection binding changed")
    source_hashes = parent.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("parent lacks source hashes")
    source_hash_audit = audit_parent_source_hashes(source_hashes)
    actual_inputs = snapshot_files(input_paths)
    expected_inputs = {path: source_hashes.get(path) for path in actual_inputs}
    if None in expected_inputs.values() or actual_inputs != expected_inputs:
        raise ValueError("parent loader inputs differ from sealed source hashes")
    actual_geometry = serializable(data.geometry_receipt)
    if actual_geometry != parent.get("fit", {}).get("grouped_geometry"):
        raise ValueError("parent grouped geometry differs from reconstructed data")
    if (
        tuple(data.child_sessions) != tuple(unit["session_ids"])
        or parent["fit"].get("capture_count") != unit["size"]
        or parent.get("grouped_row_count") != len(data.times)
    ):
        raise ValueError("parent capture lineage differs from reconstructed data")
    return {
        "source_hashes": dict(source_hashes),
        "source_hash_audit": source_hash_audit,
        "bound_input_hashes": actual_inputs,
        "geometry_receipt": actual_geometry,
    }


def validate_child_rough_provenance(receipt, child_path, single_unit, dataset):
    """Validate one coherent child RX initializer and its rough-fit authority."""

    session_id = single_unit["session_ids"][0]
    expected_inputs = {session_id: digest(ROOT / "scans" / session_id / "bundle.json")}
    if (
        receipt.get("run_id") != "coherent-v1"
        or receipt.get("stage") != "coherent"
        or receipt.get("unit") != single_unit
        or receipt.get("dataset") != dataset
        or receipt.get("selection_sha256") != digest(ROOT / "selection.json")
        or receipt.get("inputs") != expected_inputs
    ):
        raise ValueError("child coherent receipt has different unit or input provenance")
    source_hashes = receipt.get("source_hashes")
    if not isinstance(source_hashes, dict) or source_hashes.get("track_seed.py") != digest(
        ROOT / "track_seed.py"
    ):
        raise ValueError("child rough solver provenance changed")
    fit = receipt.get("fit", {})
    rough = fit.get("rough", {})
    rx_initial = np.asarray(fit.get("rx_initial"), dtype=float)
    if (
        rough.get("success") is not True
        or np.asarray(rough.get("position_km"), dtype=float).shape != (2,)
        or rx_initial.ndim != 1
        or len(rx_initial) < 6
        or np.any(~np.isfinite(rx_initial))
    ):
        raise ValueError("child lacks a successful rough/RX initializer")
    cached_digest = receipt.get("cached_rough_fit_sha256")
    cached_path = None
    if cached_digest is not None:
        cached_path = ROOT / "runs" / "rough-v1" / single_unit["unit_id"] / "fit.json"
        cached = json.loads(cached_path.read_text())
        if (
            digest(cached_path) != cached_digest
            or cached.get("stage") != "rough"
            or cached.get("unit") != single_unit
            or cached.get("dataset") != dataset
            or cached.get("inputs") != expected_inputs
            or cached.get("selection_sha256") != receipt["selection_sha256"]
            or cached.get("source_hashes", {}).get("track_seed.py")
            != source_hashes["track_seed.py"]
            or cached.get("fit") != rough
        ):
            raise ValueError("cached child rough fit does not reproduce coherent provenance")
    return {
        "session_id": session_id,
        "single_unit_id": single_unit["unit_id"],
        "coherent_fit_path": str(Path(child_path).resolve()),
        "coherent_fit_sha256": digest(child_path),
        "recorded_source_hashes": source_hashes,
        "input_hashes": expected_inputs,
        "cached_rough_fit_path": None if cached_path is None else str(cached_path.resolve()),
        "cached_rough_fit_sha256": cached_digest,
    }


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports

    if unit_id not in SUPPORTED_UNITS:
        raise ValueError(f"unit_id must be one of {SUPPORTED_UNITS}")
    output = ROOT / "runs" / RUN_ID / unit_id
    if output.exists():
        raise FileExistsError(output)
    started = time.monotonic()
    snapshot = None
    try:
        selection = json.loads((ROOT / "selection.json").read_text())
        dataset, unit = _find_unit(selection, unit_id)
        if unit["size"] != 2:
            raise ValueError("initial reset prototype requires a pair")
        parent_path = ROOT / "runs" / SOURCE_RUN / unit_id / "fit.json"
        parent = json.loads(parent_path.read_text())
        exports = ROOT / "runs" / "alias-family-cohort-v1"
        manifest_path = exports / "manifest.json"
        manifest_key = str(manifest_path.resolve())
        expected_manifest_sha256 = parent.get("source_hashes", {}).get(manifest_key)
        if expected_manifest_sha256 is None:
            raise ValueError("parent does not bind the alias-family manifest")
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            exports,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        parent_binding = validate_parent_binding(parent, unit, dataset, data, input_paths)
        single_by_session = {
            row["session_ids"][0]: row
            for row in selection["datasets"][dataset]["units"]
            if row["size"] == 1
        }
        child_receipts = {}
        child_provenance = []
        extra_paths = [parent_path, Path(__file__)]
        extra_paths.extend(runner_numerical_dependency_paths())
        for session_id in unit["session_ids"]:
            single = single_by_session.get(session_id)
            if single is None:
                raise ValueError("parent capture lacks a frozen child single")
            child_path = ROOT / "runs" / "coherent-v1" / single["unit_id"] / "fit.json"
            receipt = json.loads(child_path.read_text())
            provenance = validate_child_rough_provenance(
                receipt,
                child_path,
                single,
                dataset,
            )
            child_receipts[session_id] = receipt
            child_provenance.append(provenance)
            extra_paths.append(child_path)
            if provenance["cached_rough_fit_path"] is not None:
                extra_paths.append(Path(provenance["cached_rough_fit_path"]))
        paths = list(parent_binding["source_hashes"])
        paths.extend(extra_paths)
        paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        snapshot = snapshot_files(paths)
        fitted = fit_capture_reset_branches(
            data,
            parent["fit"],
            child_receipts,
            budget_s_per_bank=15.0,
        )
        assert_snapshot_unchanged(snapshot)
    except Exception as error:
        output.mkdir(parents=True, exist_ok=False)
        failure = {
            "schema": SCHEMA,
            "run_id": RUN_ID,
            "unit_id": unit_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_s": time.monotonic() - started,
            "source_hashes": snapshot,
            "reference_read_before_seal": False,
            "evaluation_written": False,
            "sealed": True,
            "sealed_utc": datetime.now(UTC).isoformat(),
        }
        with (output / "failure.json").open("x") as stream:
            json.dump(failure, stream, indent=2, allow_nan=False)
        raise
    result = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "unit": unit,
        "dataset": dataset,
        "source_run_id": SOURCE_RUN,
        "source_fit_sha256": digest(parent_path),
        "source_hashes": snapshot,
        "parent_source_hash_audit": parent_binding["source_hash_audit"],
        "bound_input_hashes": parent_binding["bound_input_hashes"],
        "geometry_receipt": parent_binding["geometry_receipt"],
        "child_rough_provenance": child_provenance,
        "limits": {"budget_s_per_bank": 15.0, "numerical_threads": 1},
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "fit": fitted,
        "elapsed_s": time.monotonic() - started,
        "sealed": True,
        "sealed_utc": datetime.now(UTC).isoformat(),
    }
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    with fit_path.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(fit_path), "sha256": digest(fit_path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id", choices=SUPPORTED_UNITS)
    arguments = parser.parse_args()
    print(json.dumps(run_unit(arguments.unit_id)))


__all__ = [
    "audit_parent_source_hashes",
    "child_rx_only_seed",
    "evaluate_reset_seed",
    "fit_capture_reset_branches",
    "retained_continuous_incumbent",
    "runner_numerical_dependency_paths",
    "run_unit",
    "validate_child_rough_provenance",
    "validate_group_capture_rx",
    "validate_parent_binding",
]
