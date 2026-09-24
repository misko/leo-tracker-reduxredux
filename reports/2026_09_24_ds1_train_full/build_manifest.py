#!/usr/bin/env python3
"""Materialize the sealed DS1 TRAIN-only manifest from the DS1 dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark import build_manifest, canonical_json, sha256_file, validate_task

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE.parent / "2026_09_24_ds1" / "dataset.json"


def write_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=HERE / "inference-manifest.json")
    parser.add_argument("--singleton-bins", type=int, default=8)
    parser.add_argument("--include-expansion", action="store_true")
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    manifest = build_manifest(
        dataset,
        sha256_file(args.dataset),
        args.singleton_bins,
        include_expansion=args.include_expansion,
    )
    for task in manifest["tasks"]:
        validate_task(task, HERE)
    write_atomic(args.output, canonical_json(manifest))
    write_atomic(args.output.with_suffix(".sha256"), sha256_file(args.output) + "\n")
    print(
        json.dumps(
            {
                "cases": manifest["case_count"],
                "tasks": manifest["task_count"],
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
