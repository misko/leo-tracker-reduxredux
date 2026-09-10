"""Inspect a hash-pinned native recording export; perform no RF or rate fitting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from leo.operations.native_journal_recording import review_native_recording


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="Expected SHA-256 of the recording export")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-binding", type=Path)
    parser.add_argument("--source-binding-sha256")
    args = parser.parse_args()
    if (args.source_binding is None) != (args.source_binding_sha256 is None):
        parser.error("--source-binding and --source-binding-sha256 are required together")
    result = review_native_recording(
        args.recording,
        args.output,
        expected_sha256=args.sha256,
        source_binding=args.source_binding,
        expected_binding_sha256=args.source_binding_sha256,
    )
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
