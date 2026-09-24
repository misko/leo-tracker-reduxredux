#!/usr/bin/env python3
"""Record a reference comparison only after successor inference is sealed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> bool:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    return (
        path.is_file()
        and sidecar.is_file()
        and sidecar.read_text().strip() == digest(path).removeprefix("sha256:")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--reference-latitude", type=float, required=True)
    parser.add_argument("--reference-longitude", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    execution = args.input_root / "portable" / "execution.json"
    if not sealed(execution) or json.loads(execution.read_text()).get("complete") is not True:
        raise ValueError("reference evaluation requires sealed, complete successor inference")
    if args.output.exists() or args.output.with_suffix(args.output.suffix + ".sha256").exists():
        raise FileExistsError(f"refusing to overwrite evaluation: {args.output}")
    value = {
        "schema": "ds2-successor-postseal-evaluation/v1",
        "inference": {"path": str(execution.resolve()), "sha256": digest(execution)},
        "reference_coordinate": {
            "latitude_deg": args.reference_latitude,
            "longitude_deg": args.reference_longitude,
            "role": "introduced only after complete sealed successor inference",
        },
    }
    content = json.dumps(value, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
