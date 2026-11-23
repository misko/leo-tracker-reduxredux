from itertools import product

import pytest

from reports.ALGO08.v3.primary_schedule import FULL, PRIMARY, SKIP, optimum, replay_actions


def row(i, frequencies, receiver=0):
    return dict(receiver_id=receiver, channel=1, actual_rf_hz=3_000, valid_start_counter=i * 2_000_000,
                candidates=[dict(candidate_rank=rank, fractional_margin=1. - rank / 5,
                                 fractional_tracking_cfo_hz=hz) for rank, hz in frequencies])


def primary(rows):
    return [[candidate for candidate in row["candidates"] if candidate["candidate_rank"] == 0] for row in rows]


@pytest.mark.parametrize("frequencies", [
    [[(0, 0)]] * 5,
    [[(0, 0), (1, 20_000)]] * 3 + [[(0, 40_000), (1, 20_000)], [], [(0, 100)]],
    [[(1, -25_000)], [(0, -25_000)], [(0, -25_000)], [(1, -25_000)],
     [(0, 5_000), (1, -25_000)], [(0, -25_000)]],
])
def test_strict_and_owned_minima_match_exhaustive_schedules(frequencies):
    rows = [row(i, values) for i, values in enumerate(frequencies)]
    first = primary(rows)
    costs = [(0, 2, 8), (0, 4, 5), (0, 5, 2), (0, 1, 9), (0, 5, 7), (0, 3, 5)][:len(rows)]
    expected = replay_actions(rows, first, [FULL] * len(rows))
    owned = {max(i for i, factor in enumerate(expected) if factor is not None)}
    for constraint in (None, owned):
        required = range(len(rows)) if constraint is None else constraint
        valid = []
        for actions in product((SKIP, PRIMARY, FULL), repeat=len(rows)):
            replay = replay_actions(rows, first, actions)
            if all(replay[i] == expected[i] for i in required):
                valid.append(sum(cost[action] for cost, action in zip(costs, actions, strict=True)))
        solution = optimum(rows, first, costs, constraint)
        assert solution["optimum_ns"] == min(valid)
        assert sum(solution["counts"].values()) == len(rows)
        chosen = replay_actions(rows, first, solution["actions"])
        assert all(chosen[i] == expected[i] for i in required)


def test_empty_slots_evict_history_and_antennas_remain_independent():
    rows = [row(i, [(0, 0)] if i < 4 or i >= 17 else [], receiver)
            for i in range(20) for receiver in (0, 1)]
    result = optimum(rows, primary(rows), [(0, 1, 2)] * len(rows))
    assert result["selected"] == 2
    assert result["actions"] == [PRIMARY] * 8 + [SKIP] * 32


def test_owned_relaxation_rejects_missing_original_observation():
    rows = [row(0, [(0, 0)])]
    with pytest.raises(ValueError, match="lacks its original"):
        optimum(rows, primary(rows), [(0, 1, 2)], {0})
