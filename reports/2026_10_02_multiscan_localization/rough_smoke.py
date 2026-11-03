"""Bounded cohort smoke run of rough-track initialization, with post-fit evaluation."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from selection import ROOT
from track_seed import fit_rough


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def serializable(value):
    if isinstance(value, np.ndarray):
        return serializable(value.tolist())
    if isinstance(value, np.generic):
        return serializable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serializable(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--source-root", type=Path, default=ROOT / "scans")
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    selection = json.loads((ROOT / "selection.json").read_text())
    dataset = next(
        (
            name
            for name, value in selection["datasets"].items()
            if args.session_id in value["selected"]
        ),
        None,
    )
    if dataset is None:
        parser.error("Session does not belong to frozen matched cohort")
    source = args.source_root / args.session_id
    manifest = json.loads((source / "bundle.json").read_text())
    population = selection["datasets"][dataset]
    population_bytes = Path(population["manifest_path"]).read_bytes()
    if hashlib.sha256(population_bytes).hexdigest() != population["manifest_sha256"]:
        raise ValueError("Population changed after selection")
    capture = next(
        row
        for row in json.loads(population_bytes)["captures"]
        if row["session_id"] == args.session_id
    )
    if manifest["provenance"]["input_manifest_sha256"] != capture["manifest_sha256"]:
        raise ValueError("Bundle does not bind selected source capture")
    legacy = ROOT.parent / "2026_10_02_localization_benchmark"
    bundle = load_module("rough_smoke_bundle", legacy / "bundle.py")
    data = bundle.Data(source)
    if args.staged:
        from staged_fit import fit_staged

        fitted = fit_staged(data)
        stage = "staged"
        position = fitted["winner"]["parameters"][:2]
        rough = fitted["rough"]
    else:
        fitted = fit_rough(data)
        stage = "rough"
        position = fitted["position_km"]
        rough = fitted
    output = ROOT / "pilots" / args.session_id
    output.mkdir(parents=True, exist_ok=True)
    receipt = {
        "session_id": args.session_id,
        "dataset": dataset,
        "stage": stage,
        "input_bundle_sha256": hashlib.sha256((source / "bundle.npz").read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256((ROOT / "track_seed.py").read_bytes()).hexdigest(),
        "solver_sources_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("track_seed.py", "staged_fit.py", "grouped_likelihood.py")
        },
        "selection_sha256": hashlib.sha256((ROOT / "selection.json").read_bytes()).hexdigest(),
        "fit": fitted,
        "provenance_scope": data.provenance["scope"],
    }
    (output / f"{stage}-fit.json").write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    truth = json.loads((source / "evaluation.json").read_text())["reference_site"]
    common = bundle._COMMON
    error = float(
        np.linalg.norm(
            common.ecef(*common.coordinates(position))
            - common.ecef(truth["latitude_deg"], truth["longitude_deg"])
        )
    )
    result = {
        "session_id": args.session_id,
        "stage": stage,
        "success": fitted["success"],
        "reference_error_km": error,
        "elapsed_s": rough["elapsed_s"]
        + sum(trial["elapsed_s"] for trial in fitted.get("trials", [])),
        "tracks": len(rough["assignments"]),
        "accepted_tracks": sum(row["accepted"] for row in rough["assignments"]),
    }
    if args.staged:
        result["trials"] = [
            {
                "satellites": trial["satellite_count"],
                "success": trial["success"],
                "message": trial["message"],
                "selection_score": trial["selection_score"],
                "reference_error_km": float(
                    np.linalg.norm(
                        common.ecef(*common.coordinates(trial["parameters"][:2]))
                        - common.ecef(truth["latitude_deg"], truth["longitude_deg"])
                    )
                ),
            }
            for trial in fitted["trials"]
        ]
    (output / f"{stage}-evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
