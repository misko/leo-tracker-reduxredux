"""Retry both pause-affected members from frozen original seeds, without warm starts."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = HERE.parent / "2026_10_09_position_error_iter84"
sys.path.insert(0, str(ORIGINAL))
import evaluate as original  # noqa: E402


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    original.HERE = HERE
    for binding in plan["members"]:
        if binding["member"]["inventory_label"] in plan["retry_members"]:
            original.evaluate(binding, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    main()
