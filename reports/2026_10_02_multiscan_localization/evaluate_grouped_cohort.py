"""Postseal-only reference evaluation for the uniform grouped cohort run."""

from __future__ import annotations

import argparse
import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest
from finite_set_grouped_cohort import RUN_ID
from joint_inputs import _coordinates, _ecef
from selection import ROOT


def evaluate_trial(trial, references):
    estimated = _ecef(*_coordinates(np.asarray(trial["parameters"])[:2]))
    errors = {
        session: float(np.linalg.norm(
            estimated - _ecef(site["latitude_deg"], site["longitude_deg"])
        ))
        for session, site in references.items()
    }
    return {
        "satellite_count": trial["satellite_count"],
        "reference_errors_km": errors,
        "maximum_reference_error_km": max(errors.values()),
        "success": trial["success"], "status": trial["status"],
        "convergence_reason": trial["convergence_reason"],
        "selection_score": trial["selection_score"],
    }


def evaluate_fit(fitted, references):
    selection = fitted["selection"]
    return {
        "selected": evaluate_trial(selection["score_leader"], references),
        "selection_resolved": selection["selection_resolved"],
        "trials": [evaluate_trial(trial, references) for trial in fitted["trials"]],
    }


def run_unit(unit_id, *, run_id=RUN_ID):
    directory = ROOT / "runs" / run_id / unit_id
    fit_path = directory / "fit.json"
    output = directory / "evaluation.json"
    if output.exists():
        raise FileExistsError(output)
    fit_sha256 = digest(fit_path)
    receipt = json.loads(fit_path.read_text())
    if (
        receipt.get("schema") != "finite-set-grouped-cohort/v1"
        or receipt.get("reference_read_before_seal") is not False
        or receipt.get("evaluation_written") is not False
        or not receipt.get("sealed_utc")
        or receipt["unit"]["unit_id"] != unit_id
    ):
        raise ValueError("reference evaluation requires a sealed truth-free fit")
    assert_snapshot_unchanged(receipt["source_hashes"])
    reference_paths = {
        session: ROOT / "scans" / session / "evaluation.json"
        for session in receipt["unit"]["session_ids"]
    }
    references = {
        session: json.loads(path.read_text())["reference_site"]
        for session, path in reference_paths.items()
    }
    evaluation = {
        "schema": "finite-set-grouped-cohort-postseal/v1",
        "run_id": run_id,
        "unit_id": unit_id, "dataset": receipt["dataset"], "size": receipt["unit"]["size"],
        "fit_sha256": fit_sha256, "references": references,
        "reference_file_sha256": {str(path): digest(path) for path in reference_paths.values()},
        **evaluate_fit(receipt["fit"], references),
        "scope": "All-data conditional development benchmark, not held-out validation",
    }
    if digest(fit_path) != fit_sha256:
        raise RuntimeError("sealed fit changed during reference evaluation")
    with output.open("x") as stream:
        json.dump(evaluation, stream, indent=2, allow_nan=False)
    return evaluation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id")
    parser.add_argument("--run-id", default=RUN_ID)
    arguments = parser.parse_args()
    result = run_unit(arguments.unit_id, run_id=arguments.run_id)
    print(json.dumps({key: result[key] for key in ("unit_id", "selected", "selection_resolved")}))
