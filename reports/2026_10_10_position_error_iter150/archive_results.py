"""Reuse verified deterministic archive and safe restore."""

import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "archive148_for150", HERE.parent / "2026_10_10_position_error_iter148/archive_results.py"
)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore-to", type=Path)
    args = parser.parse_args()
    if args.restore_to:
        previous.SAFE.restore(
            HERE / "results-summary.tar.gz",
            json.loads((HERE / "RESULT_ARCHIVE.json").read_text()),
            args.restore_to,
        )
    else:
        result = previous.create(HERE, HERE.parents[1])
        print(result["archive_bytes"], result["archive_sha256"])
