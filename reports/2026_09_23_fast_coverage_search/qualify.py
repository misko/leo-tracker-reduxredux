#!/usr/bin/env python3
"""Verify frozen run digests and build the normalized benchmark summary."""

import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "inputs" / "runs"
SOURCES = {
    "sacramento": {
        "coarse": "fast-coverage-search-v1-sacramento-qualified",
        "exact50": "fast-coverage-search-v1-sacramento-exact-topk50-parallel8",
        "fine": "fast-coverage-search-v1-sacramento-adaptive-beam32-fine",
    },
    "reno": {
        "coarse": "fast-coverage-search-v1-reno-qualified",
        "exact50": "fast-coverage-search-v1-reno-exact-topk50",
        "fine": "fast-coverage-search-v1-reno-adaptive-beam32-fine",
    },
    "denver": {
        "coarse": "fast-coverage-search-v1-denver-qualified",
        "exact50": "fast-coverage-search-v1-denver-exact-topk50-workers16",
        "fine": "fast-coverage-search-v1-denver-adaptive-beam32-fine",
    },
}


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_run(root, run_id):
    summary_path = root / "benchmark-summary.json"
    summary = read(summary_path)
    receipt = next(row for row in summary["runs"] if row["run_id"] == run_id)
    result_path = root / run_id / "result.json"
    assert receipt["result_digest"] == digest(result_path)
    result = read(result_path)
    finalists_path = root / run_id / "finalists.json.gz"
    assert result["finalists_digest"] == digest(finalists_path)
    if "trace_digest" in result:
        assert result["trace_digest"] == digest(root / run_id / "trace.json")
    for name, expected in summary["source_snapshot"]["files"].items():
        assert expected == digest(root / "source" / name)
    with gzip.open(finalists_path, "rt") as stream:
        finalists = json.load(stream)
    return summary, result, finalists[0]


def main():
    rows = []
    seeded_path = HERE / "inputs" / "exact50-seeded-fine-result.json"
    assert digest(seeded_path) == (
        "sha256:9caac16b1d39204c2297e7e4acb607b5ae97bed5067fa24b52af8c973789efaa"
    )
    seeded = read(seeded_path)
    assert seeded["schema"] == "exact50-seeded-fine-coverage/v1"
    assert seeded["complete"] is True and seeded["truth_accessed"] is False
    reproduction_path = HERE / "inputs" / "exact50-seeded-fine-reproduction.json"
    assert digest(reproduction_path) == (
        "sha256:7ad700a15a9b5c43c7e32f3efb5ac614b0100b8e77d0782ba45eafd85cf0c36b"
    )
    reproduction = read(reproduction_path)
    assert reproduction["retrospective_capture"] is True
    assert reproduction["completed_result_digest"] == digest(seeded_path)
    for relative, expected in reproduction["sources"].items():
        name = Path(relative).name
        assert expected == digest(HERE / "inputs" / "exact50-seeded-fine-source" / name)
    for city, names in SOURCES.items():
        coarse_summary, coarse, coarse_final = load_run(
            RUNS / names["coarse"], f"{city}-uniform-200km"
        )
        exact_summary, exact, exact_final = load_run(
            RUNS / names["exact50"], f"{city}-uniform-50km"
        )
        fine_summary, fine, fine_final = load_run(RUNS / names["fine"], f"{city}-adaptive")
        for label, summary, result, finalist in (
            ("fixed 200 km", coarse_summary, coarse, coarse_final),
            ("exact top-15 50 km", exact_summary, exact, exact_final),
            ("adaptive beam 32 to 12.5 km", fine_summary, fine, fine_final),
        ):
            primary = result["top_cells"][0]["coverage"][0]
            row = {
                "city": city,
                "label": label,
                "mode": result["mode"],
                "evaluated_points": result["requested_points"],
                "fully_scored_points": result["newly_scored_points"],
                "pruned_points": result.get(
                    "partially_scored_pruned_points", len(result.get("pruning_bounds", []))
                ),
                "timing_s": {
                    "prepare": summary["timing_s"]["prediction_bank_prepare"],
                    **result["timing_s"],
                },
                "finalist": {
                    "east_km": result["top_cells"][0]["east_km"],
                    "north_km": result["top_cells"][0]["north_km"],
                    "latitude_deg": finalist["latitude_deg"],
                    "longitude_deg": finalist["longitude_deg"],
                    **primary,
                },
                "source_snapshot": summary["source_snapshot"],
                "top_k_recall": None,
                "objective_gap": None,
            }
            if label.startswith("adaptive"):
                trace = read(RUNS / names["fine"] / f"{city}-adaptive" / "trace.json")
                row["resolution_progress"] = [
                    {
                        "spacing_km": item["spacing_km"],
                        "new_points": item["new_cell_count"],
                        "cumulative_points": item["cumulative_cell_count"],
                    }
                    for item in trace
                ]
            rows.append(row)
        seeded_city = seeded["cities"][city]
        seeded_top = seeded_city["top_cells"][0]
        seeded_final = seeded_city["top_five_finalists"][0]
        primary = seeded_top["coverage"][0]
        rows.append(
            {
                "city": city,
                "label": "exact-50-seeded local 12.5 km",
                "mode": "adaptive-seeded",
                "evaluated_points": seeded_city["trace"][-1]["cumulative_cell_count"],
                "fully_scored_points": seeded_city["trace"][-1]["cumulative_cell_count"],
                "pruned_points": 0,
                "timing_s": {
                    "prepare": seeded["prediction_bank"]["elapsed_s"],
                    "search": seeded_city["elapsed_s"],
                    "finalist_recompute": 0.0,
                },
                "finalist": {
                    "east_km": seeded_top["east_km"],
                    "north_km": seeded_top["north_km"],
                    "latitude_deg": seeded_final["latitude_deg"],
                    "longitude_deg": seeded_final["longitude_deg"],
                    **primary,
                },
                "source_snapshot": {
                    "git_head": None,
                    "files": {
                        "search_multiresolution_tle_coverage.py": seeded["engine_digest"],
                        "fast_coverage_inputs.py": seeded["loader_digest"],
                    },
                },
                "top_k_recall": None,
                "objective_gap": None,
                "resolution_progress": [
                    {
                        "spacing_km": item["spacing_km"],
                        "new_points": item["new_cell_count"],
                        "cumulative_points": item["cumulative_cell_count"],
                    }
                    for item in seeded_city["trace"]
                ],
            }
        )
    output = {
        "schema": "fast-coverage-search-benchmark/v1",
        "complete": True,
        "session_id": "scan-fw-cf510316ae7f05d5",
        "selected_track_count": 10,
        "unique_observation_count": 372,
        "primary_threshold_hz_strict_less_than": 200,
        "partition_mode": "fixed-per-track-position-independent",
        "latest_initialization_policy": {
            "maximum_search_radius_km": 500,
            "denver_historical_wide_prior_stress_only": True,
        },
        "selection_score_not_independent_test_accuracy": True,
        "runs": rows,
    }
    (HERE / "inputs" / "benchmark-summary.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
