from types import SimpleNamespace
import numpy as np
import shared_satellite_refresh as refresh


def test_refresh_preserves_receiver_means_likelihood_and_source_arrays(monkeypatch):
    h=np.array([[1.,0.,2.,0.],[1.,1.,-2.,0.]])
    u=np.array([[1.,1.,1.,1.],[1.,-1.,-.5,1.],[1.,0.,2.,1.]])
    coefficient=np.array([1.,2.,3.,4.]);raw=np.array([100.,-100.]);old_curve=np.array([2.,3.,4.])
    base=dict(coefficient=coefficient,conditional_residual_hz=old_curve,linear_raw_prediction_residual_hz=raw,
        noise_precision=np.array([1.]),features=u,coefficient_prior_precision=np.ones(4),negative_twice_elbo=123.)
    p=SimpleNamespace(hardware=np.zeros((3,1)),smooth=np.zeros((3,1)),labels=[0],supported=[],
        noise_groups=np.zeros(3,int),keep=np.ones(3,bool),point_noise=np.full(3,150.),calculate=lambda x:base)
    monkeypatch.setattr(refresh,'linear_geometry',lambda p,e:(None,None,np.full(2,150.),np.zeros(2,int),None))
    monkeypatch.setattr(refresh,'geometry_features',lambda *a:{'features':h})
    refresh.attach_shared_satellite_refresh(p,[{}],np.ones(1),[0]);result=p.calculate(np.zeros(2))
    assert result['negative_twice_elbo']==123. and result['shared_satellite_receiver_change']==0.
    np.testing.assert_array_equal(result['coefficient'][[0,1,3]],coefficient[[0,1,3]])
    assert result['coefficient'][2]!=coefficient[2]
    np.testing.assert_array_equal(base['linear_raw_prediction_residual_hz'],raw)
    np.testing.assert_array_equal(base['conditional_residual_hz'],old_curve)
    delta=result['coefficient']-coefficient
    np.testing.assert_allclose(result['linear_raw_prediction_residual_hz'],raw-h@delta)
    np.testing.assert_allclose(result['conditional_residual_hz'],old_curve-u@delta)
