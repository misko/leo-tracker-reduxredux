from __future__ import annotations

import numpy as np

from tools.ds7_orbit_matched_bank import replace_rows


def test_replace_rows_changes_only_selected_candidate_slots() -> None:
    original = np.arange(24).reshape(4, 2, 3)
    replacement = np.full((2, 2, 3), -1)
    result = replace_rows(original, replacement, [1, 3])

    assert np.array_equal(result[[0, 2]], original[[0, 2]])
    assert np.array_equal(result[[1, 3]], replacement)
    assert np.array_equal(original, np.arange(24).reshape(4, 2, 3))
