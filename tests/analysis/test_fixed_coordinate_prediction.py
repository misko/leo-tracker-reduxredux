import numpy as np
import pytest
from scipy.stats import multivariate_normal
from leo.analysis.research.fixed_coordinate_prediction import fixed_coordinate_prediction


def test_fixed_receiver_uses_conditional_precision_and_reconciles_correlated_bias():
    mean=np.array([5.,1.,-2.]);gram=np.array([[4.,1.,0.],[1.,3.,1.],[0.,1.,2.]])
    design=np.array([[1.,1.,0.],[2.,3.,0.]])
    raw=np.array([2.,4.]);noise=np.diag([1.,2.]);free=[1,2]
    original=[x.copy() for x in (mean,gram,design,raw,noise)]
    q=gram[np.ix_(free,free)];h=design[:,free]
    delta=np.linalg.solve(q+h.T@np.linalg.solve(noise,h),h.T@np.linalg.solve(noise,raw))
    result=fixed_coordinate_prediction(mean,gram,design,raw,noise,free)
    np.testing.assert_allclose(result['coefficient'][free],mean[free]+delta)
    assert result['coefficient'][0]==mean[0]
    assert delta[1]!=0  # bias changes even though new observations have no bias column
    expected=noise+h@np.linalg.solve(q,h.T)
    np.testing.assert_allclose(result['predictive_covariance'],expected)
    assert result['negative_twice_log_density']==pytest.approx(-2*multivariate_normal.logpdf(raw,cov=expected))
    marginal=np.linalg.inv(gram)[np.ix_(free,free)]
    assert not np.allclose(result['conditional_prior_covariance'],marginal)
    for before,after in zip(original,(mean,gram,design,raw,noise),strict=True):np.testing.assert_array_equal(before,after)


def test_all_coordinates_matches_full_gaussian_and_rejects_bad_coordinates():
    a=np.zeros(2);g=np.array([[2.,.5],[.5,1.]]);h=np.eye(2);r=np.array([1.,3.]);n=np.eye(2)
    result=fixed_coordinate_prediction(a,g,h,r,n,[0,1])
    np.testing.assert_allclose(result['coefficient'],np.linalg.solve(g+np.eye(2),r))
    for indices in ([1,1],[2],[.5],[]):
        with pytest.raises(ValueError,match='coordinate indices'):fixed_coordinate_prediction(a,g,h,r,n,indices)


def test_family_coordinate_mapping_keeps_receiver_and_other_family_fixed():
    from types import SimpleNamespace
    from probe_native_parameter_consistency import coordinate_sets
    p=SimpleNamespace(hardware=np.empty((0,2)),smooth=np.empty((0,3)),labels=[7,8,9],supported=[8],
        rows=[{'candidate_index':j} for j in (7,8,8,9)],event_start=15)
    s=coordinate_sets(p,8)
    assert s['phase_orbit_fixed_bias']==[6,8,9,10]
    assert s['phase_orbit_bias']==[6,8,9,10,12,13]
    assert s['bias_only']==[12,13]
    assert set(s['phase_orbit_bias']).isdisjoint(s['receiver_only'])
    assert 5 not in s['phase_orbit_bias'] and 7 not in s['phase_orbit_bias']
    from conditional_satellite_refresh import family_coordinates
    assert family_coordinates(p,[8])==s['phase_orbit_bias']
    assert family_coordinates(p,[8],include_bias=False)==s['phase_orbit_fixed_bias']


def test_woodbury_position_update_matches_dense_conditional_prediction():
    from conditional_satellite_refresh import conditional_update
    mean=np.array([2.,3.,4.]);gram=np.array([[4.,1.,0.],[1.,3.,1.],[0.,1.,2.]])
    design=np.array([[1.,2.,0.],[3.,4.,0.],[2.,-1.,0.]])
    residual=np.array([20.,-30.,100.]);sigma=np.array([40.,50.,60.]);groups=np.array([0,0,1]);indices=[1,2]
    noise=np.diag(2*sigma*sigma)+300.**2*(groups[:,None]==groups[None,:])
    dense=fixed_coordinate_prediction(mean,gram,design,residual,noise,indices)
    shift,prediction,distance=conditional_update(mean,gram,design,residual,sigma,groups,indices)
    np.testing.assert_allclose(mean+shift,dense['coefficient'])
    assert prediction['objective']==pytest.approx(dense['negative_twice_log_density'])
    assert distance==pytest.approx(dense['shift_mahalanobis'])
    assert shift[0]==0
