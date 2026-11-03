"""Bounded, versioned unit fits; reference evaluation follows sealed fit output."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from joint_inputs import load_joint_data
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import fit_staged
from track_seed import fit_rough


def find_unit(selection, unit_id):
    matches = [
        (dataset, unit)
        for dataset, population in selection["datasets"].items()
        for unit in population["units"]
        if unit["unit_id"] == unit_id
    ]
    if len(matches) != 1:
        raise ValueError("Unit must appear exactly once in frozen selection")
    return matches[0]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rough_seed(root, run_id, unit, inputs):
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("rough run_id must be one nonempty path component")
    path = root / "runs" / run_id / unit["unit_id"] / "fit.json"
    receipt = json.loads(path.read_text())
    if receipt["stage"] != "rough" or receipt["unit"] != unit:
        raise ValueError("Cached rough fit has different stage or unit")
    if receipt["inputs"] != inputs:
        raise ValueError("Cached rough fit has different input bindings")
    if receipt["selection_sha256"] != digest(root / "selection.json"):
        raise ValueError("Cached rough fit has different selection")
    if receipt["source_hashes"]["track_seed.py"] != digest(root / "track_seed.py"):
        raise ValueError("Cached rough fit used a different rough solver")
    return receipt["fit"], digest(path)


def run_unit(
    unit_id,
    run_id,
    rough_only=False,
    coherent=False,
    fixed_mass_raw=False,
    rough_run_id=None,
    annealed=False,
    share_predictions=False,
    optimizer="lbfgs",
):
    if sum((rough_only, coherent, fixed_mass_raw, annealed)) > 1:
        raise ValueError("Select only one fitting mode")
    if share_predictions and not annealed:
        raise ValueError("Prediction sharing is currently enabled only for annealed fits")
    if optimizer not in ("lbfgs", "gauss-newton") or (optimizer != "lbfgs" and not annealed):
        raise ValueError("Alternative optimizer requires annealed mode")
    if rough_only and rough_run_id is not None:
        raise ValueError("Cannot reuse a rough fit in rough-only mode")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one nonempty path component")
    selection = json.loads((ROOT / "selection.json").read_text())
    dataset, unit = find_unit(selection, unit_id)
    population = selection["datasets"][dataset]
    population_path = Path(population["manifest_path"])
    if digest(population_path) != population["manifest_sha256"]:
        raise ValueError("Population digest changed")
    captures = {
        row["session_id"]: row for row in json.loads(population_path.read_text())["captures"]
    }
    inputs = {}
    for session in unit["session_ids"]:
        folder = ROOT / "scans" / session
        manifest = json.loads((folder / "bundle.json").read_text())
        if manifest["provenance"]["input_manifest_sha256"] != captures[session]["manifest_sha256"]:
            raise ValueError("Child does not bind frozen population capture")
        if digest(folder / "bundle.npz") != manifest["artifacts"]["bundle_npz_sha256"]:
            raise ValueError("Child bundle digest mismatch")
        inputs[session] = digest(folder / "bundle.json")
    bundle = load_module(
        "cohort_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    if unit["size"] == 1:
        data = bundle.Data(ROOT / "scans" / unit["session_ids"][0])
    else:
        data = load_joint_data(ROOT / "units" / unit_id)
        if data.dataset != dataset or tuple(data.child_sessions) != tuple(unit["session_ids"]):
            raise ValueError("Joint bundle does not match selected unit")
        inputs[unit_id] = digest(ROOT / "units" / unit_id / "bundle.json")
    rough, rough_digest = (
        (None, None) if rough_run_id is None else load_rough_seed(ROOT, rough_run_id, unit, inputs)
    )
    output = ROOT / "runs" / run_id / unit_id
    output.mkdir(parents=True, exist_ok=False)
    source_hashes = {
        path.name: digest(path)
        for path in sorted(ROOT.glob("*.py"))
        if not path.name.startswith("test_")
    }
    started = time.monotonic()
    try:
        if annealed:
            from annealed_fit import fit_annealed

            fitted = fit_annealed(
                data, rough=rough, share_predictions=share_predictions, optimizer=optimizer
            )
        elif coherent or fixed_mass_raw:
            from coherent_fit import fit_coherent

            fitted = fit_coherent(data, rough=rough, keep_track_identity=coherent)
        else:
            fitted = fit_rough(data) if rough_only else fit_staged(data, rough=rough)
    except Exception as error:
        (output / "failure.json").write_text(
            json.dumps(
                {
                    "unit_id": unit_id,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "elapsed_s": time.monotonic() - started,
                    "inputs": inputs,
                    "source_hashes": source_hashes,
                },
                indent=2,
            )
            + "\n"
        )
        raise
    receipt = {
        "unit": unit,
        "dataset": dataset,
        "run_id": run_id,
        "stage": "annealed"
        if annealed
        else "fixed_mass_raw"
        if fixed_mass_raw
        else ("coherent" if coherent else ("rough" if rough_only else "staged")),
        "selection_sha256": digest(ROOT / "selection.json"),
        "inputs": inputs,
        "source_hashes": source_hashes,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "cached_rough_fit_sha256": rough_digest,
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    position = fitted["position_km"] if rough_only else fitted["score_leader"]["parameters"][:2]
    estimated = bundle._COMMON.ecef(*bundle._COMMON.coordinates(position))
    errors = {}
    for session in unit["session_ids"]:
        truth = json.loads((ROOT / "scans" / session / "evaluation.json").read_text())[
            "reference_site"
        ]
        errors[session] = float(
            np.linalg.norm(
                estimated - bundle._COMMON.ecef(truth["latitude_deg"], truth["longitude_deg"])
            )
        )
    evaluation = {
        "unit_id": unit_id,
        "dataset": dataset,
        "size": unit["size"],
        "success": fitted["success"],
        "elapsed_s": receipt["elapsed_s"],
        "fit_sha256": digest(fit_path),
        "reference_errors_km": errors,
        "maximum_reference_error_km": max(errors.values()),
        "scope": "All-data development fit, conditional on persisted candidate bank; "
        "not blind validation.",
    }
    (output / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
    return evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--rough-run-id")
    parser.add_argument("--share-predictions", action="store_true")
    parser.add_argument("--optimizer", choices=("lbfgs", "gauss-newton"), default="lbfgs")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rough-only", action="store_true")
    mode.add_argument("--coherent", action="store_true")
    mode.add_argument("--fixed-mass-raw", action="store_true")
    mode.add_argument("--annealed", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run_unit(
                args.unit_id,
                args.run_id,
                args.rough_only,
                args.coherent,
                args.fixed_mass_raw,
                args.rough_run_id,
                args.annealed,
                args.share_predictions,
                args.optimizer,
            )
        )
    )


if __name__ == "__main__":
    main()
