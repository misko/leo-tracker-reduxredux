import numpy as np
import pytest
from association_mass import summarize_scores


def test_uniform_mass_entropy_and_topk_bounds():
    r=summarize_scores(np.zeros(8))
    assert r['entropy']==pytest.approx(np.log(8))
    assert r['effective_branches']==pytest.approx(8)
    assert r['omitted_mass']=={'1':.875,'2':.75,'4':.5}
    assert r['marginal_correction']==pytest.approx(np.log(8))


def test_extreme_scores_shift_invariance_and_zero_mass():
    r=summarize_scores([10000,9999,-np.inf,-10000])
    s=summarize_scores([0,-1,-np.inf,-20000])
    assert r==s and r['mass_sum']==pytest.approx(1)
    assert r['omitted_mass']['2']==0 and 0<=r['entropy']<=np.log(4)
    assert 0<=r['marginal_correction']<=np.log(4)


def test_invalid_scores_rejected():
    for x in [[1],[np.nan,0],[np.inf,0],[-np.inf,-np.inf]]:
        with pytest.raises(ValueError):summarize_scores(x)
