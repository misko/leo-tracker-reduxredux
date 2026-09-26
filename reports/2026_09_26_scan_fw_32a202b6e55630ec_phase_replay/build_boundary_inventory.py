"""Inventory every same-target boundary using metadata and acquisition only."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    visits_path = ROOT / "capture-audit/visit-inventory.csv"
    candidates_path = ROOT / "acquisition/candidate-inventory.csv"
    with visits_path.open() as stream:
        visits = list(csv.DictReader(stream))
    candidates = defaultdict(list)
    with candidates_path.open() as stream:
        for row in csv.DictReader(stream):
            if row["passed_0p025_comparison_gate"] == "True":
                candidates[int(row["visit_index"]), int(row["receiver_id"])].append(row)
    primary = {
        key: min(
            rows, key=lambda row: (-float(row["fractional_margin"]), int(row["candidate_rank"]))
        )
        for key, rows in candidates.items()
    }
    session_start = 492145132025
    development_end = session_start + 750_000_000
    rows = []
    previous_right = None
    group = -1
    for left, right in zip(visits, visits[1:], strict=False):
        if left["target_index"] != right["target_index"]:
            continue
        a, b = int(left["visit_index"]), int(right["visit_index"])
        if a != previous_right:
            group += 1
        previous_right = b
        start = int(left["valid_start_counter"])
        end = int(right["valid_end_counter_exclusive"])
        split = (
            "development"
            if end <= development_end
            else "evaluation"
            if start >= development_end
            else "cross_split_excluded"
        )
        row = {
            "left_visit": a,
            "right_visit": b,
            "target_index": int(left["target_index"]),
            "channel": int(left["channel"]),
            "overlapping_edge_group": group,
            "split": split,
            "left_start_counter": start,
            "left_end_counter_exclusive": int(left["valid_end_counter_exclusive"]),
            "right_start_counter": int(right["valid_start_counter"]),
            "right_end_counter_exclusive": end,
            "gap_samples": int(right["valid_start_counter"])
            - int(left["valid_end_counter_exclusive"]),
        }
        keys = [(visit, rx) for visit in (a, b) for rx in (0, 1)]
        row["all_four_sparse_acquisitions_pass"] = all(key in primary for key in keys)
        for label, visit in (("left", a), ("right", b)):
            for rx in (0, 1):
                value = primary.get((visit, rx))
                row[f"{label}_rx{rx}_absolute_cfo_hz"] = (
                    float(value["tracking_absolute_baseband_cfo_hz"]) if value else None
                )
                row[f"{label}_rx{rx}_candidate_rank"] = (
                    int(value["candidate_rank"]) if value else None
                )
        rows.append(row)
    destination = ROOT / "boundary-inventory.csv"
    with destination.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    qualified = [row for row in rows if row["all_four_sparse_acquisitions_pass"]]
    summary = {
        "schema": "scan-phase-boundary-inventory/v1",
        "selection_uses_phase": False,
        "candidate_boundaries": len(rows),
        "all_four_sparse_acquisitions_pass": len(qualified),
        "qualified_by_split": dict(Counter(row["split"] for row in qualified)),
        "qualified_by_channel": dict(Counter(row["channel"] for row in qualified)),
        "qualified_overlapping_edge_groups": len(
            {row["overlapping_edge_group"] for row in qualified}
        ),
        "source_hashes": {
            str(path.relative_to(ROOT)): "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (visits_path, candidates_path)
        },
        "limitation": (
            "Same target and four passing basins do not establish same emitter or continuity. "
            "CFO/epoch/track association must precede phase scoring; "
            "groups merge edges sharing a dwell."
        ),
    }
    (ROOT / "boundary-inventory-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
