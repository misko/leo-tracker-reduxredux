"""Join each published position to its own measured offline replay clock."""

import math
from statistics import median

from ..scoring import ARMS


def joined_rows(scores, clocks, spans):
    by_run = {(c["id"], c["method"]): c for c in clocks}
    arms = {(r["id"], r["method"], r["arm"]) for r in scores}
    if (
        len(by_run) != len(clocks)
        or len(arms) != len(scores)
        or arms != {(*key, arm) for key in by_run for arm in ARMS}
    ):
        raise ValueError("each measured or reconstructed run needs exactly two position rows")
    if set(spans) != {ident for ident, _ in by_run} or any(
        not math.isfinite(v) or v <= 0 for v in spans.values()
    ):
        raise ValueError("a positive recorded delivery span is required for each recording")

    result = []
    for score in scores:
        ident, method = score["id"], score["method"]
        clock = by_run[ident, method]
        seconds = clock["full_service_s"]
        calls, timely = clock["complete_detector_calls"], clock["wall_within_20ms"]
        if seconds is not None and (not math.isfinite(seconds) or seconds <= 0):
            raise ValueError("complete service elapsed time must be finite and positive")
        if (calls is None) != (timely is None) or (calls is not None and not 0 <= timely <= calls):
            raise ValueError("within-deadline calls must be part of the measured calls")
        if clock["acquisition_evidence"] == "reconstructed antenna records" and any(
            value is not None for value in (seconds, calls)
        ):
            raise ValueError(
                "post-acquisition fits cannot supply a detector or complete replay clock"
            )
        if score["status"] != "ok" and score["error_km"] is not None:
            raise ValueError("a missing or withheld fix cannot meet a position allowance")
        fits_span = seconds <= spans[ident] if seconds is not None else None
        row = {
            "id": ident,
            "method": method,
            "arm": score["arm"],
            "status": score["status"],
            "error_km": score["error_km"],
            "baseline_km": score["baseline_km"],
            "acquisition_evidence": clock["acquisition_evidence"],
            "delivery_span_s": spans[ident],
            "full_service_s": seconds,
            "service_over_span": seconds / spans[ident] if seconds is not None else None,
            "within_delivery_span": fits_span,
            "complete_detector_calls": calls,
            "wall_within_20ms": timely,
            "call_clock_scope": clock["call_clock_scope"],
        }
        for pct in (5, 10):
            eligible = score["error_km"] is not None and score["baseline_km"] is not None
            passes = eligible and score["error_km"] <= (1 + pct / 100) * score["baseline_km"]
            row[f"within_{pct}pct"] = passes
            row[f"within_{pct}pct_and_span"] = (
                passes and fits_span if fits_span is not None else None
            )
        result.append(row)
    return result


def summarize(rows, groups, methods):
    summary = []
    for cohort, ids in groups.items():
        for method in methods:
            for arm in ARMS:
                data = [
                    r for r in rows if r["id"] in ids and r["method"] == method and r["arm"] == arm
                ]
                if {r["id"] for r in data} != set(ids) or len(data) != len(ids):
                    raise ValueError(
                        "budget denominator must cover the whole scheduled recording group"
                    )
                timed = [r for r in data if r["full_service_s"] is not None]
                called = [r for r in data if r["complete_detector_calls"] is not None]
                calls = sum(r["complete_detector_calls"] for r in called)
                within = sum(r["wall_within_20ms"] for r in called)
                item = dict(
                    cohort=cohort,
                    method=method,
                    arm=arm,
                    scheduled=len(data),
                    published=sum(r["error_km"] is not None for r in data),
                    service_clock_measured=len(timed),
                    service_clock_unmeasured=len(data) - len(timed),
                    completed_within_span=sum(r["within_delivery_span"] for r in timed),
                    median_service_s=median(r["full_service_s"] for r in timed) if timed else None,
                    recordings_with_call_clocks=len(called),
                    measured_calls=calls if called else None,
                    calls_within_20ms=within if called else None,
                    fraction_calls_within_20ms=within / calls if calls else None,
                )
                for pct in (5, 10):
                    key = f"within_{pct}pct"
                    item[key] = sum(r[key] for r in data)
                    item[f"{key}_on_timed"] = sum(r[key] for r in timed)
                    item[f"{key}_and_span"] = (
                        sum(r[f"{key}_and_span"] for r in timed) if timed else None
                    )
                summary.append(item)
    return summary
