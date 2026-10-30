import numpy as np
import pytest
from probe_shared_phase_feasibility import fixed_alias_constant, sampled_intervals


def test_conditional_constant_obeys_weighted_normal_equation_without_alias_wrapping():
    y=np.array([230000.,230100.,230200.]);w=np.array([1.,2.,4.])/150**2;prior=1/300**2
    result=fixed_alias_constant(y,w,prior)
    b=result['bias_hz']
    assert b>200000  # diagnostic must not silently choose a different alias
    assert w@(y-b)==pytest.approx(prior*b)
    np.testing.assert_allclose(np.diff(result['residual_hz']),np.diff(y))
    assert result['cost']==pytest.approx(w@((y-b)**2)+prior*b*b)
    for shift in (-1.,1.):
        assert w@((y-b-shift)**2)+prior*(b+shift)**2>result['cost']
    with pytest.raises(ValueError):fixed_alias_constant(y,-w,prior)


def test_support_intervals_preserve_holes_and_single_samples():
    grid=np.array([-1.,-.1,0.,.01,.2,1.])
    assert sampled_intervals(grid,[0,1,1,0,1,0])==[[-.1,0.,2],[.2,.2,1]]
    assert sampled_intervals(grid,np.zeros(6,bool))==[]
    with pytest.raises(ValueError):sampled_intervals([0,0],[True,True])


def test_constant_coordinate_respects_prior_guard_scaling():
    from types import SimpleNamespace
    from probe_shared_phase_feasibility import constant_scale
    p=SimpleNamespace(constants=np.array([[1000.,0.],[1000.,0.],[0.,3000.],[0.,3000.]]),
        slices=[slice(0,2),slice(2,4)])
    assert constant_scale(p,0)==1000.
    assert constant_scale(p,1)==3000.
    precision=1/.3**2
    assert 1/np.sqrt(precision/constant_scale(p,1)**2)==pytest.approx(900.)
