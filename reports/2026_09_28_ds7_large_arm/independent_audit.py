"""Independent simple-window audit of the frozen original and ARM DS7 rows."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs.json"
BASELINE_ROWS = HERE / "baseline-01/rows.jsonl"
BASELINE_RUN = HERE / "baseline-01/run.json"
ARM_ROWS = HERE / "arm03/rows.jsonl"
ARM_RUN = HERE / "arm03/run.json"
OUTPUT = HERE / "INDEPENDENT_AUDIT.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def case_id(context: dict) -> str:
    return f'ds7-{context["session_id"]}-v{context["visit_index"]}'


def new_counts() -> Counter:
    return Counter(cases=0, baseline_positive_windows=0, arm_ranked_windows=0,
                   arm_executed_windows=0, arm_positive_windows=0, arm_positive_candidates=0,
                   baseline_positive_windows_arm_selected=0,
                   baseline_positive_windows_executed=0,
                   baseline_positive_windows_positive_again=0,
                   baseline_positive_windows_identity_recovered=0,
                   baseline_positive_candidates=0,
                   baseline_positive_candidates_arm_selected=0,
                   baseline_positive_candidates_executed=0,
                   baseline_positive_candidate_identity_hits=0,
                   baseline_positive_candidate_many_to_one_associations=0,
                   baseline_positive_candidate_identity_misses_executed=0,
                   baseline_positive_candidate_identity_misses_all=0)


inputs = json.loads(INPUTS.read_text())
baseline_run = json.loads(BASELINE_RUN.read_text())
arm_run = json.loads(ARM_RUN.read_text())
baseline_rows = read_rows(BASELINE_ROWS)
arm_rows = read_rows(ARM_ROWS)
assert inputs["complete"] and len(inputs["rows"]) == 704
assert baseline_run["complete"] and baseline_run["calls"] == 704 and baseline_run["failed_calls"] == 0
assert arm_run["complete"] and arm_run["calls"] == 704 and arm_run["failed_calls"] == 0
assert baseline_run["input_manifest_sha256"] == arm_run["input_manifest_sha256"] == sha(INPUTS)
assert arm_run["rows_sha256"] == sha(ARM_ROWS)

context_by_case = {case_id(row): row for row in inputs["rows"]}
assert len(context_by_case) == 704

baseline: dict[tuple[str, int, int], list[dict]] = {}
baseline_cases = set()
for row in baseline_rows:
    context = row["context"]
    key = case_id(context)
    assert row["status"] == "ok" and context == context_by_case[key]
    assert key not in baseline_cases
    baseline_cases.add(key)
    geometry = set()
    for probe in row["result"]["probes"]:
        window = (key, probe["receiver_id"], probe["probe_start_ms"])
        assert window not in baseline
        geometry.add((probe["receiver_id"], probe["probe_start_ms"]))
        for candidate in probe["candidates"]:
            assert candidate["passed_margin_gate"] == (candidate["margin"] >= 0.025)
        baseline[window] = [candidate for candidate in probe["candidates"]
                            if candidate["passed_margin_gate"]]
    assert geometry == {(receiver, start) for receiver in (0, 1) for start in range(0, 101, 10)}

ranked = set()
executed = set()
arm_positive: dict[tuple[str, int, int], dict] = {}
arm_cases = set()
for row in arm_rows:
    key = row["case_id"]
    assert row["type"] == "job" and row["status"] == "processed"
    assert key in context_by_case and key not in arm_cases
    arm_cases.add(key)
    assert {entry["receiver"] for entry in row["receivers"]} == {0, 1}
    for entry in row["receivers"]:
        receiver = entry["receiver"]
        result = entry["result"]
        order = result["rank"]["order"]
        assert sorted(order) == list(range(6))
        ranked.update((key, receiver, bit * 20) for bit in order)
        bits = [bit for bit in range(6) if result["confirmation_window_mask"] & (1 << bit)]
        assert len(bits) == result["confirmation_count"] == len(result["confirmations"])
        assert len(bits) <= 1
        for bit, confirmation in zip(bits, result["confirmations"]):
            candidates = confirmation["candidates"]
            # This makes a direct any-match audit unambiguous: an executed ARM
            # receiver-window carries at most one candidate.
            assert confirmation["candidate_count"] == len(candidates) <= 1
            window = (key, receiver, bit * 20)
            assert window in ranked and window not in executed
            executed.add(window)
            if candidates:
                candidate = candidates[0]
                if bool(candidate["fractional_complete"]) and candidate["margin"] > 0.025:
                    arm_positive[window] = candidate

assert baseline_cases == arm_cases == set(context_by_case)
baseline_positive = {window: candidates for window, candidates in baseline.items() if candidates}


def summarize(cases: set[str]) -> dict:
    counts = new_counts()
    counts["cases"] = len(cases)
    selected_windows = {window for window in ranked if window[0] in cases}
    executed_windows = {window for window in executed if window[0] in cases}
    positive_arm_windows = {window for window in arm_positive if window[0] in cases}
    positive_baseline = {window: values for window, values in baseline_positive.items()
                         if window[0] in cases}
    counts["arm_ranked_windows"] = len(selected_windows)
    counts["arm_executed_windows"] = len(executed_windows)
    counts["arm_positive_windows"] = len(positive_arm_windows)
    counts["arm_positive_candidates"] = len(positive_arm_windows)
    counts["baseline_positive_windows"] = len(positive_baseline)
    counts["baseline_positive_candidates"] = sum(len(values) for values in positive_baseline.values())
    counts["baseline_positive_windows_arm_selected"] = len(set(positive_baseline) & selected_windows)
    counts["baseline_positive_candidates_arm_selected"] = sum(
        len(positive_baseline[w]) for w in set(positive_baseline) & selected_windows
    )
    evaluated = set(positive_baseline) & executed_windows
    counts["baseline_positive_windows_executed"] = len(evaluated)
    counts["baseline_positive_candidates_executed"] = sum(len(positive_baseline[w]) for w in evaluated)
    counts["baseline_positive_windows_positive_again"] = len(set(positive_baseline) & positive_arm_windows)
    many_to_one_associations = 0
    identity_windows = 0
    for window in evaluated:
        arm_candidate = arm_positive.get(window)
        hits = 0
        if arm_candidate is not None:
            rate = context_by_case[window[0]]["rate_hz"]
            arm_epoch = arm_candidate["epoch"] + arm_candidate["fractional_offset_samples"]
            for original in positive_baseline[window]:
                timing_us = abs(original["epoch_sample"] - arm_epoch) / rate * 1e6
                cfo_hz = abs(original["tracking_cfo_hz"] - arm_candidate["tracking_cfo_hz"])
                hits += timing_us <= 2.0 and cfo_hz <= 8000.0
        many_to_one_associations += hits
        identity_windows += hits > 0
    counts["baseline_positive_windows_identity_recovered"] = identity_windows
    # There is at most one ARM candidate per window. Under the frozen one-to-one
    # rule it can recover at most one original candidate, even when several
    # duplicate original hypotheses pass the identity gates.
    counts["baseline_positive_candidate_identity_hits"] = identity_windows
    counts["baseline_positive_candidate_many_to_one_associations"] = many_to_one_associations
    counts["baseline_positive_candidate_identity_misses_executed"] = (
        counts["baseline_positive_candidates_executed"] - identity_windows
    )
    counts["baseline_positive_candidate_identity_misses_all"] = (
        counts["baseline_positive_candidates"] - identity_windows
    )
    return dict(counts)


rates = sorted({row["rate_hz"] for row in inputs["rows"]})
document = {
    "schema": "ds7-large-arm-independent-audit/v1",
    "method": "direct per-window any-match against the sole ARM confirmation candidate",
    "gates": {"baseline_positive": "margin >= 0.025", "arm_positive": "fractional_complete and margin > 0.025",
              "timing_us_inclusive": 2.0, "tracking_cfo_hz_inclusive": 8000.0},
    "source_sha256": {str(path.relative_to(HERE)): sha(path) for path in
                      (INPUTS, BASELINE_ROWS, BASELINE_RUN, ARM_ROWS, ARM_RUN, Path(__file__))},
    "assertions": {"cases_complete_unique": True, "baseline_exact_22_windows_per_case": True,
                   "arm_at_most_one_candidate_per_executed_window": True,
                   "arm_rows_match_run_receipt": True, "shared_input_manifest": True},
    "totals": summarize(set(context_by_case)),
    "per_rate_hz": {str(rate): summarize({key for key, context in context_by_case.items()
                                           if context["rate_hz"] == rate}) for rate in rates},
}
OUTPUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
print(json.dumps(document["totals"], sort_keys=True))
