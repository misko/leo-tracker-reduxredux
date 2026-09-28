"""Wave-2 matched search using the numerically verified batched profiler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The frozen fast script uses sibling imports; preserve that exact module instance.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ds7_fast_baseline_adapter as fast  # noqa: E402

from tools import ds7_association_adapter as search  # noqa: E402


def estimate(request):
    previous_model, previous_profile = search.baseline, fast.baseline.profile
    search.baseline, fast.baseline.profile = fast.baseline, fast.profile
    try:
        return search.estimate(request)
    finally:
        search.baseline, fast.baseline.profile = previous_model, previous_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    response = estimate(json.loads(args.request.read_text()))
    with args.response.open("x") as stream:
        json.dump(response, stream, allow_nan=False)


if __name__ == "__main__":
    main()
