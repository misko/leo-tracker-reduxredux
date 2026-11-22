"""Fully measure the first three donor slots, preserving the frozen activity rule."""

from .residual_schedule import Replay


class InitialDonors(Replay):
    def __init__(self):
        super().__init__("conditional")

    def visit(self, metadata, measure):
        lane = metadata["receiver_id"], metadata["channel"], metadata["actual_rf_hz"]
        if self.opportunities[lane] >= 3:
            return super().visit(metadata, measure)
        measured = list(measure(True))
        ranks = [factor["candidate_rank"] for factor in measured]
        if set(ranks) - {0, 1} or len(ranks) != len(set(ranks)):
            raise ValueError("Expected distinct verified factors at the original native ranks")
        full, _, selected = super().visit(metadata, lambda take: measured if take else [
            f for f in measured if f["candidate_rank"] == 0])
        if not full:
            # No factor can be selected with fewer than three previous visits.
            # Enrich this donor without extending the ordinary activity clock.
            if selected:
                raise ValueError("Unexpected selection during lane initialization")
            hz = tuple(f["fractional_tracking_cfo_hz"] for f in measured)
            self.continuation.by_lane[lane][-1] = (metadata["valid_start_counter"], hz)
            self.reasons["skip"] -= 1
            self.reasons["bootstrap"] += 1
        return True, measured, selected
