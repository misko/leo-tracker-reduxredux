#!/usr/bin/env python3
"""Executable publication checks for the frozen synthetic control."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--parity", type=Path, required=True)
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text())
    results = json.loads(args.results.read_text())
    parity = json.loads(args.parity.read_text())
    assert len(results["fits"]) == 6
    assert "held_" not in args.inference.read_text()
    assert inference["generator_coordinate_available_to_fit"] is False
    assert results["postseal_checks"]["noiseless_recovery"]["passed"]
    assert results["postseal_checks"]["held_frequency_invariance"]["passed"]
    assert parity["corrected_inference_held_key_count"] == 0
    assert parity["all_fits_identical"]
    assert all(row["prior_boundary_margin_km"] >= 0 for row in results["fits"])
    assert all(row["optimizer_success"] for row in results["fits"])
    print("synthetic control publication checks passed")


if __name__ == "__main__":
    main()
