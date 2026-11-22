"""Delay a native factor call until it can affect the released continuation."""

from collections import Counter, OrderedDict, defaultdict, deque
from dataclasses import dataclass
from typing import Callable

from tools.pipeline_eval.variants.carrier_continuation import Continuation, votes


@dataclass(eq=False)
class Visit:
    counter: int
    measure: Callable | None
    frequencies: tuple | None = None

    def resolve(self):
        factors = self.measure()
        self.frequencies = tuple(f["fractional_tracking_cfo_hz"] for f in factors)
        self.measure = None
        return factors


def possible_line(hz, history, now):
    hits = 0
    has_span = False
    for past in history:
        dt = (now - past.counter) / 1e7
        if past.frequencies is not None:
            # The two endpoints use the same multiply and subtract as votes().
            # Every allowed slope predicts between them, including roundoff.
            lo, hi = hz - 8000 * dt, hz - (-8000) * dt
            if not any(abs(value - min(max(value, lo), hi)) <= 800 for value in past.frequencies):
                continue
        hits += 1
        has_span |= dt >= .4
        if hits >= 3 and has_span:
            return True
    return False


class DeferredContinuation:
    """The input callback must reproduce that lane's original two-scan call."""

    def __init__(self, max_pending=16):
        if max_pending < 0:
            raise ValueError("Pending lane budget must be nonnegative")
        self.max_pending = max_pending
        self.lanes = defaultdict(deque)
        self.pending = OrderedDict()
        self.last_counter = None
        self.counts = Counter()

    def discard(self, visit):
        if visit in self.pending:
            del self.pending[visit]
            visit.measure = None
            self.counts["discarded_unmeasured"] += 1

    def resolve_history(self, visit):
        visit.resolve()
        del self.pending[visit]
        self.counts["measured_from_history"] += 1

    def select(self, probe, measure):
        now = probe["valid_start_counter"]
        lane = probe["receiver_id"], probe["channel"], probe["actual_rf_hz"]
        history = self.lanes[lane]
        if (self.last_counter is not None and self.last_counter > now
                or history and history[-1].counter >= now):
            raise ValueError("Expected chronological visits and increasing lane counters")
        self.last_counter = now
        while self.pending and now - next(iter(self.pending)).counter > 80_000_000:
            self.discard(next(iter(self.pending)))
        while history and now - history[0].counter > 80_000_000:
            history.popleft()

        # An unmeasured observation is always a possible donor. A known empty
        # observation still occupies one of the stock history's twelve slots.
        possible = [past for past in history if past.frequencies != ()]
        current = Visit(now, measure)
        selected = []
        if len(possible) < 3 or now - possible[0].counter < 4_000_000:
            self.pending[current] = None
            self.counts["deferred"] += 1
        else:
            candidates = current.resolve()
            self.counts["measured_now"] += 1
            if candidates:
                known = [(past.counter, past.frequencies or ()) for past in history]
                if len(candidates) == 1 and votes(current.frequencies[0], known, now) >= 3:
                    # Adding donors cannot remove an observed three-vote line.
                    selected = candidates
                elif any(possible_line(hz, possible, now) for hz in current.frequencies):
                    for past in possible:
                        if past.measure is not None:
                            self.resolve_history(past)
                    choice = Continuation()
                    choice.by_lane[lane].extend((past.counter, past.frequencies) for past in history)
                    _, index, _ = choice.select(dict(probe, candidates=candidates))
                    if index is not None:
                        selected = [candidates[index]]
                else:
                    self.counts["ruled_out_by_frequency"] += 1
        if len(history) == 12:
            self.discard(history.popleft())
        history.append(current)
        while len(self.pending) > self.max_pending:
            self.resolve_history(next(iter(self.pending)))
            self.counts["budget_resolutions"] += 1
        self.counts["peak_pending_lanes"] = max(self.counts["peak_pending_lanes"], len(self.pending))
        return selected
