import numpy as np
from combining_scope import cyclic_agreement


def test_constant_parity_is_uninformative_under_cyclic_controls():
    np.testing.assert_array_equal(cyclic_agreement([[0, 0, 1]] * 7, 1), np.ones(7))
    bits = np.array([[0, 1, 1], [1, 1, 0], [1, 0, 1], [0, 0, 0]])
    scores = cyclic_agreement(bits, 0)
    assert scores[0] == 1 and scores.min() < 1
