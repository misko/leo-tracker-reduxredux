import numpy as np
from state_conditioned_header import templates


def test_state_templates_count_only_qualified_training_observations():
    bits = np.array([[0, 1], [0, 1], [0, 1], [1, 0], [1, 0], [1, 0]], bool)
    valid = np.ones_like(bits)
    valid[0, 1] = False
    result = templates(bits, valid, np.array([0, 0, 0, 1, 1, 1]))
    np.testing.assert_array_equal(result[0][0], [False, True])
    np.testing.assert_array_equal(result[0][1], [True, False])
    np.testing.assert_array_equal(result[1][0], [True, False])
