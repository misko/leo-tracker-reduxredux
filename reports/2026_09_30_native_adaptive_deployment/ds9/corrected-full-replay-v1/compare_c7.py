#!/usr/bin/env python3
"""Summarize bounded corrected-native C7 searches against frozen reference traces."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEARCH = HERE / "full-public-c3-c4" / "c7-search"
REFERENCE = HERE.parents[1] / "location" / "c7-reference-search-v2"
PRIORS = {
    "sacramento": {"latitude_deg": 38.5816, "longitude_deg": -121.4944, "radius_km": 250.0},
    "reno": {"latitude_deg": 39.5296, "longitude_deg": -119.8138, "radius_km": 500.0},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timing(path: Path) -> dict[str, float | int]:
    return json.loads(path.read_text())


def main() -> None:
    regions = {}
    for name, prior in PRIORS.items():
        native_path = SEARCH / f"{name}.json"
        reference_path = REFERENCE / f"{name}.json"
        native = json.loads(native_path.read_text())
        reference = json.loads(reference_path.read_text())
        if native["evaluated_points"] != len(native["evaluations"]):
            raise ValueError(f"{name}: native evaluation count mismatch")
        native_by_point = {(row[0], row[1]): row[2] for row in native["evaluations"]}
        reference_by_point = {(row[0], row[1]): row[2] for row in reference["evaluations"]}
        common = set(native_by_point) & set(reference_by_point)
        max_difference = max(
            abs(native_by_point[point] - reference_by_point[point]) for point in common
        )
        native_selected = native["selected"]
        reference_selected = reference["selected"]
        regions[name] = {
            "prior": prior,
            "evaluated_points": native["evaluated_points"],
            "frontier_complete": native["complete"],
            "solver_status": "point-budget-reached",
            "globally_converged": False,
            "budget_points": 400,
            "selected": native_selected,
            "reference_selected": reference_selected,
            "comparison": {
                "same_incumbent_offset": (
                    native_selected["east_km"] == reference_selected["east_km"]
                    and native_selected["north_km"] == reference_selected["north_km"]
                ),
                "incumbent_offset_separation_km": (
                    (native_selected["east_km"] - reference_selected["east_km"]) ** 2
                    + (native_selected["north_km"] - reference_selected["north_km"]) ** 2
                )
                ** 0.5,
                "score_difference_hz": (
                    native_selected["score_hz"] - reference_selected["score_hz"]
                ),
                "common_evaluated_points": len(common),
                "same_evaluation_order": [row[:2] for row in native["evaluations"]]
                == [row[:2] for row in reference["evaluations"]],
                "maximum_common_point_score_difference_hz": max_difference,
            },
            "wall_timing": timing(SEARCH / f"{name}.time"),
            "trace_sha256": sha256(native_path),
            "reference_trace_sha256": sha256(reference_path),
            "stderr_sha256": sha256(SEARCH / f"{name}.stderr"),
        }
    result = {
        "schema": "org.leo.corrected-native-public-c7/v1",
        "status": "executed_budget_exhausted",
        "fixture": "../native-e2.loc1",
        "fixture_sha256": sha256(HERE / "full-public-c3-c4" / "native-e2.loc1"),
        "location_binary": "/tmp/leo-location-final-host/leo-location",
        "location_binary_sha256": sha256(Path("/tmp/leo-location-final-host/leo-location")),
        "workers": 2,
        "timeout_seconds_per_region": 300,
        "saved_winner_or_satellite_identity_input": False,
        "reference_identity_or_moment_injected": False,
        "regions": regions,
        "qualification": (
            "Both searches evaluated the fixed 400-point budget with complete=false. The "
            "returned incumbents are measured bounded-search results, not globally converged "
            "locations. Differences are interpreted with the independently measured partition "
            "and winner sensitivity in reference-comparison.json."
        ),
    }
    (SEARCH / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
