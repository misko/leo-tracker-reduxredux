import numpy as np
import pytest
from plot_ds23_algo_candidate_distributions import keyed,align,empirical


def test_comparison_rejects_duplicate_and_mismatched_scan_membership():
    row=dict(method='x',arm='c0',case='a',error='1')
    with pytest.raises(ValueError,match='duplicate'):keyed([row,row],'x','error')
    with pytest.raises(ValueError,match='exact same'):align({('c0','a'):row},{('c0','b'):row})
    with pytest.raises(ValueError,match='finite'):keyed([dict(row,error='nan')],'x','error')


def test_ecdf_and_tail_include_ties_and_the_last_outlier():
    x,cdf,tail=empirical([1,1,20])
    np.testing.assert_array_equal(x,[1,20])
    np.testing.assert_allclose(cdf,[2/3,1]);np.testing.assert_allclose(tail,[1,1/3])
