import numpy as np
from transfer_attribution import expected_match, macro_excess


def test_conditional_expectation_and_missing_class_abstention():
    labels = np.array([0, 1, 0])
    predicted = np.array([0, 0, 1])
    np.testing.assert_allclose(expected_match(labels, predicted, [[0, 1], [2]]), [1, 0, 0])
    assert macro_excess(labels, np.ones(3), np.array([True, False, True]), classes=2) is None
    assert macro_excess(labels, np.ones(3), np.ones(3, bool), classes=2) == 1
