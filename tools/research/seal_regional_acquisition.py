#!/usr/bin/env python3
"""Create or verify a content seal for a completed regional acquisition run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

REQUIRED = ("result.json", "configuration.json", "history.json", "grid.npz", "accumulated.npz")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def seal(run: Path) -> dict[str, object]:
    result = json.loads((run / "result.json").read_text())
    if result.get("complete") is not True or result.get("position_truth_used") is not False:
        raise ValueError("only complete truth-free acquisitions may be sealed")
    sessions = [
        row["session_id"] + ".npz" for row in json.loads((run / "history.json").read_text())
    ]
    names = (*REQUIRED, *sessions)
    if len(names) != len(set(names)) or any(not (run / name).is_file() for name in names):
        raise ValueError("regional acquisition file inventory is incomplete")
    document = {
        "schema": "regional-acquisition-content-seal-v1",
        "files": {name: digest(run / name) for name in sorted(names)},
    }
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    path = run / "acquisition-seal.json"
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("regional acquisition changed after sealing")
        return document
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=run)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps({str(path): seal(path) for path in args.run}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
