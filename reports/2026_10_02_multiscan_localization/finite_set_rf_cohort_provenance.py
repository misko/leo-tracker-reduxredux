"""Corrected provenance envelope for the frozen direct RF cohort runner."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import finite_set_rf_cohort as core
import finite_set_tau_continue as tau_continue
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from rough_smoke import serializable

ROOT = core.ROOT
RUN_ID = "finite-set-rf-cohort-provenance-v1"
SCHEMA = "finite-set-rf-cohort-provenance/v1"
SUPPORTED_UNITS = core.SUPPORTED_UNITS


def legacy_receipt(unit_id):
    """Describe an existing provisional receipt without using it numerically."""

    directory = ROOT / "runs" / core.RUN_ID / unit_id
    matches = [path for name in ("fit.json", "failure.json") if (path := directory / name).exists()]
    if len(matches) > 1:
        raise ValueError("provisional run contains both fit and failure receipts")
    if not matches:
        return None
    path = matches[0]
    return {
        "path": str(path.resolve()),
        "sha256": digest(path),
        "receipt_name": path.name,
        "preserved_in_place": True,
        "used_as_fit_input": False,
    }


def prevalidation_snapshot_paths(source_path, source, unit_id):
    """Return the complete envelope paths before any source validation or fitting."""

    source_hashes = source.get("source_hashes")
    inherited_paths = list(source_hashes) if isinstance(source_hashes, dict) else []
    paths = [
        *inherited_paths,
        source_path,
        Path(__file__),
        Path(core.__file__),
        Path(tau_continue.__file__),
        *[ROOT / name for name in core.NUMERICAL_DEPENDENCIES],
        ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py",
    ]
    provisional = legacy_receipt(unit_id)
    if provisional is not None:
        paths.append(provisional["path"])
    return tuple(dict.fromkeys(str(Path(path).resolve()) for path in paths))


def snapshot_then_validate(
    source_path,
    source,
    unit_id,
    *,
    snapshotter=snapshot_files,
    validator=core.validate_source_record,
):
    """Snapshot the entire envelope before invoking the frozen source validator."""

    snapshot = snapshotter(prevalidation_snapshot_paths(source_path, source, unit_id))
    validated = validator(source, unit_id)
    return validated, snapshot


def invoke_core_fit(data, source_fit, *, fitter=core.fit_rf_cohort_branches):
    """Delegate once to the frozen numerical implementation without modification."""

    return fitter(data, source_fit)


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports

    if unit_id not in SUPPORTED_UNITS:
        raise ValueError("unit_id must be one of the 32 frozen singles")
    output = ROOT / "runs" / RUN_ID / unit_id
    if output.exists():
        raise FileExistsError(output)
    source_path = ROOT / "runs" / core.SOURCE_RUN / unit_id / "fit.json"
    started = time.monotonic()
    snapshot = None
    provisional = None
    try:
        source = json.loads(source_path.read_text())
        source, snapshot = snapshot_then_validate(source_path, source, unit_id)
        assert_snapshot_unchanged(source["source_hashes"])
        provisional = legacy_receipt(unit_id)
        expected_inputs = tau_continue.expected_bound_input_hashes(source)
        exports = ROOT / "runs" / "alias-family-cohort-v1"
        manifest_path = exports / "manifest.json"
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            exports,
            expected_manifest_sha256=expected_inputs[str(manifest_path.resolve())],
        )
        bound_inputs = tau_continue.validate_bound_input_hashes(
            input_paths,
            expected_inputs,
        )
        geometry = tau_continue.validate_geometry_binding(source, data.geometry_receipt)
        fitted = invoke_core_fit(data, source["fit"])
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
            "legacy_receipt_preserved": provisional,
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
        "unit": source["unit"],
        "dataset": source["dataset"],
        "source_run_id": core.SOURCE_RUN,
        "source_fit_sha256": digest(source_path),
        "source_hashes": snapshot,
        "inherited_source_hashes": source["source_hashes"],
        "bound_input_hashes": bound_inputs,
        "geometry_receipt": geometry,
        "legacy_receipt_preserved": provisional,
        "provenance_remediation": {
            "reason": "provisional runner omitted finite_set_tau_continue.py from its snapshot",
            "frozen_runner_path": str(Path(core.__file__).resolve()),
            "frozen_runner_sha256": digest(core.__file__),
            "validator_helper_path": str(Path(tau_continue.__file__).resolve()),
            "validator_helper_sha256": digest(tau_continue.__file__),
            "snapshot_completed_before_source_validation": True,
            "frozen_core_invocations": 1,
            "legacy_receipt_used_as_fit_input": False,
            "retroactive_provenance_claim": False,
        },
        "limits": {"budget_s_per_bank": 15.0, "numerical_threads": 1},
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": True,
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
    "invoke_core_fit",
    "legacy_receipt",
    "prevalidation_snapshot_paths",
    "run_unit",
    "snapshot_then_validate",
]
