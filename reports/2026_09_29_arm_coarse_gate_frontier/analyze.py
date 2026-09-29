#!/usr/bin/env python3
"""Exploratory coarse-only candidate-gate frontier on the frozen Wave4 rows."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
COHORT = REPORTS / "2026_09_29_arm_wave4_combined" / "host704"
BASELINE = REPORTS / "2026_09_28_ds7_large_arm" / "baseline-01" / "rows.jsonl"
MATCHER = REPORTS / "2026_09_28_arm_full_optimization" / "independent_summary.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


spec = importlib.util.spec_from_file_location("frozen_matcher", MATCHER)
frozen = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(frozen)


def candidate_rate(selected: list[dict]) -> dict[tuple[str, int], int]:
    return {(x["session_id"], x["visit_index"]): int(x["rate_hz"]) for x in selected}


def apply(native: dict, rates: dict, keep) -> tuple[dict, int, dict[str, int]]:
    gated = copy.deepcopy(native)
    retained = 0
    by_rate: dict[str, int] = {}
    for case, windows in gated.items():
        rate = rates[case]
        bucket = str(rate)
        for row in windows.values():
            original = row["candidates"]
            row["candidates"] = [c for index, c in enumerate(original) if keep(original, index, rate)]
            row["candidate_count"] = len(row["candidates"])
            retained += len(row["candidates"])
            by_rate[bucket] = by_rate.get(bucket, 0) + len(row["candidates"])
            for candidate in row["candidates"]:
                candidate["epoch"] = candidate["refined_epoch"]
    return gated, retained, by_rate


def evaluate(name: str, native: dict, rates: dict, selected: list[dict], baseline: dict, keep, detail: dict) -> dict:
    gated, retained, emitted_by_rate = apply(native, rates, keep)
    quality = frozen.summarize(selected, baseline, gated)
    return {
        "name": name,
        "runtime_fields": detail,
        "emitted_candidate_entries": retained,
        "removed_candidate_entries": 123904 - retained,
        "emitted_by_rate": emitted_by_rate,
        "quality": quality,
        "possible_pre_cache_fine_calls": retained,
        "possible_pre_cache_glrt_calls": retained,
        "note": "Each emitted Wave4 candidate reaches fine preparation and final GLRT. "
                "The observed GLRT-cache and boundary-fallback call totals cannot be recomputed "
                "from candidate rows after removal, so this is not a timing or exact physical-call claim.",
    }


def main() -> None:
    manifest = json.loads((COHORT / "manifest.json").read_text())
    assert manifest["complete"] and len(manifest["selected"]) == 704
    selected = manifest["selected"]
    native = frozen.load_native(COHORT / "rows.jsonl")
    baseline = frozen.load_baseline(BASELINE)
    rates = candidate_rate(selected)
    baseline_quality = frozen.summarize(selected, baseline, native)
    results: list[dict] = []

    for threshold in [0.15 + step * 0.001 for step in range(26)]:
        results.append(evaluate("absolute", native, rates, selected, baseline,
            lambda row, index, rate, t=threshold: row[index]["coarse_score"] >= t,
            {"coarse_score_gte": round(threshold, 3)}))
    for maximum_rank in range(4, 9):
        results.append(evaluate("rank", native, rates, selected, baseline,
            lambda row, index, rate, n=maximum_rank: index < n,
            {"coarse_rank_lt": maximum_rank}))
    for ratio in [0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]:
        results.append(evaluate("ratio", native, rates, selected, baseline,
            lambda row, index, rate, q=ratio: row[index]["coarse_score"] >= q * row[0]["coarse_score"],
            {"coarse_score_over_window_max_gte": ratio}))
    for threshold in [0.15, 0.155, 0.16, 0.165, 0.17]:
        for maximum_rank in [6, 7]:
            results.append(evaluate("absolute_and_rank", native, rates, selected, baseline,
                lambda row, index, rate, t=threshold, n=maximum_rank:
                    index < n and row[index]["coarse_score"] >= t,
                {"coarse_score_gte": threshold, "coarse_rank_lt": maximum_rank}))

    # This calibration deliberately uses these same 704 rows. It is reported
    # as exploratory selection, never as a holdout result.
    thresholds_by_rate = {}
    for rate in sorted(set(rates.values())):
        target = baseline_quality["by_rate"][str(rate)]["recovered_positive_hits"]
        candidates = []
        for threshold in [0.15 + step * 0.001 for step in range(26)]:
            value = evaluate("rate_probe", native, rates, selected, baseline,
                lambda row, index, row_rate, t=threshold, chosen=rate:
                    row_rate != chosen or row[index]["coarse_score"] >= t,
                {"rate_hz": rate, "coarse_score_gte": round(threshold, 3)})
            if value["quality"]["by_rate"][str(rate)]["recovered_positive_hits"] == target:
                candidates.append((value["emitted_by_rate"][str(rate)], threshold))
        thresholds_by_rate[str(rate)] = min(candidates)[1] if candidates else 0.15
    results.append(evaluate("per_rate_absolute", native, rates, selected, baseline,
        lambda row, index, rate: row[index]["coarse_score"] >= thresholds_by_rate[str(rate)],
        {"coarse_score_gte_by_rate": thresholds_by_rate}))

    # Intra-window duplicate removal uses only the coarse epoch/bin identity;
    # retain the first rank because the row is already descending coarse score.
    results.append(evaluate("absolute_and_duplicate", native, rates, selected, baseline,
        lambda row, index, rate: row[index]["coarse_score"] >= 0.15 and
            not any((row[j]["coarse_epoch"], row[j]["coarse_bin"]) ==
                    (row[index]["coarse_epoch"], row[index]["coarse_bin"]) for j in range(index)),
        {"coarse_score_gte": 0.15, "first_per_coarse_epoch_bin": True}))

    # Keep a compact Pareto table: minimum emitted inventory for each recovered
    # hit count, across the intentionally small, interpretable policy grid.
    frontier = []
    best = None
    for result in sorted(results, key=lambda x: x["emitted_candidate_entries"]):
        recovered = result["quality"]["totals"]["recovered_positive_hits"]
        if best is None or recovered > best:
            frontier.append(result)
            best = recovered
    output = {
        "schema": "arm-coarse-gate-frontier/v1",
        "scope": "offline exploratory training analysis; no holdout, runtime, ARM, or implementation claim",
        "cohort": {"manifest_sha256": sha(COHORT / "manifest.json"), "rows_sha256": sha(COHORT / "rows.jsonl")},
        "baseline_sha256": sha(BASELINE),
        "matcher_sha256": sha(MATCHER),
        "analysis_sha256": sha(Path(__file__)),
        "baseline_observed_calls": {
            "candidate_entries_and_fine_precision_calls": 123904,
            "actual_executed_glrt_calls": sum(row["actual_executed_glrt_calls"] for windows in native.values() for row in windows.values()),
            "glrt_cache_hits": sum(row["glrt_cache_hits"] for windows in native.values() for row in windows.values()),
            "conditioned_boundary_fallback_candidates": sum(c["conditioned_fallback"] for windows in native.values() for row in windows.values() for c in row["candidates"]),
        },
        "baseline_quality": baseline_quality,
        "per_rate_thresholds_selected_on_this_cohort": thresholds_by_rate,
        "results": results,
        "pareto_frontier": frontier,
    }
    (HERE / "results.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
