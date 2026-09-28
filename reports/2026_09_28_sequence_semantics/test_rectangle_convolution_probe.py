import numpy as np
from blind_header_114 import mixed_null_check
from rectangle_convolution_probe import violations, windows, within_state_differences


def test_known_two_generator_relation_and_held_error():
    rng = np.random.default_rng(713)
    u = rng.integers(0, 2, size=(5, 38), dtype=np.uint8)
    y = u ^ np.roll(u, 1, axis=1)
    words = np.stack([u, y, rng.integers(0, 2, size=u.shape, dtype=np.uint8)], axis=-1).reshape(
        5, 114
    )
    w = windows(words, (0, 1))
    assert w.shape == (160, 14)
    mask = mixed_null_check(w, activity_floor=0)
    assert mask is not None and violations(w, mask) == 0
    w[0, (mask & -mask).bit_length() - 1] ^= 1
    assert violations(w, mask) == 1


def test_state_mask_cancels_and_unknown_evaluation_states_abstain():
    words = np.array([[1, 0], [0, 1], [0, 0], [1, 1], [1, 1], [0, 0], [1, 0]], dtype=np.uint8)
    states = np.array([0, 1, 0, 1, 0, 1, 2])
    train, held = within_state_differences(words, states, split=4)
    masks = np.array([[1, 1], [1, 0], [0, 1]], dtype=np.uint8)
    other_train, other_held = within_state_differences(words ^ masks[states], states, split=4)
    np.testing.assert_array_equal(train, other_train)
    np.testing.assert_array_equal(held, other_held)
    assert len(train) == 2 and len(held) == 2
