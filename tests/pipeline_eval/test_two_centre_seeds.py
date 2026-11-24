from collections import Counter
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from two_centre_seeds import ROBUST_CAP, radio_weights, receiver_scores, scout


def stats():
    return dict(count=np.array([100, 10, 6]), starts=np.array([0, 1, 2]),
                g=np.array([0, 1, 3]), active=np.array([True, True, True]))


def test_receiver_scores_use_separate_denominators_and_full_roster_minima():
    weights = radio_weights(stats())
    np.testing.assert_allclose(weights, [[5/6, 1/6, 0], [0., 0., 1.]])
    scores = receiver_scores(np.array([[100., 4.], [0., 1.], [np.inf, 2*ROBUST_CAP]]), weights)
    np.testing.assert_allclose(scores, [10/3, ROBUST_CAP])


def test_candidate_keeps_zero_and_prefers_bilateral_support():
    zero = np.zeros(8)
    seed1 = zero.copy()
    seed1[1] = 17
    seed2 = zero.copy()
    seed2[0] = -80
    visited = Counter()

    def cost(observed, beta, noise, bound, *, return_components):
        assert set(observed) == set(stats()) and return_components and len(noise) == 2
        visited[tuple(beta)] += 1
        values = [0., 0., 20.] if beta[1] else [9., 9., 10.]
        return None, np.column_stack([values, np.ones(3) * ROBUST_CAP])

    adapter = SimpleNamespace(seed_calibrations=lambda *args, **kwargs: iter((zero, seed1, seed2, seed2)),
                              project_radio_state=lambda state: state, proposal_phases=cost)
    audit = {}
    ordinary, candidate = scout(stats(), stats(), zero, np.ones(2), np.ones(2), adapter, audit)
    np.testing.assert_array_equal(ordinary, zero)
    np.testing.assert_array_equal(candidate, seed2)
    assert audit["picked"] == 1 and list(visited.values()) == [1, 1]


def test_no_bilateral_measured_support_does_not_admit_sparse_route():
    rows = stats()
    rows["active"][-1] = False
    assert radio_weights(rows) is None
    audit = {}
    assert scout(rows, rows, np.zeros(8), np.ones(2), np.ones(2), None, audit) is None
    assert audit["picked"] is None
