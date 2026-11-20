from itertools import pairwise

import pytest

from tools.pipeline_eval.variants.rotating_dwell import bank_events, schedule


@pytest.mark.parametrize("size,tenure", [(2, 30), (4, 60)])
def test_bank_slot_tenure_and_last_interval_are_bound(size, tenure):
    for bank in (0, 1):
        events = bank_events("authentic", size, bank, 299.997)
        assert events[0][0] == 0 and events[1][0] == tenure + 15 * bank
        assert len({c for _, radio in events for c in radio}) == 4
        last_change = [0] * (size // 2)
        for (_, before), (when, after) in pairwise(events):
            changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
            assert len(changed) == 1 and len(set(after)) == size // 2
            (slot,) = changed
            assert when - last_change[slot] >= tenure
            last_change[slot] = when
        assert 299.997 - max(last_change) >= tenure


def test_gaps_do_not_advance_the_original_physical_clock():
    origin, rate = 3_000, 50
    metadata = [(i, i % 8 + 1) for i in range(300)]
    counters = {i: origin + i * rate for i, _ in metadata}
    end = origin + 300 * rate
    picked, original = schedule("r", metadata, counters, origin, end, rate, 2)
    no_early = [(i, lane) for i, lane in metadata if i >= 74]
    after_gap, current = schedule("r", no_early, counters, origin, end, rate, 2)
    assert after_gap == [i for i in picked if i >= 74]
    assert current == original


def test_out_of_range_sample_is_rejected():
    with pytest.raises(ValueError, match="hardware clock"):
        schedule("r", [(9, 1)], {9: 12}, 13, 10_000, 1, 2)
