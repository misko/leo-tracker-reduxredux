import numpy as np
from partial_header import local_word, variable_mask


def test_variable_selection_does_not_look_at_evaluation():
    bits = np.ones((7, 3), int)
    bits[1, 1] = -1
    bits[4, 0] = -1
    valid = np.ones_like(bits, bool)
    valid[0, 2] = False
    assert variable_mask(bits, valid).tolist() == [False, True, False]


def test_local_word_requires_unrestricted_word_equality_in_both_segments():
    rng = np.random.default_rng(660)
    signs = rng.choice([-1, 1], 60)
    z = signs[(np.arange(1004) - 16 * 6) % 60].astype(complex)
    fit = local_word(z, 300, 6)
    assert fit["accepted"]
    z[420:540] *= -1
    assert not local_word(z, 300, 6)["accepted"]
