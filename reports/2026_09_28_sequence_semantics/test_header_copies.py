import numpy as np
from header_copies import select_pairs


def test_copy_selection_includes_inversions_and_excludes_constants():
    a = np.array([0, 1, 0, 1, 1, 0, 1], dtype=np.uint8)
    bits = np.stack([a, a, 1 - a, np.ones(7, dtype=np.uint8)], axis=1)
    valid = np.ones_like(bits, bool)
    assert select_pairs(bits, valid) == [(0, 1, 0), (0, 2, 1)]
    valid[0, 1] = False
    assert select_pairs(bits, valid) == [(0, 2, 1)]
