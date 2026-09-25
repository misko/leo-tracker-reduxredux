#!/usr/bin/env python3
"""Prepare the read-only DS3 LT3D geometry/cone model eligibility plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from support import build_plan, recording_loader

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE.parent / "manifest.json"


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--capture-root",
        type=Path,
        help="read-only override containing <session_id>/manifest.json",
    )
    args = parser.parse_args()
    document = build_plan(load_object(args.manifest), recording_loader(args.capture_root))
    print(json.dumps(document, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
