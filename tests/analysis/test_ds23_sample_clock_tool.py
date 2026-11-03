import numpy as np
import pytest
from ds23_sample_clock import clock_geometry,clock_columns,make_clock_problem
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from test_ds23_height_problem import example


def fixture():
    p=example();p.flat_rx=p.flat_labels+1
    return p


def test_zero_rate_replays_all_original_geometry_features():
    p=fixture();expected=geometry_features(p,np.zeros(2),0.);actual=clock_geometry(p,np.zeros(2),np.zeros(2))
    for key in ('features','frequency','intercept','derivative','elevation'):
        np.testing.assert_array_equal(actual[key],expected[key])


def test_clock_derivative_has_frequency_and_time_scaling_with_receiver_isolation():
    p=fixture();x=np.zeros(2);orbit=np.zeros(6);g=geometry_features(p,x,0.);h=.001
    p.flat_times+=h;plus=geometry_features(p,x,0.)['frequency'];p.flat_times-=2*h
    minus=geometry_features(p,x,0.)['frequency'];p.flat_times+=h
    derivative=(plus-minus)/(2*h)
    expected=-p.q*(g['frequency']+p.flat_times*derivative)
    columns=clock_columns(p,x,orbit)
    np.testing.assert_allclose(columns.sum(axis=1),expected,rtol=3e-5,atol=.03)
    assert np.all(columns[p.flat_rx==2,0]==0) and np.all(columns[p.flat_rx==1,1]==0)


def test_clock_zero_sigma_columns_integrate_to_one_under_student_phase_prior(monkeypatch):
    import ds23_sample_clock as module
    from types import SimpleNamespace
    p=fixture();p.scan=SimpleNamespace(tracks=[dict(times=np.zeros(12),receiver=1),dict(times=np.zeros(12),receiver=2)])
    monkeypatch.setattr(module,'make_problem',lambda *a,**k:p)
    weights=np.array([1.,.6]);mu=np.array([.1,-.1]);g=geometry_features(p,np.zeros(2),0.);features=g['features'];width=features.shape[1]
    mean=np.zeros(width);mean[10:12]=mu/p.phase_sigma;groups=np.full(width,-1,int);groups[10:12]=[0,1]
    scale=np.ones(width);scale[-2:]=.3
    expected=hierarchical_bound(p.values-p.q*g['intercept']-features@mean,features*scale,p.point_noise,p.noise_groups,
        powers=weights,prior_groups=groups,prior_nu=3.)
    actual=make_clock_problem(p.scan,None,p.keep,'c0',p.reference,weights,mu,dict(nu=3.,multiplier=1.),0.).calculate(np.zeros(2))
    np.testing.assert_allclose(actual['negative_twice_elbo'],expected['negative_twice_elbo'],atol=1e-8,rtol=1e-12)
    np.testing.assert_array_equal(actual['sample_clock_ppm'],np.zeros(2))


def test_known_small_clock_error_matches_linearized_physical_signal():
    p=fixture();x=np.array([3.,-2.]);epsilon=np.array([25.,-30.])*1e-6
    base=clock_geometry(p,x,np.zeros(2));truth=clock_geometry(p,x,epsilon)
    actual=p.q*(truth['frequency']-base['frequency']);linear=clock_columns(p,x,np.zeros(6))@epsilon
    np.testing.assert_allclose(actual,linear,atol=.001,rtol=.003)
    with pytest.raises(ValueError):clock_geometry(p,x,np.array([np.nan,0.]))
