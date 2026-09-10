"""Register a verified native publication for the recording API and UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from leo.operations.native_recording_registry import NativeRecordingRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    bundle_id = NativeRecordingRegistry(args.registry).register(
        args.manifest, expected_sha256=args.sha256
    )
    print(json.dumps({"bundle_id": bundle_id}))


if __name__ == "__main__":
    main()
