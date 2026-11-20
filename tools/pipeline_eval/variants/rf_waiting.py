"""A causal one-slot admission policy and a measured-service replay clock."""

from heapq import heappop, heappush

POLICIES = ("fifo", "latest", "oldest_rf")


def replace_waiter(policy, pending_rf, incoming_rf, last_start):
    """Choose between two waiting windows using only work that already started."""
    if policy == "fifo":
        return False
    if policy == "latest":
        return True
    if policy == "oldest_rf":
        return last_start.get(incoming_rf, -1) < last_start.get(pending_rf, -1)
    raise ValueError(f"unknown waiting policy {policy!r}")


def simulate(arrivals, workers, policy):
    """Replay all arrivals. Each event is (due ns, RF or None if invalid, CPU ns)."""
    if type(workers) is not int or workers < 1 or policy not in POLICIES:
        raise ValueError("positive worker count and a recognized queue policy are required")
    running, emitted, last_start = [], [], {}
    pending = None
    previous_due = -1

    def start(visit, start_ns):
        due, rf, duration = arrivals[visit]
        end = start_ns + duration
        last_start[rf] = start_ns
        heappush(running, end)
        emitted.append((visit, start_ns, end))

    def advance(until):
        nonlocal pending
        while running and running[0] <= until:
            available = heappop(running)
            if pending is not None:
                start(pending, available)
                pending = None

    for visit, (due, rf, cpu_ns) in enumerate(arrivals):
        if due < 0 or due < previous_due or (rf is not None and cpu_ns <= 0):
            raise ValueError("visits require ordered arrival clocks and positive valid CPU times")
        previous_due = due
        advance(due)
        if rf is None:
            continue
        if len(running) < workers:
            start(visit, due)
        elif pending is None or replace_waiter(policy, arrivals[pending][1], rf, last_start):
            pending = visit
    if pending is not None:
        advance(running[0])
    return emitted
