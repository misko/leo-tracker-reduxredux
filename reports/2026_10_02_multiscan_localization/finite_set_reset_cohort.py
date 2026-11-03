"""Truth-free frozen reset-multistart expansion across all D/Q cohort units."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN_ID = "finite-set-reset-cohort-v1"
SCHEMA = "finite-set-reset-cohort/v1"
STANDARD_PARENT_RUN = "finite-set-grouped-cohort-v1"
LEGACY_RETRY_PARENT_RUN = "finite-set-grouped-cohort-legacy-retry-v1"
ALIAS_EXPORT_RUN = "alias-family-cohort-v1"
SUPPORTED_UNITS = tuple(
    f"{dataset}-{kind}{index:02d}"
    for dataset in ("DS10", "DS11")
    for kind, count in (("D", 8), ("Q", 4))
    for index in range(1, count + 1)
)
NUMERICAL_DEPENDENCIES = (
    "alias_family_joint.py",
    "capture_reset_fit.py",
    "capture_reset_gn.py",
    "coherent_fit.py",
    "finite_set_capture_reset.py",
    "finite_set_fit.py",
    "finite_set_grouped_cohort.py",
    "finite_set_likelihood.py",
    "finite_set_reset_multistart.py",
    "gauss_newton.py",
    "grouped_likelihood.py",
    "joint_inputs.py",
    "prediction_jacobian.py",
    "prediction_plan.py",
    "profile_seed.py",
    "rough_smoke.py",
    "selection.py",
    "staged_fit.py",
    "track_likelihood.py",
    "track_seed.py",
)


def _digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _snapshot_files(paths):
    snapshot = {}
    for path in paths:
        key = str(Path(path).resolve())
        if key in snapshot:
            continue
        snapshot[key] = _digest(key)
    return snapshot


def _assert_snapshot_unchanged(snapshot):
    changed = [path for path, expected in snapshot.items() if _digest(path) != expected]
    if changed:
        raise RuntimeError(f"fitting provenance changed before seal: {', '.join(changed)}")


def expected_parent_run(unit_id):
    if unit_id not in SUPPORTED_UNITS:
        raise ValueError("unit must be one of the frozen DS10/DS11 D/Q units")
    if unit_id == "DS10-Q01":
        return LEGACY_RETRY_PARENT_RUN
    return STANDARD_PARENT_RUN


def validate_parent_identity(parent, unit_id):
    """Validate the one declared parent identity and adapt it for the frozen validator."""

    expected_run = expected_parent_run(unit_id)
    if (
        parent.get("schema") != "finite-set-grouped-cohort/v1"
        or parent.get("run_id") != expected_run
        or parent.get("unit", {}).get("unit_id") != unit_id
    ):
        raise ValueError("grouped parent identity differs from the declared cohort source")
    normalized = copy.deepcopy(parent)
    normalized["run_id"] = STANDARD_PARENT_RUN
    return normalized, {
        "run_id": expected_run,
        "legacy_retry_parent": expected_run == LEGACY_RETRY_PARENT_RUN,
        "validator_run_id_normalization": (
            "legacy_retry_to_standard_schema_identity"
            if expected_run == LEGACY_RETRY_PARENT_RUN
            else "none"
        ),
    }


def validate_unit_shape(unit_id, unit):
    expected_size = 2 if unit_id[5] == "D" else 4
    sessions = unit.get("session_ids")
    if (
        unit.get("unit_id") != unit_id
        or unit.get("size") != expected_size
        or not isinstance(sessions, list)
        or len(sessions) != expected_size
        or len(set(sessions)) != expected_size
    ):
        raise ValueError("selected D/Q unit has inconsistent capture geometry")
    return expected_size


def _raw_selected_unit(selection, unit_id):
    matches = [
        (dataset, unit)
        for dataset, population in selection.get("datasets", {}).items()
        for unit in population.get("units", ())
        if unit.get("unit_id") == unit_id
    ]
    if len(matches) != 1:
        raise ValueError("unit must appear exactly once in frozen selection")
    return matches[0]


def _child_units(selection, dataset, sessions):
    singles = {
        unit["session_ids"][0]: unit
        for unit in selection["datasets"][dataset]["units"]
        if unit.get("size") == 1 and len(unit.get("session_ids", ())) == 1
    }
    children = []
    for session in sessions:
        if session not in singles:
            raise ValueError("parent capture lacks a frozen child single")
        children.append(singles[session])
    return children


def numerical_dependency_paths(root=ROOT):
    root = Path(root)
    paths = [root / name for name in NUMERICAL_DEPENDENCIES]
    paths.append(root.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    return tuple(paths)


def source_paths(root, selection_path, parent_path, parent, child_units):
    """Return the complete input, validator, and numerical closure before validation."""

    root = Path(root)
    paths = [Path(__file__), selection_path, parent_path]
    paths.extend(numerical_dependency_paths(root))
    source_hashes = parent.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("grouped parent lacks source hashes")
    paths.extend(Path(path) for path in source_hashes)
    for child in child_units:
        unit_id = child["unit_id"]
        paths.append(root / "runs" / "coherent-v1" / unit_id / "fit.json")
        paths.append(root / "runs" / "rough-v1" / unit_id / "fit.json")
    return tuple(dict.fromkeys(Path(path).resolve() for path in paths))


def fit_with_frozen_core(data, parent, child_receipts, *, fitter=None):
    """Call the frozen two-branch, 15-second-per-branch numerical core unchanged."""

    if fitter is None:
        from finite_set_reset_multistart import fit_reset_multistart_branches

        fitter = fit_reset_multistart_branches
    return fitter(data, parent["fit"], child_receipts)


def run_unit(unit_id):
    if unit_id not in SUPPORTED_UNITS:
        raise ValueError("unit must be one of the frozen DS10/DS11 D/Q units")
    parent_run = expected_parent_run(unit_id)
    output = ROOT / "runs" / RUN_ID / unit_id
    if output.exists():
        raise FileExistsError(output)
    selection_path = ROOT / "selection.json"
    parent_path = ROOT / "runs" / parent_run / unit_id / "fit.json"
    started = time.monotonic()
    snapshot = None
    try:
        preliminary = _snapshot_files((Path(__file__), selection_path, parent_path))
        selection = json.loads(selection_path.read_text())
        parent = json.loads(parent_path.read_text())
        raw_dataset, raw_unit = _raw_selected_unit(selection, unit_id)
        raw_children = _child_units(selection, raw_dataset, raw_unit["session_ids"])
        paths = source_paths(ROOT, selection_path, parent_path, parent, raw_children)
        snapshot = _snapshot_files(paths)
        if any(snapshot.get(path) != value for path, value in preliminary.items()):
            raise RuntimeError("selection or parent changed while assembling provenance")

        from alias_family_joint import load_unit_with_family_exports
        from finite_set_capture_reset import (
            _find_unit,
            validate_child_rough_provenance,
            validate_parent_binding,
        )
        from rough_smoke import serializable

        dataset, unit = _find_unit(selection, unit_id)
        if dataset != raw_dataset or unit != raw_unit:
            raise ValueError("validated selection differs from snapshotted unit")
        validate_unit_shape(unit_id, unit)
        normalized_parent, parent_identity = validate_parent_identity(parent, unit_id)
        exports = ROOT / "runs" / ALIAS_EXPORT_RUN
        manifest_path = exports / "manifest.json"
        manifest_key = str(manifest_path.resolve())
        expected_manifest = parent.get("source_hashes", {}).get(manifest_key)
        if expected_manifest is None:
            raise ValueError("grouped parent does not bind the alias-family manifest")
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            exports,
            expected_manifest_sha256=expected_manifest,
        )
        unbound_paths = [
            str(Path(path).resolve())
            for path in input_paths
            if str(Path(path).resolve()) not in snapshot
        ]
        if unbound_paths:
            raise ValueError(f"loader used unsnapshotted inputs: {', '.join(unbound_paths)}")
        parent_binding = validate_parent_binding(
            normalized_parent,
            unit,
            dataset,
            data,
            input_paths,
        )
        children = _child_units(selection, dataset, unit["session_ids"])
        child_receipts = {}
        child_provenance = []
        for child in children:
            session_id = child["session_ids"][0]
            child_path = ROOT / "runs" / "coherent-v1" / child["unit_id"] / "fit.json"
            receipt = json.loads(child_path.read_text())
            provenance = validate_child_rough_provenance(
                receipt,
                child_path,
                child,
                dataset,
            )
            child_receipts[session_id] = receipt
            child_provenance.append(provenance)
        fitted = fit_with_frozen_core(data, parent, child_receipts)
        _assert_snapshot_unchanged(snapshot)
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
        "source_run_id": parent_run,
        "source_fit_sha256": _digest(parent_path),
        "parent_identity": parent_identity,
        "source_hashes": snapshot,
        "numerical_closure": {
            str(path.resolve()): snapshot[str(path.resolve())]
            for path in numerical_dependency_paths()
        },
        "inherited_source_hashes": parent_binding["source_hashes"],
        "source_hash_audit": parent_binding["source_hash_audit"],
        "bound_input_hashes": parent_binding["bound_input_hashes"],
        "geometry_receipt": parent_binding["geometry_receipt"],
        "child_provenance": child_provenance,
        "limits": {
            "budget_s_per_refinement": 15.0,
            "refinements_per_bank": 2,
            "numerical_threads": 1,
        },
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "fit": fitted,
        "elapsed_s": time.monotonic() - started,
        "sealed": True,
        "sealed_utc": datetime.now(UTC).isoformat(),
        "scope": (
            "Truth-free all-data D/Q expansion of the frozen reset-multistart numerical core. "
            "Every parent bank receives the unchanged two independent 15-second branches; "
            "child rough seeds and grouped input geometry remain source-bound."
        ),
    }
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    with fit_path.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(fit_path), "sha256": _digest(fit_path)}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", required=True, choices=SUPPORTED_UNITS)
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = parse_args()
    print(json.dumps(run_unit(arguments.unit)))


__all__ = [
    "SUPPORTED_UNITS",
    "expected_parent_run",
    "fit_with_frozen_core",
    "numerical_dependency_paths",
    "parse_args",
    "run_unit",
    "source_paths",
    "validate_parent_identity",
    "validate_unit_shape",
]
