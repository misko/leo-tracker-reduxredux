"""Choose between measured carriers using only past observations on the same RF lane."""

from collections import defaultdict, deque


def votes(hz, history, counter):
    earlier = [
        ((counter - t) / 1e7, values)
        for t, values in history
        if 0 < counter - t <= 80_000_000 and values
    ]
    if len(earlier) < 3 or earlier[0][0] < 0.4:
        return 0
    best = 0
    for dt, seeds in earlier:
        for seed in seeds:
            slope = (hz - seed) / dt
            if abs(slope) > 8000:
                continue
            hits = [
                gap
                for gap, values in earlier
                if any(abs(value - (hz - slope * gap)) <= 800 for value in values)
            ]
            if hits and max(hits) >= 0.4:
                best = max(best, len(hits))
    return best


class Continuation:
    def __init__(self):
        self.by_lane = defaultdict(lambda: deque(maxlen=12))

    def select(self, probe):
        lane = (probe["receiver_id"], probe["channel"], probe["actual_rf_hz"])
        history = self.by_lane[lane]
        now = probe["valid_start_counter"]
        if history and history[-1][0] >= now:
            raise ValueError("non-increasing hardware counter in receiver-channel history")
        factors = probe["candidates"]
        if len(factors) > 2:
            raise ValueError("continuation expects at most two distinct verified factors")
        scores = [votes(f["fractional_tracking_cfo_hz"], history, now) for f in factors]
        history.append((now, tuple(f["fractional_tracking_cfo_hz"] for f in factors)))
        if not factors:
            return None, None, []
        preferred = max(
            range(len(factors)),
            key=lambda i: (factors[i]["fractional_margin"], -factors[i]["candidate_rank"]),
        )
        if len(scores) == 2:
            other = 1 - preferred
            if scores[other] >= 3 and scores[other] >= scores[preferred] + 2:
                preferred = other
        selective = preferred if scores[preferred] >= 3 else None
        return preferred, selective, scores
