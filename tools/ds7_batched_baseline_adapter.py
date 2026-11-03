#!/usr/bin/env python3
"""Optional exact baseline adapter using cross-track batched offset scheduling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from tools import ds7_baseline_adapter as baseline

    sys.modules.setdefault("ds7_baseline_adapter", baseline)
    from tools import ds7_fast_baseline_adapter as fast
    from tools.ds7_batched_objective import BatchedJointObjective
except ImportError:  # Direct execution from tools/.
    import ds7_baseline_adapter as baseline
    import ds7_fast_baseline_adapter as fast
    from ds7_batched_objective import BatchedJointObjective


def estimate(request: dict) -> dict:
    """Delegate to the frozen fast solver while replacing only its objective scheduler."""
    original = baseline.JointObjective
    baseline.JointObjective = BatchedJointObjective
    try:
        return fast.estimate(request)
    finally:
        baseline.JointObjective = original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    result = estimate(json.loads(args.request.read_text()))
    with args.response.open("x") as stream:
        json.dump(result, stream, allow_nan=False)


if __name__ == "__main__":
    main()
