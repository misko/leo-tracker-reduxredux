"""Audit exact original-baseline scientific accounting."""

import argparse
from collections import Counter
import json
from pathlib import Path


def blank():
    return Counter(dwells=0, confirmed_dwells=0, receiver_windows=0,
                   positive_receiver_windows=0, candidate_entries=0,
                   positive_candidates=0)


parser = argparse.ArgumentParser()
parser.add_argument("run", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
receipt = json.loads((args.run / "run.json").read_text())
totals = blank()
rates = {}
reasons = Counter()
edges = Counter()
targets = Counter()
window_geometry_valid = True
gate_field_mismatches = 0
exact_gate_values = 0
rows = []
for line in (args.run / "rows.jsonl").read_text().splitlines():
    row = json.loads(line)
    if row["status"] != "ok":
        raise ValueError("failed baseline row")
    rows.append(row)
    rate = str(row["context"]["rate_hz"])
    bucket = rates.setdefault(rate, blank())
    for counter in (totals, bucket):
        counter["dwells"] += 1
        counter["confirmed_dwells"] += row["result"]["first"] is not None
    reasons[row["result"]["reason"]] += 1
    edges[row["context"]["target"]["edge"]] += 1
    targets[str(row["context"]["target_index"])] += 1
    probes = row["result"]["probes"]
    actual_geometry = sorted((p["receiver_id"], p["probe_start_ms"]) for p in probes)
    expected_geometry = [(receiver, start) for receiver in (0, 1) for start in range(0, 101, 10)]
    window_geometry_valid &= actual_geometry == expected_geometry
    for probe in probes:
        positive_window = any(c["passed_margin_gate"] for c in probe["candidates"])
        for counter in (totals, bucket):
            counter["receiver_windows"] += 1
            counter["positive_receiver_windows"] += positive_window
        for candidate in probe["candidates"]:
            passed_exact = candidate["margin"] >= 0.025
            gate_field_mismatches += passed_exact != candidate["passed_margin_gate"]
            exact_gate_values += candidate["margin"] == 0.025
            for counter in (totals, bucket):
                counter["candidate_entries"] += 1
                counter["positive_candidates"] += candidate["passed_margin_gate"]

summary = {
    "schema": "ds7-large-arm-baseline-summary/v1",
    "run_complete": receipt["complete"], "sources_unchanged": receipt["sources_unchanged"],
    "planned_calls": receipt["planned_calls"], "calls": receipt["calls"],
    "failed_calls": receipt["failed_calls"], "totals": dict(totals),
    "by_sample_rate_hz": {key: dict(value) for key, value in sorted(rates.items())},
    "reason_counts": dict(reasons), "target_edge_counts": dict(edges),
    "target_index_counts": dict(targets),
    "all_dwells_have_exact_22_window_geometry": window_geometry_valid,
    "window_starts_ms_per_receiver": list(range(0, 101, 10)),
    "margin_gate": 0.025, "gate_field_mismatches": gate_field_mismatches,
    "candidate_margins_exactly_equal_to_gate": exact_gate_values,
}
if len(rows) != 704 or totals["candidate_entries"] != 704 * 22 * 8:
    raise ValueError("baseline accounting")
args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
