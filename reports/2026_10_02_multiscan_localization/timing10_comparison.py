"""Run the frozen all-56 timing10 versus grouped-profile comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
PROTOCOL = ROOT / "timing10-comparison-protocol-v1.json"
RUNS = {"legacy": "legacy-timing10-cohort-v1", "grouped": "grouped-timing-profile-joint-v1"}
DEPENDENCIES = (
    "finite_set_capture_reset.py", "finite_set_tau_continue.py",
    "finite_set_tau_profile_run.py", "finite_set_tau_profile.py", "finite_set_cavity.py",
    "finite_set_fit.py", "finite_set_likelihood.py", "alias_family_joint.py",
    "prediction_plan.py", "prediction_jacobian.py", "gauss_newton.py", "joint_inputs.py",
    "staged_fit.py", "rough_smoke.py", "grouped_likelihood.py", "track_likelihood.py",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def units():
    selection = json.loads((ROOT / "selection.json").read_text())
    rows = [(dataset, unit) for dataset, population in selection["datasets"].items()
            for unit in population["units"]]
    expected = {(dataset, size): count for dataset in ("DS10", "DS11")
                for size, count in ((1, 16), (2, 8), (4, 4))}
    observed = {key: sum(dataset == key[0] and unit["size"] == key[1]
                        for dataset, unit in rows) for key in expected}
    if observed != expected or len(rows) != 56:
        raise ValueError("comparison requires the complete frozen 56-unit cohort")
    return rows


def parent_path(unit_id):
    run_id = ("finite-set-grouped-cohort-legacy-retry-v1" if unit_id == "DS10-Q01"
              else "finite-set-grouped-cohort-v1")
    return ROOT / "runs" / run_id / unit_id / "fit.json"


def initial_parameters(coherent, candidate_count):
    initial = np.asarray(coherent["fit"]["rx_initial"], dtype=float).copy()
    rough = coherent["fit"]["rough"]
    if (
        rough.get("success") is not True or initial.shape != (6 + candidate_count,)
        or np.any(~np.isfinite(initial)) or np.any(np.abs(initial[[3, 5]]) > 50 + 1e-9)
        or not np.array_equal(initial[:2], np.asarray(rough["position_km"]))
        or np.any(np.abs(initial[:2]) > 200)
    ):
        raise ValueError("shared track/RX initializer is malformed or outside declared bounds")
    initial[6:] = 0
    return initial


def prepare(unit_id, arm):
    if arm not in RUNS:
        raise ValueError("unknown comparison arm")
    protocol = json.loads(PROTOCOL.read_text())
    if digest(ROOT / "selection.json") != protocol["selection_sha256"]:
        raise ValueError("frozen cohort selection changed")
    matched = [(dataset, unit) for dataset, unit in units() if unit["unit_id"] == unit_id]
    if len(matched) != 1:
        raise ValueError("unit is outside frozen cohort")
    dataset, unit = matched[0]
    if arm == "grouped" and unit["size"] == 1:
        raise ValueError("reuse existing sealed single timing-profile fits; do not rerun")
    grouped_path = parent_path(unit_id)
    coherent_path = ROOT / "runs/coherent-v1" / unit_id / "fit.json"
    grouped_bytes, coherent_bytes = grouped_path.read_bytes(), coherent_path.read_bytes()
    grouped, coherent = json.loads(grouped_bytes), json.loads(coherent_bytes)
    paths = [Path(__file__), PROTOCOL, ROOT / "selection.json", grouped_path, coherent_path,
             *map(Path, grouped["source_hashes"]), *(ROOT / name for name in DEPENDENCIES)]
    if arm == "legacy":
        paths.append(ROOT / "legacy_timing10_fit.py")
    paths = list(dict.fromkeys(str(path.resolve()) for path in paths))
    snapshot = {path: digest(path) for path in paths}
    if (snapshot[str(grouped_path)] != hashlib.sha256(grouped_bytes).hexdigest()
            or snapshot[str(coherent_path)] != hashlib.sha256(coherent_bytes).hexdigest()):
        raise RuntimeError("source receipt changed before validation")
    from alias_family_joint import load_unit_with_family_exports
    from finite_set_capture_reset import audit_parent_source_hashes
    from finite_set_tau_continue import expected_bound_input_hashes, validate_bound_input_hashes
    from rough_smoke import serializable

    if (
        grouped.get("schema") != "finite-set-grouped-cohort/v1"
        or grouped.get("run_id") != grouped_path.parent.parent.name
        or grouped.get("unit") != unit or grouped.get("dataset") != dataset
        or grouped.get("reference_read_before_seal") is not False
        or grouped.get("evaluation_written") is not False or not grouped.get("sealed_utc")
        or grouped.get("source_fit_sha256") != snapshot[str(coherent_path)]
        or coherent.get("unit") != unit or coherent.get("dataset") != dataset
        or coherent.get("run_id") != "coherent-v1" or coherent.get("stage") != "coherent"
        or coherent.get("selection_sha256") != protocol["selection_sha256"]
    ):
        raise ValueError("grouped and coherent sources do not bind this frozen unit")
    source_audit = audit_parent_source_hashes(grouped["source_hashes"])
    expected = expected_bound_input_hashes(grouped)
    exports = ROOT / "runs/alias-family-cohort-v1"
    _, data, input_paths = load_unit_with_family_exports(
        unit_id, exports, expected_manifest_sha256=expected[str(exports / "manifest.json")],
    )
    bound_inputs = validate_bound_input_hashes(input_paths, expected)
    if serializable(data.geometry_receipt) != grouped["fit"]["grouped_geometry"]:
        raise ValueError("loaded full geometry differs from frozen grouped geometry")
    expected_coherent_inputs = {session: digest(ROOT / "scans" / session / "bundle.json")
                                for session in unit["session_ids"]}
    if unit["size"] > 1:
        expected_coherent_inputs[unit_id] = digest(ROOT / "units" / unit_id / "bundle.json")
    if coherent.get("inputs") != expected_coherent_inputs:
        raise ValueError("track initializer uses different input bundles")
    return data, initial_parameters(coherent, len(data.numbers)), {
        "unit": unit, "dataset": dataset, "source_hashes": snapshot,
        "bound_input_hashes": bound_inputs, "source_hash_audit": source_audit,
        "geometry_receipt": serializable(data.geometry_receipt),
        "grouped_source_path": str(grouped_path), "grouped_source_sha256": digest(grouped_path),
        "coherent_source_sha256": digest(coherent_path), "grouped_fit": grouped["fit"],
    }


def run_unit(unit_id, arm):
    output = ROOT / "runs" / RUNS[arm] / unit_id
    if output.exists():
        raise FileExistsError(output)
    started = time.monotonic()
    binding = None
    try:
        data, initial, binding = prepare(unit_id, arm)
        if arm == "legacy":
            from legacy_timing10_fit import fit_legacy_timing10

            trial = fit_legacy_timing10(data, initial, budget_s=60.0)
            fitted = {"trials": [trial], "selection": {
                "score_leader": trial, "winner": trial,
                "selection_resolved": bool(trial["success"]), "success": bool(trial["success"]),
            }}
        else:
            from finite_set_cavity import prepare_replacement_scorer
            from finite_set_tau_profile_run import fit_profile_branches

            fitted = fit_profile_branches(
                data, binding["grouped_fit"], cavity_factory=prepare_replacement_scorer,
            )
        from finite_set_fit import assert_snapshot_unchanged
        from rough_smoke import serializable

        assert_snapshot_unchanged(binding["source_hashes"])
        receipt = {key: value for key, value in binding.items() if key != "grouped_fit"}
        receipt.update(
            schema=f"{RUNS[arm][:-3]}/v1", run_id=RUNS[arm], arm=arm, fit=fitted,
            protocol_sha256=digest(PROTOCOL), elapsed_s=time.monotonic() - started,
            reference_read_before_seal=False, evaluation_written=False,
            sealed_utc=datetime.now(UTC).isoformat(), initial_parameters=initial,
            candidate_count=len(data.numbers), all_data_used=True,
        )
        output.mkdir(parents=True, exist_ok=False)
        with (output / "fit.json").open("x") as stream:
            json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
        return {"unit_id": unit_id, "arm": arm, "elapsed_s": receipt["elapsed_s"],
                "selection_resolved": fitted["selection"]["selection_resolved"]}
    except Exception as error:
        if not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            with (output / "failure.json").open("x") as stream:
                json.dump({"unit_id": unit_id, "arm": arm, "error": str(error),
                           "error_type": type(error).__name__, "reference_read_before_seal": False,
                           "elapsed_s": time.monotonic() - started,
                           "source_hashes": None if binding is None else binding["source_hashes"]},
                          stream, indent=2)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--arm", choices=tuple(RUNS), required=True)
    parser.add_argument("--preflight", action="store_true")
    arguments = parser.parse_args()
    if arguments.preflight:
        data, initial, binding = prepare(arguments.unit, arguments.arm)
        print(json.dumps({"unit": arguments.unit, "arm": arguments.arm,
                          "rows": len(data.times), "candidates": len(data.numbers)}))
    else:
        print(json.dumps(run_unit(arguments.unit, arguments.arm)), flush=True)
