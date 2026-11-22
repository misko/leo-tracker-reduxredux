"""Resolve skipped historical residuals for primaries that lack votes."""

from collections import Counter, OrderedDict

from tools.pipeline_eval.variants.carrier_continuation import votes

from .deferred_continuation import Visit, possible_line
from .residual_schedule import RESIDUAL_HORIZON, Replay

PENDING_LANES = 64
STEREO_WINDOW_BYTES = 200_000 * 2 * 2 * 2


def primary_only(factors):
    return [row for row in factors if row["candidate_rank"] == 0]


class PrimaryRescue:
    """Keep the foreground schedule and enrich only past continuation slots."""

    def __init__(self, max_pending=PENDING_LANES):
        if max_pending < 0:
            raise ValueError("Expected a nonnegative pending lane budget")
        self.max_pending = max_pending
        self.foreground = Replay("conditional")
        self.pending = OrderedDict()
        self.retained_windows = Counter()
        self.counts = Counter()
        self.last_counter = None

    def _take(self, key):
        pending = self.pending.pop(key)
        counter = key[1]
        self.retained_windows[counter] -= 1
        if not self.retained_windows[counter]:
            del self.retained_windows[counter]
        return pending

    def _drop(self, key, reason):
        if key in self.pending:
            self._take(key)
            self.counts[reason] += 1

    def _rescue(self, lane, history, now, primary):
        hz = primary["fractional_tracking_cfo_hz"]
        slots = [(i, counter) for i, (counter, _) in enumerate(history)
                 if (lane, counter) in self.pending]
        if not slots or votes(hz, history, now) >= 3:
            return
        self.counts["primary_deficits_with_pending"] += 1
        for index, counter in reversed(slots):
            possible = [
                Visit(t, None, None if (lane, t) in self.pending else frequencies)
                for t, frequencies in history if 0 < now - t <= RESIDUAL_HORIZON
            ]
            if not possible_line(hz, possible, now):
                self.counts["stopped_without_possible_line"] += 1
                break
            earlier, known_primary = self._take((lane, counter))
            full = list(earlier(True))
            if primary_only(full) != known_primary:
                raise ValueError("Historical query changed the original primary")
            ranks = {factor["candidate_rank"] for factor in full}
            if ranks - {0, 1} or len(ranks) != len(full):
                raise ValueError("Expected distinct historical native ranks")
            history[index] = (counter, tuple(f["fractional_tracking_cfo_hz"] for f in full))
            self.counts["historical_full_queries"] += 1
            self.counts["historical_residuals_found"] += 1 in ranks
            self.counts["maximum_query_age_ticks"] = max(
                self.counts["maximum_query_age_ticks"], now - counter,
            )
            if votes(hz, history, now) >= 3:
                self.counts["primary_thresholds_restored"] += 1
                break

    def visit(self, metadata, measure):
        lane = metadata["receiver_id"], metadata["channel"], metadata["actual_rf_hz"]
        now = metadata["valid_start_counter"]
        history = self.foreground.continuation.by_lane[lane]
        if ((self.last_counter is not None and now < self.last_counter)
                or (history and now <= history[-1][0])):
            raise ValueError("Expected chronological stereo visits with increasing lane counters")
        self.last_counter = now
        while self.pending:
            oldest = next(iter(self.pending))
            if now - oldest[1] <= RESIDUAL_HORIZON:
                break
            self._drop(oldest, "expired_pending")
        oldest_lane_counter = history[0][0] if len(history) == history.maxlen else None

        def choose(use_residual):
            factors = list(measure(use_residual))
            primary = primary_only(factors)
            if primary:
                self._rescue(lane, history, now, primary[0])
            return factors

        use_residual, factors, selected = self.foreground.visit(metadata, choose)
        if oldest_lane_counter is not None:
            self._drop((lane, oldest_lane_counter), "history_evicted_pending")
        if not use_residual:
            self.pending[lane, now] = (measure, primary_only(factors))
            self.retained_windows[now] += 1
        while len(self.pending) > self.max_pending:
            self._drop(next(iter(self.pending)), "budget_evicted_pending")
        lanes, windows = len(self.pending), len(self.retained_windows)
        self.counts["peak_pending_lanes"] = max(self.counts["peak_pending_lanes"], lanes)
        self.counts["peak_stereo_windows"] = max(self.counts["peak_stereo_windows"], windows)
        return use_residual, factors, selected
