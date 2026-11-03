"""Bounded alias-family input ablation; no reference-position access."""

from __future__ import annotations

import argparse
import json

import numpy as np
from finite_set_fit import (
    GroupMedianGeometryData,
    array_digest,
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from gauss_newton import refine_gauss_newton
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import select_trials


class FamilyGeometryData:
    def __init__(self, source, representatives):
        self.source = GroupMedianGeometryData(source)
        indices = np.asarray(representatives, dtype=int)
        if (
            indices.ndim != 1
            or len(indices) == 0
            or len(np.unique(indices)) != len(indices)
            or np.any(indices < 0)
            or np.any(indices >= len(source.times))
        ):
            raise ValueError("representatives must be unique valid source rows")
        self.original_rows = indices.copy()
        for name in ("times", "measured", "rf", "receiver", "channel", "group", "margin"):
            setattr(self, name, np.asarray(getattr(self.source, name))[indices].copy())
        if not np.array_equal(np.unique(self.group), np.unique(source.group)):
            raise ValueError("family grouping must preserve every observation group")
        self.geometry_receipt = {
            "preselection_geometry": self.source.geometry_receipt,
            "representative_row_count": len(indices),
            "group_count": len(np.unique(self.group)),
            "original_rows_sha256": array_digest(self.original_rows),
            "fitted_array_hashes": {
                name: array_digest(getattr(self, name))
                for name in ("times", "measured", "rf", "receiver", "channel", "group", "margin")
            },
        }

    def __getattr__(self, name):
        return getattr(self.source, name)


def fit_families(data, source_fit, *, budget_s=15.0, refiner=refine_gauss_newton):
    if not np.isfinite(budget_s) or not 0 < budget_s <= 15:
        raise ValueError("per-bank budget must lie in (0, 15]")
    trials = []
    for source in source_fit["finite_set_trials"]:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        likelihood = build_likelihood_arms(data, len(satellites), len(source_fit["full_bank"]))[
            "finite_set"
        ]
        trial = refiner(
            data,
            np.asarray(source["parameters"], dtype=float).copy(),
            satellites,
            np.ones(len(satellites)),
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            slope_bound=50.0,
            budget_s=budget_s,
        )
        if trial["objective"] > trial["initial_objective"] + 1e-6:
            raise ValueError("refinement increased its same-data seed objective")
        trial["source_parameters"] = source["parameters"]
        trial["source_bank_unchanged"] = True
        trials.append(trial)
    return {
        "full_bank": source_fit["full_bank"],
        "finite_set_trials": trials,
        "finite_set_selection": select_trials(trials),
    }


def run_case(unit_id, run_id):
    import alias_family
    import candidate_prevalence_diagnostic as prevalence
    import edge_alias_diagnostic as edge

    _, session_id, _ = prevalence.UNITS[unit_id]
    source_path = ROOT / "runs" / prevalence.SOURCE_RUN_ID / unit_id / "fit.json"
    bundle_dir = ROOT / "scans" / session_id
    output = ROOT / "runs" / run_id / unit_id / "fit.json"
    if output.exists():
        raise FileExistsError(output)
    source = json.loads(source_path.read_text())
    if (
        source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or source.get("stage") != "finite_set_raw_control_continuation"
        or source.get("unit", {}).get("unit_id") != unit_id
        or source.get("unit", {}).get("session_ids") != [session_id]
    ):
        raise ValueError("source must be a sealed truth-free fit")
    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    paths = [source_path, bundle_dir / "bundle.json", bundle_dir / "bundle.npz"]
    paths.append(bundle_path)
    paths += list(ROOT.glob("*.py"))
    snapshot = snapshot_files(paths)
    manifest = json.loads((bundle_dir / "bundle.json").read_text())
    bundle = load_module("family_bundle", bundle_path)
    data = bundle.Data(bundle_dir)
    _, projected, rows, join, sample_rate = edge._metadata(
        prevalence.DEFAULT_BULK_ROOT,
        session_id,
        manifest["provenance"]["input_manifest_sha256"],
        manifest["provenance"]["persisted_analysis_manifest_sha256"],
    )
    binding = prevalence._verify_bundle_rows(data, manifest, projected)
    if any(row is None for row in rows):
        raise ValueError("metadata join must be complete")
    for row, point in zip(rows, projected, strict=True):
        row["candidate_id"] = point.candidate_id
    grouping = alias_family.group_alias_families(rows, frame_period_samples=sample_rate / 750.0)
    row_indices = {row["candidate_id"]: index for index, row in enumerate(rows)}
    representatives = [row_indices[row["candidate_id"]] for row in grouping["representative_rows"]]
    geometry = FamilyGeometryData(data, representatives)
    fit = fit_families(geometry, source["fit"])
    assert_snapshot_unchanged(snapshot)
    result = {
        "schema": "finite-set-alias-family-pilot/v1",
        "unit_id": unit_id,
        "session_id": session_id,
        "source_fit_sha256": digest(source_path),
        "source_hashes": snapshot,
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "interpretation": (
            "Input ablation; absolute objective is not comparable to ungrouped data. "
            "Candidate bank remains conditional on persisted reviews. "
            "All families train the fit through their selected representatives; no holdout."
        ),
        "join": {**join, **binding},
        "grouping": grouping,
        "original_row_count": len(data.times),
        "representative_row_count": len(geometry.times),
        "geometry_receipt": geometry.geometry_receipt,
        "fit": fit,
        "sealed": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(output), "sha256": digest(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id", choices=("DS10-S01", "DS11-S02"))
    parser.add_argument("--run-id", default="finite-set-alias-family-v1")
    arguments = parser.parse_args()
    print(json.dumps(run_case(arguments.unit_id, arguments.run_id)))
