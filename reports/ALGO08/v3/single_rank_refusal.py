"""Run ordinary cold ranking once when the two-centre scout declines to choose seeds."""

from contextlib import contextmanager
from unittest.mock import patch

import combined_successor as combined
import two_centre_seeds as seeds


class _NoScoutSeeds(Exception):
    pass


class SingleRankHandoff(combined.SuccessorHandoff):
    def rank(self, scan):
        if scan is not self.scan or self.scout:
            return super().rank(scan)
        original_scout = seeds.scout

        def choose(stats, offer, initial, sigma, bounds, discovery, audit):
            proposals = original_scout(stats, offer, initial, sigma, bounds, discovery, audit)
            if proposals is None and audit is self.scout:
                # The existing two-centre implementation is about to execute
                # the ordinary centre fits inside a speculative rank. Only
                # the ordinary producer outside that scope can own a checkpoint.
                raise _NoScoutSeeds
            return proposals

        started = seeds.now()
        try:
            with patch.object(seeds, "scout", choose):
                return super().rank(scan)
        except _NoScoutSeeds:
            self.scout.update(paid=seeds.elapsed(started), fallback="no_supported_scout",
                              paid_centres=0, declined_before_centre_fits=True)
        started = seeds.now()
        nodes = combined.NominationHandoff.rank(self, scan)
        self.scout["ordinary_retry"] = seeds.elapsed(started)
        return nodes


@contextmanager
def single_rank_refusal():
    """Limit the change to one serial research worker's guarded solver."""
    with patch.object(combined, "SuccessorHandoff", SingleRankHandoff):
        yield
