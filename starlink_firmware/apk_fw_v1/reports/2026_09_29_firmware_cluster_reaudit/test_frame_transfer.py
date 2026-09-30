import numpy as np
from frame_transfer import balanced_accuracy, family_controls, normalize


def test_macro_score_does_not_reward_large_majority_and_phase_ignores_amplitude():
    truth = np.array([0] * 99 + [1])
    assert balanced_accuracy(truth, np.zeros(100, int)) == .5
    z = np.array([[1 + 2j, -3 + 1j], [2 - 3j, -1 - 1j]])
    np.testing.assert_allclose(normalize(z), normalize(z * np.array([[2, 7], [3, 8]])))


def test_constant_control_abstains_without_dominating_another_test():
    p, maxima = family_controls([[100, 100, 100], [3, 1, 2]])
    assert p[0] is None
    assert p[1] == 1 / 3
    np.testing.assert_allclose(maxima, [1, -1, 0])
