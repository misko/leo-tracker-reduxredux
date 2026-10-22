import numpy as np

from ds23_active_mode_support import disabled_families


def test_masked_owners_do_not_authorize_new_shape_modes_but_incumbent_design_is_preserved():
    rows = [dict(candidate_index=k) for k in [1, 1, 2, 2, 3, 3]]
    tracks = [dict(receiver=r, channel=c) for r, c in [(1, 1), (2, 1), (1, 2), (2, 2), (1, 3), (2, 3)]]
    slices = [slice(k, k+1) for k in range(6)]
    members = list(range(6))
    mask = np.array([True, False, True, True, True, False])
    assert disabled_families([1, 2, 3], rows, slices, members, tracks, mask, {3}) == [1]
    assert disabled_families([1, 2, 3], rows, slices, members, tracks, np.zeros(6, bool), {3}) == []
