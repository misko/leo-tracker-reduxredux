"""Summarize reviewed physical revisits and reject corrupted transition evidence."""

import copy
import hashlib
import json
from pathlib import Path
from review_scan64_frequency_revisit_sequence import review

BASE = Path(__file__).parent
root = BASE / "scan64-revisit30-v1"
op = json.loads((root / "operator.json").read_text())
children = [
    json.loads((root / f"visit-{n}/independent-visit-review.json").read_text()) for n in range(3)
]
text = (root / "visits.txt").read_text()
sequence = review(root)
assert op["before"] == op["after"] and op["temporary_files_removed"]
assert op["serial"] == "1040005e0b100007100010000bf33a5d4d"
mutations = 0
variants = [
    (text.replace("1536-selected-observer3-scan64", "1536-selected"), children),
    (text.replace("visit after_run 0 0", "visit after_run 0 -1"), children),
]
for field, value in [("probe_sha256", "0" * 64), ("epoch_bindings", [[0, 999, 0, 0]])]:
    changed = copy.deepcopy(children)
    changed[1][field] = value
    variants.append((text, changed))
for altered, reports in variants:
    try:
        review(root, text=altered, children=reports)
    except AssertionError:
        mutations += 1
    else:
        raise AssertionError("corrupted association accepted")
timings = [t for child in children for t in child["timings"]]
result = dict(
    status="pass",
    serial=op["serial"],
    rate=op["rate"],
    lo_plan_hz=op["lo_plan_hz"],
    rf_seconds=sequence["rf_seconds"],
    mutations_rejected=mutations,
    grid_values_checked=sum(c["grid_values_checked"] for c in children),
    ranking_scores_checked=sum(c["ordering_scores_checked"] for c in children),
    resolver_hypotheses_checked=sum(c["resolver_hypotheses_checked"] for c in children),
    moment_dense_fits_checked=sum(c["moment_and_dense_fits_checked"] for c in children),
    accepted=sum(c["accepted_past_observations"] for c in children),
    native_results=sum(c["native_results"] for c in children),
    epoch_bindings=[c["epoch_bindings"] for c in children],
    scan_rank_ms=[min(t["scan_rank_ms"] for t in timings), max(t["scan_rank_ms"] for t in timings)],
    worker_ms=[min(t["worker_ms"] for t in timings), max(t["worker_ms"] for t in timings)],
    max_refill_gap_ms=max(c["max_refill_gap_ns"] for c in children) / 1e6,
    active_cdc_drops=sum(c["cdc_drops"] for c in children),
    active_pacer_drops=sum(c["pacer_drops"] for c in children),
    artifact_bytes=sum(v["bytes"] for v in op["artifacts"].values()),
    native_tracking_qualified=False,
    physical_supported_loss_reacquisition_qualified=False,
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
)
with (root / "result-summary.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(json.dumps(result, indent=2))
