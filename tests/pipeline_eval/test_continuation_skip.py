from itertools import product

import pytest

from reports.ALGO08.v3.continuation_skip import optimum, replay


def row(i, hz, receiver=0):
    return dict(receiver_id=receiver, channel=1, actual_rf_hz=3000, valid_start_counter=i * 2_000_000,
                candidates=[dict(candidate_rank=j, fractional_margin=1 - j / 5,
                                 fractional_tracking_cfo_hz=value) for j, value in enumerate(hz)])


@pytest.mark.parametrize("frequencies", [
    [(0,), (0,), (0,), (0,), (0,), (0,)],
    [(0,), (0, 9000), (), (0,), (9000, 0), (0, 9000), (9000,)],
    [(), (), (8000,), (), (), ()],
])
def test_exact_schedule_matches_brute_force(frequencies):
    rows = [row(i, f) for i, f in enumerate(frequencies)]
    costs = [2, 5, 1, 9, 3, 7, 8][:len(rows)]
    original = replay(rows, range(len(rows)))
    best = min(sum(c for c, keep in zip(costs, bits) if keep)
               for bits in product((False, True), repeat=len(rows))
               if replay(rows, {i for i, keep in enumerate(bits) if keep}) == original)
    result = optimum(rows, costs)
    assert result["optimum_ns"] == best
    assert replay(rows, result["kept_indices"]) == original


def test_empty_slots_and_antennas_remain_independent():
    rows = [row(i, [0] if (i < 4 or i >= 17) else [], rx) for i in range(20) for rx in (0, 1)]
    result = optimum(rows, [1] * len(rows))
    assert result["selected"] == 2
    assert result["kept_indices"] == list(range(8))
    assert result["optimum_ns"] > result["selected_only_floor_ns"]
