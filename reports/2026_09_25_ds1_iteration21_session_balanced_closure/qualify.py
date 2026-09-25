#!/usr/bin/env python3
"""Qualification for an interior iteration21 zero-rate basin."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--fidelity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output exists")
    inference, fidelity = (
        json.loads(args.inference.read_text()),
        json.loads(args.fidelity.read_text()),
    )
    if fidelity.get("inference_sha256") != digest(args.inference):
        raise ValueError("fidelity is not bound to inference")
    closure = bool(
        inference.get("complete")
        and inference.get("steps")
        and not inference["steps"][-1]["winner_on_edge"]
    )
    scores = inference.get("per_session_scores_by_coordinate", [])
    score_complete = bool(scores and all(len(row.get("session_scores", [])) == 6 for row in scores))
    result = {
        "schema": "ds1-iteration21-session-balanced-closure-qualification/v1",
        "reference_used": False,
        "inference": {"path": str(args.inference), "sha256": digest(args.inference)},
        "fidelity": {"path": str(args.fidelity), "sha256": digest(args.fidelity)},
        "interior_closure": closure,
        "per_session_score_coverage_complete": score_complete,
        "zero_rate_direct_sgp4_passed": bool(fidelity.get("passed")),
        "widened_rate_diagnostic": "not used for selection or qualification",
        "qualified": bool(closure and score_complete and fidelity.get("passed")),
    }
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
