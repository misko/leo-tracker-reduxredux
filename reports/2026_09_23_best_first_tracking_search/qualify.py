#!/usr/bin/env python3
"""Verify frozen best-first runs and build a compact report summary."""

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "inputs" / "runs"
CONFIGS = {
    "exact-centre": "best-first-search-exact-centre-v1",
    "parent-linear": "best-first-search-parent-linear-v1",
}


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def main():
    reference = read(HERE / "inputs" / "evaluation-reference.json")
    compaction = read(HERE / "inputs" / "compaction-receipt.json")
    compact_rows = {(row["run"], row["city"]): row for row in compaction["rows"]}
    rows = []
    for mode, name in CONFIGS.items():
        root = RUNS / name
        execution = read(root / "summary.json")
        assert execution["execution_complete"] is True
        assert execution["input_provenance"]["selected_track_count"] == 34
        assert execution["input_provenance"]["unique_observation_count"] == 750
        for source, expected in execution["source_snapshot"]["files"].items():
            assert digest(root / "source" / source) == expected
        for receipt in execution["runs"]:
            result_path = root / receipt["city"] / "result.compact.json"
            result = read(result_path)
            assert result["original_full_result_digest"] == receipt["result_digest"]
            compact = compact_rows[(name, receipt["city"])]
            assert compact["original_result_digest"] == receipt["result_digest"]
            assert compact["compact_result_digest"] == digest(result_path)
            assert result["execution_complete"] is True
            assert result["search_complete"] is False
            assert result["result_guarantee"] == "budget-bounded-incomplete"
            selected = result["final_lattice_selection"]
            rows.append(
                {
                    "city": receipt["city"],
                    "priority_mode": mode,
                    "search_s": result["search_s"],
                    "evaluated_points": result["search"]["metrics"]["evaluated_point_count"],
                    "finest_point_count": len(result["search"]["finest_evaluations"]),
                    "selected": selected,
                    "selected_diagnostics": result["final_lattice_diagnostics"],
                    "postselection_distance_km": distance_km(
                        selected["metadata"]["latitude_deg"],
                        selected["metadata"]["longitude_deg"],
                        reference["latitude_deg"],
                        reference["longitude_deg"],
                    ),
                    "validation": result["exact_validation"],
                    "trace": result["search"]["trace"],
                    "priority_metrics": result["priority_metrics"],
                    "compact_result_digest": digest(result_path),
                }
            )
    evidence = RUNS / CONFIGS["parent-linear"] / "frozen-track-evidence.json"
    linear_execution = read(RUNS / CONFIGS["parent-linear"] / "summary.json")
    assert digest(evidence) == linear_execution["frozen_track_evidence_digest"]
    frozen = read(evidence)
    assert len(frozen["tracks"]) == 34
    assert all(row["span_s"] >= 3 and len(row["observation_ids"]) >= 6 for row in frozen["tracks"])
    output = {
        "schema": "best-first-tracking-search-report/v1",
        "session_id": "scan-fw-cf510316ae7f05d5",
        "execution_complete": True,
        "search_complete": False,
        "track_count": 34,
        "unique_observation_count": 750,
        "radius_km": 500,
        "budget_points": 400,
        "rows": rows,
    }
    (HERE / "summary.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
