import numpy as np
import pytest
from recursive_quad_starts import quad_starts,remaining_quad_budget


def fixture():
    return dict(pair_states=[np.array([1,2,11,12,13]),np.array([3,4,21,22,23])],
        pair_scans=[['a','b'],['c','d']],pair_columns=[[[0,1,2],[0,1,3,4]],[[0,1,2,3],[0,1,4]]],
        target_scans=['a','b','c','d'],target_columns=[[0,1,2],[0,1,3,4],[0,1,5,6],[0,1,7]],dimension=8)


def test_transfer_unequal_scans_and_reordered_pairs_preserves_nuisances():
    args=fixture();actual=quad_starts(**args)
    np.testing.assert_array_equal(actual,[[1,2,11,12,13,21,22,23],[3,4,11,12,13,21,22,23]])
    for key in ['pair_states','pair_scans','pair_columns']:args[key]=args[key][::-1]
    np.testing.assert_array_equal(quad_starts(**args),actual)
    actual[0,2]=999;assert args['pair_states'][1][2]==11


def test_reject_duplicate_scan_and_incomplete_mapping():
    args=fixture();args['pair_scans'][1][0]='a'
    with pytest.raises(ValueError,match='duplicate'):quad_starts(**args)
    args=fixture();args['pair_columns'][0][1]=[0,1,3]
    with pytest.raises(ValueError,match='incomplete'):quad_starts(**args)


def test_pair_totals_already_include_singles_and_can_exhaust_budget():
    assert remaining_quad_budget([110,120])==(230,130)
    assert remaining_quad_budget([180,175])==(355,5)
    with pytest.raises(ValueError):remaining_quad_budget([100,float('nan')])
