"""Offline admission model: saved public evidence, no IQ/radio/detector writes.

Measured worker wall costs are scenarios, not costs measured for skipped dwells.
No verdict is inferred for counterfactually admitted or skipped dwells.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Visit:
    number: int
    target: int
    ready_ms: float


@dataclass(frozen=True)
class Check:
    visit: int
    target: int
    ready_ms: float
    started_ms: float
    completed_ms: float


POLICIES = (
    "immediate",
    "every_2",
    "every_3",
    "oldest_target_one_pending",
    "freshness_guard_one_pending",
)


def simulate(visits, cost_ms, policy, *, maximum_queue_age_ms=120.0, freshness_limit_ms=2500.0):
    """One non-preemptive worker, at most one pending complete dwell.

    Completions precede simultaneous arrivals. Ties retain the older pending
    dwell. Fairness ranks last dispatch including the running check. Expired
    pending work is dropped, never converted to negative detector evidence.
    """
    if policy not in POLICIES or not math.isfinite(cost_ms) or cost_ms <= 0:
        raise ValueError("invalid policy or service time")
    if not math.isfinite(maximum_queue_age_ms) or maximum_queue_age_ms < 0:
        raise ValueError("invalid queue age")
    if not math.isfinite(freshness_limit_ms) or freshness_limit_ms <= 0:
        raise ValueError("invalid freshness limit")
    if any(
        v.number != i
        or not 0 <= v.target < 8
        or not math.isfinite(v.ready_ms)
        or v.ready_ms < 0
        or (i and v.ready_ms <= visits[i - 1].ready_ms)
        for i, v in enumerate(visits)
    ):
        raise ValueError("visits must have contiguous identities and increasing ready times")
    last_started = [-math.inf] * 8
    last_ready = [-math.inf] * 8
    seen = set()
    checks = []
    running_until = None
    pending = None
    pressure_until = -math.inf

    def eligible(visit, now):
        if policy != "freshness_guard_one_pending" or now >= pressure_until:
            return True
        overdue = {target for target in seen if now - last_ready[target] >= freshness_limit_ms}
        return not overdue or visit.target in overdue

    def dispatch(visit, now):
        nonlocal running_until
        running_until = now + cost_ms
        last_started[visit.target] = now
        last_ready[visit.target] = visit.ready_ms
        checks.append(Check(visit.number, visit.target, visit.ready_ms, now, running_until))

    for visit in visits:
        if running_until is not None and running_until <= visit.ready_ms:
            completed = running_until
            running_until = None
            if pending is not None:
                if completed - pending.ready_ms <= maximum_queue_age_ms and eligible(
                    pending, completed
                ):
                    dispatch(pending, completed)
                pending = None
            if running_until is not None and running_until <= visit.ready_ms:
                running_until = None
        seen.add(visit.target)
        if policy.startswith("every_") and visit.number % int(policy[-1]):
            continue
        if running_until is None:
            if eligible(visit, visit.ready_ms):
                dispatch(visit, visit.ready_ms)
        elif policy in ("oldest_target_one_pending", "freshness_guard_one_pending"):
            pressure_until = visit.ready_ms + freshness_limit_ms
            if pending is not None and visit.ready_ms - pending.ready_ms > maximum_queue_age_ms:
                pending = None
            if pending is None or last_started[visit.target] < last_started[pending.target]:
                pending = visit
    if pending is not None:
        assert running_until is not None
        if running_until - pending.ready_ms <= maximum_queue_age_ms and eligible(
            pending, running_until
        ):
            dispatch(pending, running_until)
    return checks


def summarize(visits, checked_ids):
    checked = set(checked_ids)
    if len(checked) != len(checked_ids) or not checked <= {v.number for v in visits}:
        raise ValueError("duplicate or foreign check")
    span = visits[-1].ready_ms if visits else 0.0
    targets = []
    for target in range(8):
        available = [v for v in visits if v.target == target]
        retained = [v.ready_ms for v in available if v.number in checked]
        boundaries = [0.0, *retained, span]
        targets.append(
            {
                "target": target,
                "visits": len(available),
                "screened": len(retained),
                "screening_percent": 100 * len(retained) / len(available) if available else None,
                "maximum_source_screen_gap_ms": max(
                    b - a for a, b in zip(boundaries, boundaries[1:], strict=False)
                ),
            }
        )
    return {
        "visits": len(visits),
        "screened": len(checked),
        "screening_percent": 100 * len(checked) / len(visits) if visits else 0.0,
        "unvisited_targets": [r["target"] for r in targets if not r["visits"]],
        "starved_targets": [r["target"] for r in targets if r["visits"] and not r["screened"]],
        "per_target": targets,
    }


def evaluate(snapshot):
    publication = snapshot["responses"]["glrt"]["body"]
    capture = snapshot["responses"]["detail"]["body"]["capture"]
    evidence = publication["evidence"]
    rows = evidence["results"]
    expected = capture.get("visit_count", capture.get("retained_visits"))
    if (
        publication["session_id"] != capture["session_id"]
        or publication["error"] is not None
        or evidence["error"] is not None
        or not evidence["delivery_complete"]
        or evidence["dropped_results"]
        or len(rows) != expected
        or len(rows) != evidence["expected_results"]
        or not rows
    ):
        raise ValueError("incomplete or unbound evidence")
    rate = capture["sample_rate_hz"]
    origin = int(rows[0]["valid_start"])
    visits, screened, costs = [], [], []
    previous_end = origin
    for i, row in enumerate(rows):
        start, end = int(row["valid_start"]), int(row["valid_end"])
        if (
            int(row["visit"]) != i
            or row["rate_hz"] != rate
            or row["rx"] != 1
            or row["channel"] not in (1, 2, 3, 4)
            or row["edge"] not in ("lower", "upper")
            or end - start != rate * 120 // 1000
            or start < previous_end
            or row["search_window_mask"] not in (0, 63)
        ):
            raise ValueError("invalid RX1 full-dwell geometry")
        previous_end = end
        visits.append(
            Visit(
                i, row["channel"] - 1 + 4 * (row["edge"] == "upper"), (end - origin) * 1000 / rate
            )
        )
        if row["search_window_mask"] == 63:
            cost = row["wall_ms"]
            if not math.isfinite(cost) or cost <= 0:
                raise ValueError("invalid measured wall cost")
            screened.append(i)
            costs.append(cost)
    if not costs:
        raise ValueError("no measured service-cost cohort")
    scenarios = []
    for label, cost in (("wall_median", np.median(costs)), ("wall_p99", np.percentile(costs, 99))):
        for reserve in (0.0, 20.0):
            for policy in POLICIES:
                checks = simulate(visits, float(cost) + reserve, policy)
                scenarios.append(
                    {
                        "cost_basis": label,
                        "worker_wall_ms": float(cost),
                        "additional_serial_reserve_ms": reserve,
                        "policy": policy,
                        "maximum_pending_age_ms": max(r.started_ms - r.ready_ms for r in checks),
                        "maximum_result_age_after_dwell_ms": max(
                            r.completed_ms - r.ready_ms for r in checks
                        ),
                        "terminal_drain_ms": max(
                            0.0, checks[-1].completed_ms - visits[-1].ready_ms
                        ),
                        **summarize(visits, [r.visit for r in checks]),
                        "checks": [asdict(r) for r in checks],
                    }
                )
    return {
        "scope": "Counterfactual admission; no detector, sensitivity, ARM speedup or RF-duty claim",
        "session_id": capture["session_id"],
        "sample_rate_hz": rate,
        "input_manifest_sha256": publication["input_manifest_sha256"],
        "cost_cohort_count": len(costs),
        "maximum_queue_age_ms": 120.0,
        "freshness_guard_threshold_ms": 2500.0,
        "source_gap_includes_capture_boundaries": True,
        "observed": summarize(visits, screened),
        "scenarios": scenarios,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.snapshot.read_bytes()
    result = evaluate(json.loads(gzip.decompress(source)))
    result["snapshot_sha256"] = hashlib.sha256(source).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"session_id": result["session_id"], "scenarios": len(result["scenarios"])}))


if __name__ == "__main__":
    main()
