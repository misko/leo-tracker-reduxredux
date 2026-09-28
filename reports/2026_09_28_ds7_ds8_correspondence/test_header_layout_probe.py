import numpy as np
from header_layout_probe import best_check, check_score, lane_order, windows


def test_blocked_and_interleaved_serializations_recover_same_windows():
    triples = np.random.default_rng(34).integers(0, 2, (40, 3))
    direct = windows([triples.ravel()], 0, (0, 2), False)
    blocked = windows([triples.T.ravel()], 0, (0, 2), True)
    assert np.array_equal(direct, blocked)


def test_lane_grouping_never_invents_or_drops_missing_carriers():
    for lanes in [1, 4, 8, 16, 32]:
        order = lane_order(1004, lanes)
        assert np.array_equal(np.sort(order), np.arange(1004))
        assert np.all(np.diff(order % lanes) >= 0)


def test_known_convolutional_relation_generalizes_in_blocked_layout():
    rng = np.random.default_rng(48)

    def encoded():
        source = rng.integers(0, 2, 1200)
        streams = [
            np.convolve(source, [(g >> k) & 1 for k in range(7)])[: len(source)] % 2
            for g in [0o171, 0o133, 0o165]
        ]
        return np.array(streams).ravel()

    discovery = windows([encoded()], 0, (0, 1), True)
    evaluation = windows([encoded()], 0, (0, 1), True)
    mask, score = best_check(discovery)
    assert score == 1
    assert check_score(evaluation, mask) == 1
