#!/usr/bin/env python3
"""Execute one sealed, evaluator-blind model arm."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import resource
from core import run_model


FEATURE_ARMS = {"M6", "M7", "M10"}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def unavailable_feature_result(unit: str, arm: str, evidence_root: Path) -> dict:
    """Return a source-bound terminal receipt without inventing an observable."""
    feature_path = Path(__file__).with_name("feature-feasibility.json")
    evidence_path = evidence_root / f"{unit}.json"
    feature_document = json.loads(feature_path.read_text())
    evidence = json.loads(evidence_path.read_text())
    model = feature_document["models"][arm]
    if model["status"] == "feasible":
        raise RuntimeError(f"{arm} is feasible and requires a numerical implementation")
    return {
        "schema": "sacramento-model-prediction/v2",
        "unit_id": unit,
        "arm": arm,
        "method": model["method"],
        "status": model["status"],
        "qualified": False,
        "reason": model["reason"],
        "required_fields": model["required_fields"],
        "session_id": evidence["session_id"],
        "manifest_sha256": evidence["manifest_sha256"],
        "inputs": {
            str(evidence_path): digest(evidence_path),
            str(feature_path): digest(feature_path),
        },
        "reference_coordinate_accessed": False,
        "point_estimate": None,
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".seal.json").exists():
        raise FileExistsError("prediction or seal already exists")
    result = (
        unavailable_feature_result(args.unit, args.arm, args.evidence_root)
        if args.arm in FEATURE_ARMS
        else run_model(args.unit, args.arm, args.evidence_root)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(result, indent=2, allow_nan=False) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(encoded)
    seal = {"prediction_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest()}
    with args.output.with_suffix(".seal.json").open("x") as stream:
        json.dump(seal, stream, indent=2); stream.write("\n")
    print(json.dumps({"output": str(args.output), "status": result["status"]}))

if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_AS, (6 * 1024**3, 6 * 1024**3))
    main()
