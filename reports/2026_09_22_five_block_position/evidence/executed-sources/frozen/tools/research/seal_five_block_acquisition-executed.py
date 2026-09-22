#!/usr/bin/env python3
"""Seal a completed five-block regional acquisition including its partition receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PARTITION = "five-chronological-blocks-train-0-2-4-heldout-1-3-v1"
REQUIRED = (
    "result.json",
    "configuration.json",
    "history.json",
    "grid.npz",
    "accumulated.npz",
    "partition-receipt.json",
    "execution-receipt.json",
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def seal(run: Path) -> dict[str, object]:
    result = json.loads((run / "result.json").read_text())
    receipt = json.loads((run / "partition-receipt.json").read_text())
    execution = json.loads((run / "execution-receipt.json").read_text())
    if (
        result.get("complete") is not True
        or result.get("position_truth_used") is not False
        or result.get("partition") != PARTITION
        or receipt.get("partition") != PARTITION
        or result.get("partition_receipt_digest") != receipt.get("content_digest")
        or execution.get("partition_receipt_digest") != receipt.get("content_digest")
        or execution.get("position_truth_used") is not False
    ):
        raise ValueError("only complete bound five-block acquisitions may be sealed")
    sessions = [
        row["session_id"] + ".npz" for row in json.loads((run / "history.json").read_text())
    ]
    names = (*REQUIRED, *sessions)
    if len(names) != len(set(names)) or any(not (run / name).is_file() for name in names):
        raise ValueError("five-block acquisition file inventory is incomplete")
    document = {
        "schema": "regional-five-block-acquisition-content-seal-v1",
        "files": {name: digest(run / name) for name in sorted(names)},
    }
    path = run / "acquisition-seal.json"
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != payload:
        raise ValueError("five-block acquisition changed after sealing")
    path.write_text(payload)
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps({str(path): seal(path) for path in args.run}, indent=2))


if __name__ == "__main__":
    main()
