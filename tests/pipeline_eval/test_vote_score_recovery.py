from itertools import product

import pytest

from tools.pipeline_eval.variants import carrier_continuation as stock
from tools.pipeline_eval.variants.experimental.vote_score_recovery import retained_factor


@pytest.mark.parametrize("margins", [(0.2, 0.1), (0.1, 0.2), (0.2, 0.2)])
def test_all_vote_counts_ties_and_both_scan_orders(monkeypatch, margins):
    factors = [dict(fractional_tracking_cfo_hz=i, fractional_margin=m, candidate_rank=i)
               for i, m in enumerate(margins)]
    for votes in product(range(13), repeat=2):
        monkeypatch.setattr(stock, "votes", lambda hz, _history, _counter: votes[hz])
        for order in (factors, factors[::-1]):
            probe = dict(receiver_id=0, channel=1, actual_rf_hz=1, valid_start_counter=1, candidates=order)
            _, keep, counts = stock.Continuation().select(probe)
            requested = []

            def recover(index):
                requested.append(index)
                return order[index]

            assert retained_factor(counts, recover) == (None if keep is None else order[keep])
            expected = 0 if max(counts) < 3 else 1 if abs(counts[0]-counts[1]) >= 2 else 2
            assert len(requested) == expected


def test_empty_single_and_malformed_rows():
    assert retained_factor([], None) is None
    assert retained_factor([2], None) is None
    assert retained_factor([3], lambda index: index) == 0
    with pytest.raises(ValueError):
        retained_factor([0, 0, 0], None)
