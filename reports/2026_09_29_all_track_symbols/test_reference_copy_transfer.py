import numpy as np
from reference_copy_transfer import frozen_pairs


def test_reference_copy_must_survive_later_frames_without_refitting():
    x = np.tile([0, 1], 39).astype(np.uint8)
    bits = np.stack([x, x, 1 - x], axis=1)
    valid = np.ones_like(bits, dtype=bool)
    candidates, survivors = frozen_pairs(bits, valid)
    assert len(candidates) == len(survivors) == 2
    bits[-1, 1] ^= 1
    candidates, survivors = frozen_pairs(bits, valid)
    assert len(candidates) == 2 and len(survivors) == 1
    assert survivors[0] == (0, 2, 1)


def test_unqualified_later_copy_is_not_counted_as_a_pass():
    x = np.tile([0, 1], 39).astype(np.uint8)
    bits = np.stack([x, x], axis=1)
    valid = np.ones_like(bits, dtype=bool)
    valid[-1, 0] = False
    candidates, survivors = frozen_pairs(bits, valid)
    assert len(candidates) == 1 and not survivors
