import numpy as np
from audit import exclude_family


def test_excludes_every_active_family_point_and_preserves_unrelated_partial_mask():
    rows=[{'candidate_norad':52311},{'candidate_norad':66102},{'candidate_norad':52311}]
    slices=[slice(0,3),slice(3,6),slice(6,8)]
    original=np.array([1,0,1,0,1,1,1,0],bool);before=original.copy()
    keep,removed=exclude_family(rows,slices,original,52311)
    np.testing.assert_array_equal(keep,[0,0,0,0,1,1,0,0])
    np.testing.assert_array_equal(removed,[1,0,1,0,0,0,1,0])
    np.testing.assert_array_equal(original,before)
    assert keep.sum()+removed.sum()==original.sum()


def test_absent_family_changes_no_observation():
    original=np.array([1,0,1],bool)
    keep,removed=exclude_family([{'candidate_norad':66102}],[slice(0,3)],original,52311)
    np.testing.assert_array_equal(keep,original)
    assert not removed.any()
