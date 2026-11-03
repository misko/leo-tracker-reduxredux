"""Run one additional sealed timing-profile pass from a v1 incumbent."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_tau_profile_run import fit_profile_branches
from rough_smoke import serializable
from selection import ROOT

SOURCE_RUN = "finite-set-tau-profile-v1"
RUN_ID = "finite-set-tau-profile-v2"
SOURCE_SCHEMA = "finite-set-tau-profile/v1"
SCHEMA = "finite-set-tau-profile/v2"
SUPPORTED_UNITS = ("DS10-S01", "DS11-S02")


def validate_source_record(source, unit_id):
    """Require a complete, sealed, truth-free v1 timing-profile result."""

    if source.get("schema") != SOURCE_SCHEMA or source.get("run_id") != SOURCE_RUN:
        raise ValueError("source must be a v1 timing-profile fit")
    unit = source.get("unit")
    if not isinstance(unit, dict) or unit.get("unit_id") != unit_id:
        raise ValueError("source unit identity differs from requested unit")
    if source.get("dataset") != unit_id[:4]:
        raise ValueError("source dataset differs from requested unit")
    if (
        source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or not source.get("sealed_utc")
    ):
        raise ValueError("source must be sealed without reference or evaluation access")
    source_hashes = source.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("source lacks inherited file hashes")
    if any(
        not isinstance(path, str) or not isinstance(value, str) or len(value) != 64
        for path, value in source_hashes.items()
    ):
        raise ValueError("source file hashes are malformed")
    source_fit_sha256 = source.get("source_fit_sha256")
    if not isinstance(source_fit_sha256, str) or len(source_fit_sha256) != 64:
        raise ValueError("source grouped-cohort fit hash is malformed")
    fit = source.get("fit")
    if not isinstance(fit, dict):
        raise ValueError("source lacks fitted branches")
    trials = fit.get("trials")
    attempts = fit.get("attempts")
    full_bank = fit.get("full_bank")
    if (
        not isinstance(trials, list)
        or not trials
        or not isinstance(attempts, list)
        or len(attempts) != len(trials)
        or not isinstance(full_bank, list)
        or not full_bank
    ):
        raise ValueError("source branch ladder is incomplete")
    if (
        fit.get("all_timing_profiles_complete") is not True
        or fit.get("local_refinements_resolved") is not True
        or fit.get("selection", {}).get("selection_resolved") is not True
    ):
        raise ValueError("source timing profiles and refinements must be resolved")
    banks = []
    for trial, attempt in zip(trials, attempts, strict=True):
        bank = trial.get("satellite_indices")
        if not isinstance(bank, list) or not bank or trial.get("success") is not True:
            raise ValueError("every source bank must have a converged incumbent")
        if (
            attempt.get("satellite_indices") != bank
            or attempt.get("profile", {}).get("complete") is not True
            or attempt.get("local_refinement", {}).get("success") is not True
        ):
            raise ValueError("every source bank must have a complete profile and refinement")
        banks.append(tuple(bank))
    if len(set(banks)) != len(banks) or tuple(full_bank) not in banks:
        raise ValueError("source branch banks are duplicated or omit the full bank")
    return source


def assert_inherited_hashes_unchanged(source_hashes):
    """Verify every file sealed into the source run still has its recorded bytes."""

    assert_snapshot_unchanged(source_hashes)
    return dict(source_hashes)


def expected_bound_input_hashes(source):
    """Extract the exact loader inputs from the inherited source snapshot."""

    hashes = source["source_hashes"]
    unit = source["unit"]
    sessions = unit.get("session_ids")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("source unit lacks child sessions")
    export_directory = ROOT / "runs" / "alias-family-cohort-v1"
    expected_paths = [ROOT / "selection.json", export_directory / "manifest.json"]
    export_root = export_directory.resolve()
    for session in sessions:
        receipts = [
            Path(path)
            for path in hashes
            if Path(path).parent == export_root and session in Path(path).name
        ]
        if len(receipts) != 1:
            raise ValueError(f"source must bind one alias-family receipt for {session}")
        scan_root = ROOT / "scans" / session
        expected_paths.extend([receipts[0], scan_root / "bundle.json", scan_root / "bundle.npz"])
    if len(sessions) > 1:
        unit_root = ROOT / "units" / unit["unit_id"]
        expected_paths.extend([unit_root / "bundle.json", unit_root / "bundle.npz"])
    expected = {}
    for path in expected_paths:
        key = str(path.resolve())
        if key not in hashes:
            raise ValueError(f"source does not bind loader input {key}")
        expected[key] = hashes[key]
    return expected


def validate_bound_input_hashes(input_paths, expected_hashes):
    """Require loader-returned paths and bytes to equal the sealed input binding."""

    actual = snapshot_files(input_paths)
    if actual != expected_hashes:
        raise ValueError("reconstructed loader inputs differ from sealed source hashes")
    return actual


def validate_geometry_binding(source, geometry_receipt, *, source_path=None):
    """Match reconstructed grouped geometry to the source cohort geometry."""

    if source_path is None:
        source_root = ROOT / "runs" / "finite-set-grouped-cohort-v1"
        source_path = source_root / source["unit"]["unit_id"] / "fit.json"
    source_path = Path(source_path)
    key = str(source_path.resolve())
    if source["source_hashes"].get(key) != source.get("source_fit_sha256"):
        raise ValueError("source grouped-cohort fit digest is not inherited exactly")
    grouped_source = json.loads(source_path.read_text())
    expected = grouped_source.get("fit", {}).get("grouped_geometry")
    actual = serializable(geometry_receipt)
    if actual != expected:
        raise ValueError("reconstructed grouped geometry differs from sealed source")
    return actual


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports
    from finite_set_cavity import prepare_replacement_scorer
    from finite_set_grouped_cohort import EXPORT_SHA256, EXPORTS

    if unit_id not in SUPPORTED_UNITS:
        raise ValueError(f"unit_id must be one of {SUPPORTED_UNITS}")
    directory = ROOT / "runs" / RUN_ID / unit_id
    if directory.exists():
        raise FileExistsError(directory)
    source_path = ROOT / "runs" / SOURCE_RUN / unit_id / "fit.json"
    started = time.monotonic()
    source = None
    snapshot = None
    try:
        source = validate_source_record(json.loads(source_path.read_text()), unit_id)
        inherited_hashes = assert_inherited_hashes_unchanged(source["source_hashes"])
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            EXPORTS,
            expected_manifest_sha256=EXPORT_SHA256,
        )
        bound_input_hashes = validate_bound_input_hashes(
            input_paths,
            expected_bound_input_hashes(source),
        )
        geometry_receipt = validate_geometry_binding(source, data.geometry_receipt)
        snapshot = snapshot_files([*inherited_hashes, source_path, __file__])
        fitted = fit_profile_branches(
            data,
            source["fit"],
            cavity_factory=prepare_replacement_scorer,
        )
        assert_snapshot_unchanged(snapshot)
    except Exception as error:
        directory.mkdir(parents=True, exist_ok=False)
        failure = {
            "schema": SCHEMA,
            "run_id": RUN_ID,
            "unit_id": unit_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_s": time.monotonic() - started,
            "reference_read_before_seal": False,
            "evaluation_written": False,
        }
        if snapshot is not None:
            failure["source_hashes"] = snapshot
        with (directory / "failure.json").open("x") as stream:
            json.dump(failure, stream, indent=2, allow_nan=False)
        raise
    result = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "unit": source["unit"],
        "dataset": source["dataset"],
        "source_run_id": SOURCE_RUN,
        "source_fit_sha256": digest(source_path),
        "source_hashes": snapshot,
        "inherited_source_hashes": inherited_hashes,
        "bound_input_hashes": bound_input_hashes,
        "geometry_receipt": geometry_receipt,
        "continuation_profile_passes": 1,
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "fit": fitted,
        "elapsed_s": time.monotonic() - started,
        "sealed_utc": datetime.now(UTC).isoformat(),
        "scope": (
            "Exactly one additional complete timing-coordinate profile pass followed by the "
            "unchanged joint GN branch refiner for every sealed v1 bank. Source incumbents are "
            "retained by objective. No reference or evaluation artifact is read or written."
        ),
    }
    directory.mkdir(parents=True, exist_ok=False)
    output = directory / "fit.json"
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(output), "sha256": digest(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id", choices=SUPPORTED_UNITS)
    arguments = parser.parse_args()
    print(json.dumps(run_unit(arguments.unit_id)))
