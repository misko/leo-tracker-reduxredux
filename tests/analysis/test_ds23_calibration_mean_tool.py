import copy
import numpy as np
from ds23_calibration_mean import mean_problem
from ds23_height_problem import geometry_features
from ds23_predictive_linear import predictive_residual
from test_ds23_height_problem import example


def test_known_receiver_translation_preserves_bound_residuals_and_predictions_at_multiple_sites(monkeypatch):
    import ds23_calibration_mean as module
    original=example();original.smooth[:,0]=original.q*np.sin(original.flat_times/80)
    original.smooth[:,1]=original.q*np.cos(original.flat_times/80)
    weights=np.array([1.,.6]);mu=np.array([.1,-.2]);model=dict(multiplier=1.,nu=3.)
    for x in (np.zeros(2),np.array([5.,-2.])):
        monkeypatch.setattr(module,'make_problem',lambda *a,**k:copy.deepcopy(original))
        a=mean_problem(None,None,original.keep,'c0',original.reference,weights,mu,model,1,0).calculate(x)
        shifted=copy.deepcopy(original);kappa=-1.3;index=original.hardware.shape[1]+1
        u=geometry_features(original,x,0.)['features'];shifted.values+=u[:,index]*kappa
        monkeypatch.setattr(module,'make_problem',lambda *a,**k:copy.deepcopy(shifted))
        b=mean_problem(None,None,original.keep,'c0',original.reference,weights,mu,model,1,kappa).calculate(x)
        for key in ('negative_twice_elbo','conditional_residual_hz','latent_coefficient','noise_precision','coefficient_prior_precision'):
            np.testing.assert_allclose(a[key],b[key],atol=2e-7,rtol=1e-9)
        expected=a['coefficient'].copy();expected[index]+=kappa
        np.testing.assert_allclose(b['coefficient'],expected,atol=1e-8)
        # Added linear evidence shares the same translated calibration mean.
        ul=u[:8];y=np.linspace(-50,50,8);groups=np.zeros(8,int)
        g=np.diag(a['coefficient_prior_precision'])+u.T@(u*(weights[original.noise_groups]*a['noise_precision'][original.noise_groups]/original.point_noise**2)[:,None])
        before=predictive_residual(y-ul@a['coefficient'],ul,g,np.full(8,100.),groups)
        after=predictive_residual(y+ul[:,index]*kappa-ul@b['coefficient'],ul,g,np.full(8,100.),groups)
        np.testing.assert_allclose(before['objective'],after['objective'],atol=1e-8)


def test_synthetic_receiver_perturbation_preserves_original_values_and_other_receiver():
    from types import SimpleNamespace
    from probe_ds23_receiver_invariance import perturb
    first=np.array([10.,20.]);second=np.array([30.,40.])
    scan=SimpleNamespace(tracks=[dict(values=first,receiver=1,rf_hz=11.5e9),
        dict(values=second,receiver=2,rf_hz=11.5e9)],rx_basis=[np.array([[.5],[-.5]]),np.ones((2,1))])
    result=perturb(scan,1,0,1.)
    np.testing.assert_array_equal(scan.tracks[0]['values'],first)
    np.testing.assert_array_equal(scan.tracks[1]['values'],second)
    np.testing.assert_array_equal(result.tracks[0]['values'],[110.,-80.])
    np.testing.assert_array_equal(result.tracks[1]['values'],second)
    assert result.tracks[0] is not scan.tracks[0]
