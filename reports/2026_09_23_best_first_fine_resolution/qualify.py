#!/usr/bin/env python3
"""Verify and normalize the frozen fine-resolution search comparison."""

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "inputs" / "runs"
CONFIGS = {
    "12.5 km / 400": "best-first-search-exact-centre-v1",
    "6.25 km / 400": "best-first-search-exact-centre-6p25-budget400-v1",
    "6.25 km / 800": "best-first-search-exact-centre-6p25-budget800-v1",
}


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def main():
    reference = read(HERE / "inputs" / "evaluation-reference.json")
    receipt = read(HERE / "inputs" / "compaction-receipt.json")
    compact = {(row["run"], row["city"]): row for row in receipt["rows"]}
    rows = []
    for label, name in CONFIGS.items():
        root = RUNS / name
        execution = read(root / "summary.json")
        assert execution["execution_complete"] is True
        assert execution["input_provenance"]["selected_track_count"] == 34
        assert execution["input_provenance"]["unique_observation_count"] == 750
        for source, expected in execution["source_snapshot"]["files"].items():
            assert digest(root / "source" / source) == expected
        if "frozen_track_evidence_digest" in execution:
            assert (
                digest(root / "frozen-track-evidence.json")
                == execution["frozen_track_evidence_digest"]
            )
        for run in execution["runs"]:
            path = root / run["city"] / "result.compact.json"
            result = read(path)
            bound = compact[(name, run["city"])]
            assert bound["original_result_digest"] == run["result_digest"]
            assert bound["compact_result_digest"] == digest(path)
            assert result["search_complete"] is False
            selected = result["final_lattice_selection"]
            rows.append(
                {
                    "label": label,
                    "city": run["city"],
                    "search_s": result["search_s"],
                    "evaluated_points": result["search"]["metrics"]["evaluated_point_count"],
                    "finest_points": len(result["search"]["finest_evaluations"]),
                    "global_incumbent": result["search"]["best"],
                    "finest_selection": selected,
                    "postselection_distance_km": distance_km(
                        selected["metadata"]["latitude_deg"],
                        selected["metadata"]["longitude_deg"],
                        reference["latitude_deg"],
                        reference["longitude_deg"],
                    ),
                    "trace": result["search"]["trace"],
                    "validation": result["exact_validation"],
                }
            )
    output = {
        "schema": "best-first-fine-resolution-report/v1",
        "execution_complete": True,
        "search_complete": False,
        "full_6p25_in_circle_lattice_count": 20108,
        "rows": rows,
    }
    (HERE / "summary.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
