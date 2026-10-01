"""Post-hoc explanatory association weights for accepted frozen fits only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import audit_receipts
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = ROOT / "plans/localization-approaches-2026-10-01/benchmark.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_diagnostics(log_weights) -> dict:
    """Normalize candidate-then-background log weights stably."""
    values = np.asarray(log_weights, dtype=float)
    if values.ndim != 1 or values.size < 2 or np.any(np.isnan(values)):
        raise ValueError("log weights must contain candidates and background")
    maximum = np.max(values)
    if not np.isfinite(maximum):
        raise ValueError("at least one branch weight must be finite")
    weights = np.exp(values - maximum)
    probabilities = weights / weights.sum()
    satellite = probabilities[:-1]
    satellite_mass = float(satellite.sum())
    conditional_entropy = None
    if satellite_mass > 0:
        conditional = satellite / satellite_mass
        positive = conditional > 0
        conditional_entropy = float(
            -np.sum(conditional[positive] * np.log(conditional[positive]))
        )
    full_positive = probabilities > 0
    full_entropy = float(-np.sum(
        probabilities[full_positive] * np.log(probabilities[full_positive])
    ))
    return {
        "background_probability": float(probabilities[-1]),
        "background_is_argmax": bool(np.argmax(probabilities) == probabilities.size - 1),
        "conditional_satellite_entropy_nats": conditional_entropy,
        "max_satellite_probability": float(np.max(satellite)),
        "effective_branch_count": float(np.exp(full_entropy)),
    }


def run(evaluator_path: Path, *, repository_root: Path = ROOT) -> dict:
    started = time.monotonic()
    evaluator = json.loads(evaluator_path.read_text())
    plan = audit_receipts.load_plan(PLAN)
    jobs = []
    bindings = {}
    height_bindings = {}
    for row in evaluator.get("rows", []):
        if not row.get("accepted"):
            continue
        receipt_path = Path(row["receipt_path"])
        if not receipt_path.is_absolute():
            receipt_path = repository_root / receipt_path
        if digest(receipt_path) != row.get("receipt_sha256"):
            raise ValueError(f"evaluator receipt hash mismatch: {receipt_path}")
        audit = audit_receipts.audit_receipt(receipt_path, plan, repository_root)
        if not audit["passed"] or audit["warnings"]:
            raise ValueError(f"receipt/source/seal audit failed: {receipt_path}: {audit}")
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("best") is None:
            raise ValueError(f"accepted receipt lacks best fit: {receipt_path}")
        jobs.append((row["arm"], row["unit_id"], receipt_path, receipt))
        bindings[str(receipt_path)] = digest(receipt_path)
        for path, expected in receipt.get("inputs", {}).items():
            evidence_path = Path(path)
            if not evidence_path.is_file() or digest(evidence_path) != expected:
                raise ValueError(f"bound evidence hash mismatch: {evidence_path}")
            bindings[path] = expected
        height = receipt.get("height_input_bindings") or {}
        grid_path = Path(height.get("grid_path", ""))
        grid_digest = height.get("grid_sha256")
        if not grid_path.is_file() or not grid_digest or digest(grid_path) != grid_digest:
            raise ValueError(f"bound height input hash mismatch: {grid_path}")
        height_bindings[str(receipt_path)] = height

    # Import only after every accepted receipt and live frozen source has passed audit.
    sys.path.insert(0, str(HERE))
    from adapter import prepare

    scans = []
    for arm, unit, receipt_path, receipt in jobs:
        _scan, _height, ports = prepare(unit)
        best = receipt["best"]
        state = np.asarray(best["mean"] + best["satellite_epoch_s"], dtype=float)
        tracks = [normalized_diagnostics(port.score_all(state)) for port in ports]
        background = [track["background_probability"] for track in tracks]
        entropy = [
            track["conditional_satellite_entropy_nats"] for track in tracks
            if track["conditional_satellite_entropy_nats"] is not None
        ]
        maximum = [track["max_satellite_probability"] for track in tracks]
        effective = [track["effective_branch_count"] for track in tracks]
        scans.append({
            "arm": arm,
            "unit_id": unit,
            "receipt_path": str(receipt_path),
            "track_count": len(tracks),
            "candidate_count": ports[0].candidate_count if ports else 0,
            "mean_background_probability": float(np.mean(background)),
            "max_background_probability": float(np.max(background)),
            "fraction_tracks_background_argmax": float(np.mean([
                track["background_is_argmax"] for track in tracks
            ])),
            "conditional_satellite_entropy_defined_track_count": len(entropy),
            "mean_conditional_satellite_entropy_nats": (
                None if not entropy else float(np.mean(entropy))
            ),
            "mean_max_satellite_probability": float(np.mean(maximum)),
            "mean_effective_branch_count": float(np.mean(effective)),
            "hard_best_background_count": sum(
                value == "background" for value in best.get("associations", [])
            ),
        })
    return {
        "schema": "localization-association-diagnostics/v1",
        "qualification": (
            "post-hoc explanatory normalized fit weights only; not identity accuracy, "
            "calibrated confidence, posterior mode weights, or benchmark runtime"
        ),
        "accepted_scan_count": len(scans),
        "scans": scans,
        "bindings": {
            "helper_sha256": digest(Path(__file__)),
            "adapter_sha256": digest(HERE / "adapter.py"),
            "evaluator_sha256": digest(evaluator_path),
            "receipts_and_evidence": dict(sorted(bindings.items())),
            "height_input_bindings_by_receipt": dict(sorted(height_bindings.items())),
        },
        "posthoc_wall_seconds": time.monotonic() - started,
        "posthoc_time_excluded_from_inference_benchmark": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_two_stage_evaluator", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.final_two_stage_evaluator)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
