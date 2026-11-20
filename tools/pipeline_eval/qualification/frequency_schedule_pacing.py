"""Apply actual detector CPU costs to an idealized paced worker pool."""

from heapq import heapreplace
from math import fsum, isfinite

CORES = (1, 2, 3, 4, 6, 8, 10, 12)
DEADLINE_S = 300.0


def pace(arrivals, costs, cores, deadline=DEADLINE_S):
    if cores < 1 or len(arrivals) != len(costs):
        raise ValueError("every paced job requires one cost and at least one worker")
    available = [0.0] * cores
    finished = []
    previous = 0.0
    for arrival, cost in zip(arrivals, costs, strict=True):
        if not isfinite(arrival) or not isfinite(cost) or arrival < previous or cost <= 0:
            raise ValueError("pace requires ordered nonnegative visits and positive CPU costs")
        previous = arrival
        finish = max(arrival, available[0]) + cost
        heapreplace(available, finish)
        finished.append(finish)
    completed = sum(t <= deadline for t in finished)
    total = fsum(costs)
    return dict(
        detector_cpu_work_s=total,
        work_only_lower_bound_s=total / cores,
        completed_by_300_s=completed,
        pending_at_300_s=len(arrivals) - completed,
        simulated_detector_ready_s=max(finished, default=0.0),
    )
