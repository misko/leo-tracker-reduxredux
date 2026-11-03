#!/usr/bin/env python3
"""Execute one evaluator-blind covariance/epoch confirmation arm."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource

from core import run_model

ARMS = ("C1", "M2", "M4", "M24")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", required=True)
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    seal_path = args.output.with_suffix(".seal.json")
    if args.output.exists() or seal_path.exists():
        raise FileExistsError("prediction or seal already exists")
    result = run_model(args.unit, args.arm, args.evidence_root)
    if result.get("unit_id") != args.unit or result.get("arm") != args.arm:
        raise ValueError("model result identity differs from requested cell")
    if result.get("reference_coordinate_accessed") is not False:
        raise ValueError("model result lacks explicit truth-isolation declaration")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(result, indent=2, allow_nan=False) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(encoded)
    seal = {"prediction_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest()}
    with seal_path.open("x") as stream:
        json.dump(seal, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "status": result["status"]}))


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_AS, (6 * 1024**3, 6 * 1024**3))
    main()
