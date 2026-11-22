"""Experimental per-RF burst sampling before native detection and continuation."""
from collections import Counter
from contextlib import contextmanager


class BurstCadence:
    """Retain eight consecutive valid visits to each RF, then skip eight."""

    def __init__(self):
        self.visits = Counter()
        self.skipped = Counter()

    def wrap(self, detector):
        @contextmanager
        def open_receiver(*args, **kwargs):
            with detector(*args, **kwargs) as detect:
                def visit(window):
                    rf = window.acquisition["actual_if_center_hz"] + window.target["lnb_lo_hz"]
                    index = self.visits[rf]
                    self.visits[rf] += 1
                    if index % 16 >= 8:
                        self.skipped[window.target["channel"]] += 1
                        return []
                    return detect(window)
                yield visit
        return open_receiver

    def receipt(self, result):
        skipped = sum(self.skipped.values())
        counts = result["counts"]
        if counts["processed"] + counts["invalid_capture"] + skipped != result["window_count"]:
            raise ValueError("Scheduled receiver visits do not reconcile with the recording")
        return dict(policy="8-on-8-off-per-rf", skipped_valid_visits=skipped,
                    skipped_by_channel=dict(self.skipped))
