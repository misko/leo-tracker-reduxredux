"""Nonpreemptive scheduling over signed delivery metadata and fixed waiting budgets."""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from heapq import heappop, heappush

NS = 1_000_000_000
WAITING = 8
LAG_NS = NS


class Policy(str, Enum):
    FIFO = "fifo"
    REPLACE = "replace-oldest"
    ROUND_ROBIN = "rf-round-robin"


@dataclass(frozen=True)
class Arrival:
    visit: int
    time_ns: int
    rf: int
    valid: bool


class Waiting:
    def __init__(self, policy, capacity, lag_ns, rf_bins):
        if capacity < 0 or lag_ns <= 0 or not rf_bins:
            raise ValueError("invalid queue capacity, lag or RF order")
        self.policy, self.capacity, self.lag_ns = policy, capacity, lag_ns
        self.rf_bins = tuple(rf_bins)
        if len(set(rf_bins)) != len(rf_bins):
            raise ValueError("RF target order contains duplicates")
        if policy == Policy.ROUND_ROBIN and capacity < len(rf_bins):
            raise ValueError("round robin requires a waiting slot for each RF bin")
        self.queue, self.by_rf, self.cursor = deque(), {}, 0

    def __len__(self):
        return len(self.by_rf) if self.policy == Policy.ROUND_ROBIN else len(self.queue)

    def ids(self):
        rows = self.by_rf.values() if self.policy == Policy.ROUND_ROBIN else self.queue
        return sorted(row.visit for row in rows)

    def expire(self, time_ns):
        threshold = time_ns - self.lag_ns
        if self.policy == Policy.ROUND_ROBIN:
            stale = [rf for rf, row in self.by_rf.items() if row.time_ns <= threshold]
            return [self.by_rf.pop(rf).visit for rf in stale]
        expired = []
        while self.queue and self.queue[0].time_ns <= threshold:
            expired.append(self.queue.popleft().visit)
        return expired

    def admit(self, arrival):
        if self.policy == Policy.ROUND_ROBIN:
            older = self.by_rf.get(arrival.rf)
            self.by_rf[arrival.rf] = arrival
            return (older.visit, "replaced_rf") if older is not None else None
        discarded = None
        if len(self.queue) == self.capacity:
            if self.policy == Policy.FIFO or self.capacity == 0:
                return arrival.visit, "queue_full"
            discarded = self.queue.popleft().visit, "replaced_oldest"
        self.queue.append(arrival)
        return discarded

    def dispatch(self):
        if self.policy != Policy.ROUND_ROBIN:
            return self.queue.popleft()
        for _ in self.rf_bins:
            rf = self.rf_bins[self.cursor]
            self.cursor = (self.cursor + 1) % len(self.rf_bins)
            if rf in self.by_rf:
                return self.by_rf.pop(rf)
        raise ValueError("no waiting job for any configured RF target")


def simulate(arrivals, durations_ns, workers, policy, rf_bins, *, capacity=WAITING, lag_ns=LAG_NS):
    if workers < 1 or not arrivals or len(arrivals) != len(durations_ns):
        raise ValueError("invalid workers or unmatched service clock")
    waiting = Waiting(policy, capacity, lag_ns, rf_bins)
    pending = []
    starts, finishes, dispositions = {}, {}, {}
    deadline = arrivals[-1].time_ns + lag_ns
    peak_waiting = 0

    def start(arrival, time_ns):
        duration = durations_ns[arrival.visit]
        if type(duration) is not int or duration <= 0:
            raise ValueError("started visit lacks a positive service duration")
        starts[arrival.visit] = time_ns
        heappush(pending, (time_ns + duration, arrival.visit))

    def expire(time_ns):
        for visit in waiting.expire(time_ns):
            dispositions[visit] = "expired_waiting"

    def complete_through(time_ns):
        while pending and pending[0][0] <= time_ns:
            finished, visit = heappop(pending)
            finishes[visit] = finished
            dispositions[visit] = (
                "ready" if finished - arrivals[visit].time_ns <= lag_ns else "expired_running"
            )
            expire(finished)
            if waiting:
                start(waiting.dispatch(), finished)
        expire(time_ns)

    previous_ns = -1
    for i, arrival in enumerate(arrivals):
        if arrival.visit != i or arrival.time_ns <= previous_ns or arrival.rf not in rf_bins:
            raise ValueError("invalid physical arrival order, timestamp or RF target")
        previous_ns = arrival.time_ns
        complete_through(arrival.time_ns)
        if not arrival.valid:
            dispositions[i] = "invalid_capture"
        elif len(pending) < workers:
            if policy == Policy.ROUND_ROBIN:
                waiting.admit(arrival)
                start(waiting.dispatch(), arrival.time_ns)
            else:
                start(arrival, arrival.time_ns)
        else:
            discard = waiting.admit(arrival)
            if discard is not None:
                dispositions[discard[0]] = discard[1]
            peak_waiting = max(peak_waiting, len(waiting))

    at_last_delivery = {"waiting": waiting.ids(), "running": sorted(i for _, i in pending)}
    complete_through(deadline)
    at_deadline = {"waiting": waiting.ids(), "running": sorted(i for _, i in pending)}
    dispositions.update({i: "deadline_running" for i in at_deadline["running"]})
    for visit in at_deadline["waiting"]:
        dispositions[visit] = "deadline_waiting"
    if set(dispositions) != set(range(len(arrivals))):
        raise ValueError("queue outcomes must cover all physical deliveries")
    return dict(
        start_ns=starts,
        finish_ns=finishes,
        outcomes=dispositions,
        last_delivery=at_last_delivery,
        deadline=at_deadline,
        deadline_ns=deadline,
        peak_waiting=peak_waiting,
        ready_next=[
            i for i, following in enumerate(arrivals[1:])
            if dispositions[i] == "ready" and finishes[i] <= following.time_ns
        ],
    )
