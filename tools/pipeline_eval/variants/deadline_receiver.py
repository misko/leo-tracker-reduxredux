"""Give compact v5 a fixed time slice and keep time for the smooth-clock receiver."""

import math
from time import monotonic

from ..scoring import ARMS, validate_result

BOUNDARY = "Stored GLRT detections through a deadline-limited compact or smooth-clock fix"
RESERVE_S = 15.0


def deadline_result():
    return dict(
        status="timed_out",
        reason="receiver deadline elapsed",
        boundary=BOUNDARY,
        arms={arm: {"latlon": None} for arm in ARMS},
        metrics={},
    )


def route(compact, smooth, *, total_s, reserve_s=RESERVE_S, now=monotonic):
    """Run serial, cancellable workers. Each receives its remaining wall-time allowance."""
    if not (math.isfinite(total_s) and math.isfinite(reserve_s) and 0 < reserve_s < total_s):
        raise ValueError("the reserve must be positive and below the finite total deadline")
    started = now()
    calls = []
    selected = "none"
    result = deadline_result()
    for name, worker, cutoff in (
        ("compact", compact, started + total_s - reserve_s),
        ("smooth", smooth, started + total_s),
    ):
        before = now()
        allowed = cutoff - before
        if allowed <= 0:
            break
        returned = worker(allowed)
        after = now()
        validate_result(returned)
        if after < before:
            raise ValueError("the deadline clock must be monotonic")
        late = after > cutoff
        result = deadline_result() if late else returned
        calls.append(
            dict(
                method=name,
                budget_s=allowed,
                wall_s=after - before,
                status=result["status"],
                worker_status=returned["status"],
                late=late,
            )
        )
        selected = name if not late else "none"
        if result["status"] not in ("failed", "timed_out"):
            break
    return dict(result=result, selected=selected, calls=calls, elapsed_s=now() - started)
