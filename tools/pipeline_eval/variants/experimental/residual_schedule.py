"""Replay a causal residual-discovery schedule with the released continuation."""

from collections import Counter

from tools.pipeline_eval.variants.carrier_continuation import Continuation


MODES = ("always-two", "primary-only", "conditional")
SENTINEL_PERIOD = 3
RESIDUAL_HORIZON = 80_000_000  # The released 8-second horizon on the 10 MS/s device clock.


class Replay:
    def __init__(self, mode, *, initialize_donors=False):
        if mode not in MODES:
            raise ValueError("Unknown residual schedule")
        self.mode = mode
        self.initialize_donors = initialize_donors
        self.opportunities = Counter()
        self.last_residual = {}
        self.continuation = Continuation()
        self.reasons = Counter()

    def visit(self, metadata, measure):
        """Choose a scan mode before the callback reveals any current factor."""
        lane = metadata["receiver_id"], metadata["channel"], metadata["actual_rf_hz"]
        now = metadata["valid_start_counter"]
        offset = self.opportunities[lane]
        self.opportunities[lane] += 1
        reason = self.mode
        use_residual = self.mode == "always-two"
        if self.mode == "conditional":
            last = self.last_residual.get(lane)
            if offset % SENTINEL_PERIOD == 0:
                reason, use_residual = "sentinel", True
            elif last is not None and 0 < now - last <= RESIDUAL_HORIZON:
                reason, use_residual = "activity", True
            else:
                reason = "skip"
        # Before there are three historical opportunities, no current factor
        # can pass continuation. Measure these slots for future votes only.
        bootstrap = self.initialize_donors and reason == "skip" and offset < 3
        full = use_residual or bootstrap
        factors = list(measure(full))
        ranks = {f["candidate_rank"] for f in factors}
        if ranks - {0, 1} or len(ranks) != len(factors):
            raise ValueError("Expected distinct factors at the original native ranks")
        if 1 in ranks:
            if not full:
                raise ValueError("A skipped residual was exposed to the continuation")
            if use_residual:
                self.last_residual[lane] = now
        self.reasons["bootstrap" if bootstrap else reason] += 1
        _, selected, _ = self.continuation.select(dict(metadata, candidates=factors))
        admitted = [] if selected is None else [factors[selected]]
        return full, factors, admitted
