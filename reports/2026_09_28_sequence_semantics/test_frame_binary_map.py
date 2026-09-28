import numpy as np
from frame_binary_map import intervals


def test_inclusive_symbol_numbering_and_boundaries():
    assert intervals(np.array([True, True, False, True])) == [[2, 3], [5, 5]]
    assert intervals(np.ones(300, dtype=bool)) == [[2, 301]]
    assert intervals(np.zeros(300, dtype=bool)) == []
