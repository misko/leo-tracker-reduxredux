import numpy as np
from state_transfer import templates, transfer


def test_state_templates_generalize_to_new_noisy_samples():
    rng = np.random.default_rng(17)
    labels = np.repeat([0, 1], 20)
    patterns = rng.normal(size=(2, 3, 12))
    train = patterns[labels] + rng.normal(size=(40, 3, 12)) * .1
    target = patterns[[0, 1]] + rng.normal(size=(2, 3, 12)) * .1
    result = transfer(train, target, labels, np.array([0, 1]),
                      [rng.permutation(labels) for _ in range(19)])
    assert result["state_over_global_error_reduction"] > .9
    assert result["shuffled_state_exceedances"] == 0


def test_constant_pattern_is_not_state_information():
    labels = np.array([0, 0, 1, 1])
    train = np.ones((4, 2, 3))
    target = np.ones((2, 2, 3)) * 1.1
    result = transfer(train, target, labels, np.array([0, 1]), [labels[::-1]])
    assert result["state_over_global_error_reduction"] == 0
    assert np.array_equal(templates(train, labels, [1, 0]), np.ones((2, 2, 3)))
