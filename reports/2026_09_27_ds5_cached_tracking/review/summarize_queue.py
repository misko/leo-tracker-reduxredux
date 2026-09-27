#!/usr/bin/env python3
"""Summarize a frozen dev replay as serialized physical-visit queue service."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics

import numpy as np


HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
REPLAY = REPORT / "dev_direct_v3.json"
DATASET = REPORT / "dataset/cases.json"
OUTPUT = HERE / "queue_dev_direct_v3.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    array = np.asarray(values, dtype=np.float64)
    return {
        "p50": float(np.percentile(array, 50, method="linear")),
        "p95": float(np.percentile(array, 95, method="linear")),
        "p99": float(np.percentile(array, 99, method="linear")),
        "maximum": float(np.max(array)),
        "mean": float(np.mean(array)),
    }


def receiver_median(row: dict, side: str, metric: str) -> float:
    values = row[side]
    if len(values) < 3:
        raise ValueError("queue summary requires at least three timing repetitions")
    samples = [float(value[metric]) for value in values]
    if not all(np.isfinite(samples)):
        raise ValueError("nonfinite receiver timing")
    return statistics.median(samples)


def queue_model(visits: list[dict], side: str, metric: str) -> dict:
    by_session: dict[str, list[dict]] = defaultdict(list)
    for visit in visits:
        by_session[visit["session_id"]].append(visit)
    service_values: list[float] = []
    wait_values: list[float] = []
    age_values: list[float] = []
    gap_values: list[float] = []
    deadline_misses = 0
    session_rows = []
    for session, rows in sorted(by_session.items()):
        rows.sort(key=lambda row: (row["arrival_seconds"], row["visit_index"]))
        origin = rows[0]["arrival_seconds"]
        completion = 0.0
        total_service = 0.0
        for index, row in enumerate(rows):
            arrival = row["arrival_seconds"] - origin
            service_ms = row[f"{side}_{metric}_ms"]
            service_seconds = service_ms / 1000.0
            wait_ms = max(0.0, completion - arrival) * 1000.0
            completion = max(completion, arrival) + service_seconds
            age_ms = (completion - arrival) * 1000.0
            service_values.append(service_ms)
            wait_values.append(wait_ms)
            age_values.append(age_ms)
            total_service += service_seconds
            if index + 1 < len(rows):
                next_arrival = rows[index + 1]["arrival_seconds"] - origin
                gap_ms = (next_arrival - arrival) * 1000.0
                if gap_ms <= 0:
                    raise ValueError("source arrivals must increase within a session")
                gap_values.append(gap_ms)
                deadline_misses += completion > next_arrival
        horizon = rows[-1]["arrival_seconds"] - rows[0]["arrival_seconds"]
        session_rows.append(
            {
                "session_id": session,
                "rate_hz": rows[0]["rate_hz"],
                "physical_visits": len(rows),
                "arrival_horizon_seconds": horizon,
                "serialized_service_seconds": total_service,
                "service_to_arrival_horizon": total_service / horizon if horizon else None,
            }
        )
    return {
        "model": "one serialized server worker; both receiver medians summed per physical visit",
        "clock": metric,
        "processing_service_ms": quantiles(service_values),
        "queue_wait_backlog_ms": quantiles(wait_values),
        "capture_complete_to_decision_ms": quantiles(age_values),
        "capture_complete_interarrival_ms": quantiles(gap_values),
        "next_arrival_deadline_misses": deadline_misses,
        "eligible_next_arrival_deadlines": len(gap_values),
        "sessions": session_rows,
    }


def run() -> dict:
    replay = json.loads(REPLAY.read_text())
    dataset = json.loads(DATASET.read_text())
    if replay["split"] != "dev" or replay["dataset_sha256"] != sha256(DATASET):
        raise ValueError("replay is not associated with the current development dataset")
    expected = {
        case["case_id"]: case for case in dataset["cases"] if case["split"] == "dev"
    }
    rows_by_case: dict[str, list[dict]] = defaultdict(list)
    for row in replay["rows"]:
        if row["case_id"] not in expected or row["rx"] not in (0, 1):
            raise ValueError("unexpected replay row")
        rows_by_case[row["case_id"]].append(row)
    visits = []
    skipped = []
    for case_id, case in sorted(
        expected.items(), key=lambda item: (item[1]["session_id"], item[1]["visit_index"])
    ):
        rows = rows_by_case.get(case_id, [])
        if len(rows) != 2 or {row["rx"] for row in rows} != {0, 1}:
            skipped.append(
                {
                    "case_id": case_id,
                    "status": "unprocessed_unknown",
                    "receiver_rows": len(rows),
                }
            )
            continue
        for row in rows:
            if (
                row["session_id"] != case["session_id"]
                or row["start_counter"] != case["source_start_counter"]
                or row["end_counter"] != case["source_end_counter_exclusive"]
                or row["rate_hz"] != case["rate_hz"]
            ):
                raise ValueError("replay row source association mismatch")
        visit = {
            "case_id": case_id,
            "session_id": case["session_id"],
            "visit_index": case["visit_index"],
            "rate_hz": case["rate_hz"],
            "arrival_seconds": case["source_end_counter_exclusive"] / case["rate_hz"],
        }
        for side in ("baseline_times", "candidate_times"):
            label = "baseline" if side == "baseline_times" else "candidate"
            for metric in ("cpu_ms", "wall_ms"):
                visit[f"{label}_{metric}"] = sum(
                    receiver_median(row, side, metric) for row in rows
                )
        visits.append(visit)
    if len(visits) + len(skipped) != len(expected):
        raise ValueError("physical visit inventory mismatch")

    paired_hits = [row for row in replay["rows"] if not row["used_blind"]]
    rate_bounds = {}
    for rate in sorted({row["rate_hz"] for row in replay["rows"]}):
        all_rate = [row for row in replay["rows"] if row["rate_hz"] == rate]
        hits = [row for row in paired_hits if row["rate_hz"] == rate]
        baseline_mean = statistics.mean(
            receiver_median(row, "baseline_times", "cpu_ms") for row in all_rate
        )
        if hits:
            paired_baseline = sum(
                receiver_median(row, "baseline_times", "cpu_ms") for row in hits
            )
            paired_fast = sum(
                receiver_median(row, "candidate_times", "cpu_ms") for row in hits
            )
            hit_fraction = paired_fast / paired_baseline
            replacement_route_limit = (
                (0.1 - hit_fraction) / (1.0 - hit_fraction)
                if hit_fraction < 0.1
                else None
            )
            additive_route_limit = max(0.0, 0.1 - hit_fraction)
        else:
            paired_baseline = paired_fast = hit_fraction = None
            replacement_route_limit = additive_route_limit = None
        rate_bounds[str(rate)] = {
            "reference_receiver_mean_cpu_ms": baseline_mean,
            "observed_accepted_fast_receiver_cases": len(hits),
            "paired_accepted_fast_reference_cpu_ms": paired_baseline,
            "paired_accepted_fast_candidate_cpu_ms": paired_fast,
            "paired_hit_normalized_cost": hit_fraction,
            "maximum_baseline_cost_route_fraction_if_fast_replaces_blind": replacement_route_limit,
            "maximum_downstream_blind_route_fraction_if_fast_runs_on_every_visit": additive_route_limit,
            "ten_x_feasible_with_observed_full_aperture_fast_cost": bool(
                hit_fraction is not None and hit_fraction < 0.1
            ),
        }

    return {
        "schema": "org.leo.research.cached-tracking-queue-summary/v1",
        "scope": "development server replay; not ARM or production realtime qualification",
        "source": {
            "replay_path": str(REPLAY.relative_to(REPORT)),
            "replay_sha256": sha256(REPLAY),
            "dataset_sha256": sha256(DATASET),
            "script_sha256": sha256(Path(__file__)),
        },
        "accounting": {
            "expected_physical_visits": len(expected),
            "processed_physical_visits": len(visits),
            "processed_receiver_visits": len(visits) * 2,
            "skipped_unknown_physical_visits": len(skipped),
            "skipped": skipped,
            "arrival_definition": "source_end_counter_exclusive/rate_hz; queue resets per session",
            "capture_duration_excluded_from_processing_service": True,
        },
        "queue": {
            side: {
                metric: queue_model(visits, side, metric)
                for metric in ("cpu", "wall")
            }
            for side in ("baseline", "candidate")
        },
        "ten_x_fast_gate_bounds": {
            "formula_replacement": "f <= (0.1-h)/(1-h), for fast-or-blind normalized hit cost h",
            "formula_additive": "r <= 0.1-h, when every visit pays fast gate h and routed visits add one baseline cost",
            "rate_matched": rate_bounds,
            "warning": "No 5 MS/s accepted fast cases exist in this development replay; do not transfer the 2.5 MS/s cost ratio.",
        },
    }


if __name__ == "__main__":
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    result = run()
    OUTPUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"accounting": result["accounting"], "queue": result["queue"],
                      "ten_x_fast_gate_bounds": result["ten_x_fast_gate_bounds"]}, indent=2))
