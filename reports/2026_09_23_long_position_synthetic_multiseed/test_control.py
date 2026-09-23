#!/usr/bin/env python3
"""Publication checks for the frozen multi-seed sensitivity control."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    inference_text = args.inference.read_text()
    inference = json.loads(inference_text)
    results = json.loads(args.results.read_text())
    assert inference["seeds"] == list(range(2026092300, 2026092320))
    assert len(inference["fits"]) == 80
    forbidden = {
        "held_capped800_rmse_hz", "held_uncapped_rmse_hz", "postseal_error_km",
        "postseal_generator", "postseal_summaries",
    }
    observed = set()

    def collect_keys(value):
        if isinstance(value, dict):
            observed.update(value)
            for child in value.values():
                collect_keys(child)
        elif isinstance(value, list):
            for child in value:
                collect_keys(child)

    collect_keys(inference)
    assert forbidden.isdisjoint(observed)
    assert all(row["optimizer_success"] for row in results["fits"])
    assert len(results["postseal_summaries"]) == 4
    assert all(row["fit_count"] == 20 for row in results["postseal_summaries"])
    print("multi-seed synthetic control checks passed")


if __name__ == "__main__":
    main()
