import numpy as np
from mean_shape import split


def test_factorization_with_correlated_paths():
    rng=np.random.default_rng(20261023);a=rng.normal(size=(12,5));k=a@a.T+np.eye(12);y=rng.normal(size=12)
    d=split(y,k,[(0,5),(5,12)])
    assert abs(d['replay_difference'])<1e-10
    assert d['level_dimensions']==2 and d['contrast_dimensions']==10


def test_constant_shift_cannot_change_temporal_contrast_score():
    k=np.eye(8)+np.ones((8,8));y=np.arange(8.)
    a=split(y,k,[(0,4),(4,8)]);b=split(y+np.r_[np.ones(4)*30,np.ones(4)*-20],k,[(0,4),(4,8)])
    assert np.isclose(a['contrasts']['total'],b['contrasts']['total'])
    assert not np.isclose(a['levels_given_contrasts']['total'],b['levels_given_contrasts']['total'])
