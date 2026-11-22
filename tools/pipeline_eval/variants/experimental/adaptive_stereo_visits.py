"""Omit one stereo visit only after redundant, recently measured strong support."""

from collections import Counter, defaultdict, deque
from dataclasses import dataclass

from leo.contracts.fast_scan_native import FastScanPolicyV2
from tools.pipeline_eval.variants.carrier_continuation import Continuation, votes

RATE = 10_000_000
MAX_AGE = 8 * RATE
MIN_SPAN = 4_000_000
MAX_SLOPE = 8000
MIN_DONORS = 4  # The released minimum of three plus one spare donor.
RETAINED_SLOTS = 11  # One slot is spent on the proposed empty visit.
STRONG_MARGIN = FastScanPolicyV2().strong_margin


def identity(pair):
    """Return the stereo continuation lane and its hardware counter."""
    left, right = pair
    fields = ("channel", "actual_rf_hz", "valid_start_counter")
    if ((left["receiver_id"], right["receiver_id"]) != (0, 1)
            or any(left[key] != right[key] for key in fields)):
        raise ValueError("Expected both receivers on the same RF and hardware clock")
    return (left["channel"], left["actual_rf_hz"]), left["valid_start_counter"]


def follow_up(counters, now):
    if len(counters) < 2:
        return None
    earlier, latest = counters[-2], counters[-1]
    if not earlier < latest < now:
        raise ValueError("Expected increasing hardware counters per RF")
    return now + max(now - latest, latest - earlier)


@dataclass(frozen=True)
class Opportunity:
    counter: int
    skipped: bool
    strong_frequencies: tuple[float, float] | None


def skip_reason(history, now):
    if history and history[-1].skipped:
        return "follow-up"
    future = follow_up([row.counter for row in history], now)
    if future is None:
        return "startup"

    support = []
    for row in reversed(history):
        if future - row.counter > MAX_AGE:
            break
        if row.skipped:
            continue
        if row.strong_frequencies is None:
            break
        support.append(row)
    if len(support) < MIN_DONORS or future - support[-1].counter < MIN_SPAN:
        return "insufficient-strong-history"

    for antenna in (0, 1):
        latest, previous = support[:2]
        hz = latest.strong_frequencies[antenna]
        previous_hz = previous.strong_frequencies[antenna]
        slope = (hz - previous_hz) / ((latest.counter - previous.counter) / RATE)
        if abs(slope) > MAX_SLOPE:
            return "unstable-frequency"
        prediction = hz + slope * ((future - latest.counter) / RATE)
        measured = [(row.counter, (row.strong_frequencies[antenna],)) for row in reversed(support)]
        if votes(prediction, measured, future) < MIN_DONORS:
            return "unstable-frequency"
    return "skip"


class AdaptiveStereo:
    def __init__(self):
        self.lanes = defaultdict(lambda: deque(maxlen=RETAINED_SLOTS))
        self.continuation = Continuation()
        self.reasons = Counter()

    def visit(self, pair, measure):
        """Consult the current factors only after choosing whether to measure."""
        lane, now = identity(pair)
        history = self.lanes[lane]
        if history and now <= history[-1].counter:
            raise ValueError("Expected increasing hardware counters per RF")
        reason = skip_reason(history, now)
        skipped = reason == "skip"
        observed = ((), ()) if skipped else measure()
        strong = None
        if all(len(factors) == 1 and factors[0]["fractional_margin"] >= STRONG_MARGIN
               for factors in observed):
            strong = tuple(lane[0]["fractional_tracking_cfo_hz"] for lane in observed)
        history.append(Opportunity(now, skipped, strong))
        self.reasons[reason] += 1
        chosen, support = [], []
        for metadata, factors in zip(pair, observed, strict=True):
            probe = dict(metadata, candidates=factors)
            preferred, selected, counts = self.continuation.select(probe)
            admitted = [] if selected is None else [factors[selected]]
            chosen.append(dict(metadata, candidates=admitted))
            support.append(dict(preferred=preferred, selected=selected, votes=counts))
        return skipped, observed, chosen, support


def optimistic_skip_limit(pairs):
    """Bound skips using timestamps and assuming every donor is usable."""
    counters = defaultdict(lambda: deque(maxlen=RETAINED_SLOTS))
    best = defaultdict(lambda: (0, 0))
    eligible = 0
    for pair in pairs:
        lane, now = identity(pair)
        history = counters[lane]
        future = follow_up(history, now)
        donors = [past for past in history if future is not None and future - past <= MAX_AGE]
        possible = len(donors) >= MIN_DONORS and future - donors[0] >= MIN_SPAN
        eligible += possible
        prior_keep, prior_skip = best[lane]
        best[lane] = (max(prior_keep, prior_skip), prior_keep + 1 if possible else 0)
        history.append(now)
    return dict(timestamp_eligible_visits=eligible,
                maximum_nonconsecutive_skips=sum(max(row) for row in best.values()))
