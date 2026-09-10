"""Review one published native episode from its manifest and expected digest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from leo.operations.native_recording_bundle import review_native_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review_native_bundle(args.manifest, args.output, expected_sha256=args.sha256)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
