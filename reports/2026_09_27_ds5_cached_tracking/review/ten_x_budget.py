#!/usr/bin/env python3
"""Reproduce remaining 10x CPU budgets from frozen new-data receipts."""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_budget(path: Path) -> dict:
    receipt = json.loads(path.read_text())
    groups = defaultdict(list)
    baseline = []
    attempts = Counter()
    for row in receipt["rows"]:
        cost = statistics.median(item["cpu_ms"] for item in row["candidate_times"])
        groups[row["reason"]].append(cost)
        baseline.append(statistics.median(item["cpu_ms"] for item in row["baseline_times"]))
        if row["attempted_cache"]:
            attempts[row["rate_hz"]] += 1
    base = sum(baseline)
    candidate = sum(sum(values) for values in groups.values())
    summary = receipt["summary"]["all_visits"]
    if abs(base - summary["costs"]["baseline_times"]["cpu_ms"]) > 1e-9:
        raise ValueError("baseline row accounting differs from summary")
    if abs(candidate - summary["costs"]["candidate_times"]["cpu_ms"]) > 1e-9:
        raise ValueError("candidate row accounting differs from summary")
    hit = sum(groups["cache_hit"])
    nonhit = candidate - hit
    blind_calls = summary["blind_calls"]
    target = base / 10
    return {
        "source_sha256": sha256(path), "receiver_visits": len(receipt["rows"]),
        "reasons": {name: {"count": len(values), "cpu_ms": sum(values),
                            "mean_cpu_ms": statistics.mean(values)}
                    for name, values in sorted(groups.items())},
        "cache_attempts_by_rate": {str(k): v for k, v in sorted(attempts.items())},
        "baseline_cpu_ms": base, "candidate_cpu_ms": candidate,
        "observed_speedup": base / candidate, "ten_x_budget_cpu_ms": target,
        "blind_calls": blind_calls, "accepted_hit_cpu_ms": hit,
        "nonhit_cpu_ms": nonhit,
        "maximum_speedup_if_accepted_hits_were_free": base / nonhit,
        "nonhit_budget_with_observed_hit_cost_ms": target - hit,
        "required_mean_nonhit_cpu_ms": (target - hit) / blind_calls,
        "observed_mean_nonhit_cpu_ms": nonhit / blind_calls,
        "required_nonhit_reduction_factor": (nonhit / blind_calls) / ((target - hit) / blind_calls),
    }


def main() -> None:
    v6_path = ROOT / "new_data_v6.json"
    partial_path = ROOT / "new_data_partial2.json"
    transfer_path = ROOT / "new_data" / "fft32_transfer" / "results.json"
    v6 = replay_budget(v6_path)
    partial = replay_budget(partial_path)
    if {name: v6["reasons"][name]["count"] for name in v6["reasons"]} != {
            "cache_hit": 74, "cold": 95, "expired": 35, "failed_prediction": 52}:
        raise ValueError("V6 route population differs")
    cold_expiry = sum(v6["reasons"][name]["cpu_ms"] for name in ("cold", "expired"))
    cold_expiry_count = sum(v6["reasons"][name]["count"] for name in ("cold", "expired"))

    receipt = json.loads(v6_path.read_text())
    hit_by_rate = defaultdict(list)
    acquisition_by_rate = defaultdict(list)
    acquisition_calls = Counter()
    for row in receipt["rows"]:
        cost = statistics.median(item["cpu_ms"] for item in row["candidate_times"])
        if row["reason"] == "cache_hit":
            hit_by_rate[row["rate_hz"]].append(cost)
        if row["reason"] in ("cold", "expired"):
            acquisition_by_rate[row["rate_hz"]].append(cost)
        if row["used_blind"]:
            acquisition_calls[row["rate_hz"]] += 1
    gate_proxy = sum(statistics.mean(hit_by_rate[rate]) * count
                     for rate, count in ((int(k), v) for k, v in v6["cache_attempts_by_rate"].items()))
    acquisition_proxy = sum(statistics.mean(acquisition_by_rate[rate]) * count
                            for rate, count in acquisition_calls.items()) / v6["blind_calls"]
    acquisition_budget = (v6["ten_x_budget_cpu_ms"] - gate_proxy) / v6["blind_calls"]

    transfer = json.loads(transfer_path.read_text())
    fp32 = transfer["summary"]["all"]["costs"]
    stages = {}
    for method in ("reference", "candidate"):
        native = sum(row[method]["native_total_cpu_ms"] for row in transfer["rows"])
        rank = sum(row[method]["rank_cpu_ms"] for row in transfer["rows"])
        confirm = sum(row[method]["confirmation_cpu_ms"] for row in transfer["rows"])
        stages[method] = {"native_cpu_ms": native, "rank_cpu_ms": rank,
                          "confirmation_cpu_ms": confirm,
                          "rank_fraction": rank / native,
                          "confirmation_fraction": confirm / native}
    payload = {
        "schema": "org.leo.research.ten-x-remaining-budget/v1",
        "scope": "frozen server receipts; not ARM timing or a detector qualification",
        "v6": v6, "partial2": partial,
        "v6_cold_expiry_bound": {
            "calls": cold_expiry_count, "cpu_ms": cold_expiry,
            "mean_cpu_ms": cold_expiry / cold_expiry_count,
            "maximum_speedup_if_every_other_action_were_free": v6["baseline_cpu_ms"] / cold_expiry,
            "mean_budget_if_failed_predictions_free_and_hit_cost_preserved_ms":
                (v6["ten_x_budget_cpu_ms"] - v6["accepted_hit_cpu_ms"]) / cold_expiry_count,
        },
        "v6_rate_matched_gate_proxy": {
            "warning": "Accepted-hit means proxy failed-check cost; this is a budget model, not measured stage decomposition.",
            "cache_gate_cpu_ms": gate_proxy,
            "current_blind_acquisition_proxy_mean_cpu_ms": acquisition_proxy,
            "required_blind_acquisition_mean_cpu_ms": acquisition_budget,
            "required_acquisition_reduction_factor": acquisition_proxy / acquisition_budget,
        },
        "uniform_full_coverage_engine": {
            "receiver_visits": 256,
            "ten_x_mean_cpu_budget_ms": v6["ten_x_budget_cpu_ms"] / 256,
            "qualified_fp32_blind_mean_cpu_ms": fp32["strided_candidate_cpu_ms"] / 256,
            "remaining_reduction_factor_from_fp32_blind":
                (fp32["strided_candidate_cpu_ms"] / 256) / (v6["ten_x_budget_cpu_ms"] / 256),
            "fp32_transfer_receipt_sha256": sha256(transfer_path),
            "fp32_stage_profile": stages,
        },
        "runner_sha256": sha256(Path(__file__).resolve()),
    }
    (ROOT / "review" / "ten_x_budget.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
