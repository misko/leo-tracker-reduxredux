import numpy as np
import pytest
from leo.analysis.localization_geometry import stationary_range_rate_grid
from leo.analysis.localization_geometry_blas import stationary_range_rate_grid_blas


@pytest.mark.parametrize('strided',[False,True])
def test_matches_original_geometry(strided):
    rng=np.random.default_rng(194)
    p=rng.normal(size=(19,8,3));p*=7000/np.linalg.norm(p,axis=-1,keepdims=True)
    v=rng.normal(size=p.shape)*4
    r=rng.normal(size=(32,3));r*=6371/np.linalg.norm(r,axis=-1,keepdims=True)
    if strided:p=p[:,::2];v=v[:,::2];r=r[::2]
    up=r/np.linalg.norm(r,axis=-1,keepdims=True)
    expected=stationary_range_rate_grid(p,v,r,up)
    actual=stationary_range_rate_grid_blas(p,v,r,up)
    for a,b in zip(actual,expected):np.testing.assert_allclose(a,b,rtol=1e-11,atol=1e-11)


def test_rejects_zero_range_and_bad_up():
    p=np.array([[[6371.,0.,0.]]]);v=np.zeros_like(p);r=p[0]
    with pytest.raises(ValueError,match='squared range'):
        stationary_range_rate_grid_blas(p,v,r,np.array([[1.,0.,0.]]))
    with pytest.raises(ValueError,match='normalized'):
        stationary_range_rate_grid_blas(p,v,r,np.array([[2.,0.,0.]]))
