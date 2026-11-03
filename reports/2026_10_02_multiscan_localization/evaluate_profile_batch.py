"""Evaluate sealed grouped/profile fits without feeding references back to fitting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluate_grouped_cohort import evaluate_fit
from finite_set_fit import assert_snapshot_unchanged, digest
from selection import ROOT

SCHEMAS = {
    "grouped-independent-rx-v1": "grouped-independent-rx/v1",
    "finite-set-grouped-cohort-v1": "finite-set-grouped-cohort/v1",
    "finite-set-tau-profile-v1": "finite-set-tau-profile/v1",
    "finite-set-capture-reset-v1": "finite-set-capture-reset/v1",
    "finite-set-reset-profile-v1": "finite-set-reset-profile/v1",
    "finite-set-rf-fit-v1": "finite-set-rf-fit/v1",
    "finite-set-rf-gn-v1": "finite-set-rf-gn/v1",
    "finite-set-rf-profile-v1": "finite-set-rf-profile/v1",
    "finite-set-reset-multistart-v1": "finite-set-reset-multistart/v1",
    "finite-set-reset-cohort-v1": "finite-set-reset-cohort/v1",
    "finite-set-reset-sparse-continue-v1": "finite-set-reset-sparse-continue/v1",
    "legacy-timing10-cohort-v1": "legacy-timing10-cohort/v1",
    "grouped-timing-profile-joint-v1": "grouped-timing-profile-joint/v1",
    "finite-set-rf-cohort-v1": "finite-set-rf-cohort/v1",
    "finite-set-group-mixture-v1": "finite-set-group-mixture/v1",
    "finite-set-group-mixture-continue-v1": "finite-set-group-mixture-continue/v1",
}


def validate_receipt(record, unit_id, run_id):
    if (
        run_id not in SCHEMAS or record.get("schema") != SCHEMAS[run_id]
        or record.get("run_id") != run_id
        or record.get("unit", {}).get("unit_id") != unit_id
        or record.get("reference_read_before_seal") is not False
        or record.get("evaluation_written") is not False
        or not record.get("sealed_utc")
        or not record.get("source_hashes")
    ):
        raise ValueError("evaluation requires an identified, sealed, truth-free fit")


def evaluate_unit(unit_id, run_id):
    directory = ROOT / "runs" / run_id / unit_id
    fit_path = directory / "fit.json"
    fit_hash = digest(fit_path)
    record = json.loads(fit_path.read_text())
    validate_receipt(record, unit_id, run_id)
    output = directory / "evaluation.json"
    if output.exists():
        result = json.loads(output.read_text())
        if result.get("fit_sha256") != fit_hash:
            raise ValueError("existing evaluation is bound to a different fit")
        assert_snapshot_unchanged(result["reference_file_sha256"])
        return result
    assert_snapshot_unchanged(record["source_hashes"])
    paths = {
        session: ROOT / "scans" / session / "evaluation.json"
        for session in record["unit"]["session_ids"]
    }
    hashes = {str(path): digest(path) for path in paths.values()}
    references = {
        session: json.loads(path.read_text())["reference_site"] for session, path in paths.items()
    }
    result = {
        "schema": "grouped-profile-postseal/v1", "unit_id": unit_id, "run_id": run_id,
        "fit_sha256": fit_hash, "reference_file_sha256": hashes, "references": references,
        **evaluate_fit(record["fit"], references),
        "scope": "All-data conditional development benchmark, not held-out validation.",
    }
    assert_snapshot_unchanged(hashes)
    if digest(fit_path) != fit_hash:
        raise RuntimeError("fit changed during evaluation")
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def run_batch(plan_path, output_path):
    plan_path, output_path = Path(plan_path), Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    plan_hash = digest(plan_path)
    plan = json.loads(plan_path.read_text())
    if plan["selection_sha256"] != digest(ROOT / "selection.json"):
        raise ValueError("batch selection changed")
    rows = []
    for unit in plan["unit_ids"]:
        stages = {run_id: evaluate_unit(unit, run_id) for run_id in plan["pipeline"]}
        rows.append({"unit_id": unit, "stages": stages})
    if digest(plan_path) != plan_hash:
        raise RuntimeError("batch plan changed")
    result = {"schema": "grouped-profile-batch-evaluation/v1", "plan_sha256": plan_hash,
              "rows": rows, "scope": "Every planned unit retained, including unresolved fits."}
    with output_path.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("output")
    arguments = parser.parse_args()
    result = run_batch(arguments.plan, arguments.output)
    for row in result["rows"]:
        print(json.dumps({"unit_id": row["unit_id"], "stages": {
            run_id: {"error_km": stage["selected"]["maximum_reference_error_km"],
                     "resolved": stage["selection_resolved"],
                     "satellites": stage["selected"]["satellite_count"]}
            for run_id, stage in row["stages"].items()
        }}))
