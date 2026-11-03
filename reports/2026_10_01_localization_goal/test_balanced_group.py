import numpy as np

from balanced_group_objective import group_weights


def test_total_group_weight_and_clutter_invariance():
    labels = [7, 7, 7, 9, None]
    weights = group_weights(labels)
    assert np.allclose(weights[:3].sum(), weights[3])
    assert np.isclose(weights[:4].sum(), 4)
    assert weights[4] == 1
    permutation = [4, 2, 0, 3, 1]
    assert np.array_equal(group_weights([labels[i] for i in permutation]), weights[permutation])


def test_equal_counts_singletons_and_no_signal():
    for labels in [[1, 2, 3], [1, 1, 2, 2], [1, 1], [None, None], []]:
        assert np.array_equal(group_weights(labels), np.ones(len(labels)))
