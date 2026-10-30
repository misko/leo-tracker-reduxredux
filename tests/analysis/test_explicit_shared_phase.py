import numpy as np
import pytest
from scipy.stats import norm,multivariate_normal
from explicit_shared_phase import conditional_phase
from ds23_predictive_linear import predictive_residual


def test_conditioned_phase_bias_reconciliation_and_density_normalization():
    a=np.array([3.,2.,-1.,4.]);g=np.array([[5.,1.,0.,0.],[1.,4.,1.,.3],[0.,1.,2.,.2],[0.,.3,.2,3.]])
    result=conditional_phase(a,g,1,[2],2.5);delta=result['delta']
    assert delta[0]==0 and delta[3]==0
    assert (g@delta)[2]==pytest.approx(0)
    variance=np.linalg.inv(g[np.ix_([1,2],[1,2])])[0,0]
    assert result['precision']==pytest.approx(1/variance)
    assert result['negative_twice_phase_log_density']==pytest.approx(-2*norm.logpdf(.5,scale=np.sqrt(variance)))
    assert not np.isclose(variance,np.linalg.inv(g)[1,1])
    np.testing.assert_array_equal(a,[3.,2.,-1.,4.])


def test_explicit_phase_integrates_to_same_conditional_predictive_gaussian():
    from scipy.integrate import quad
    a=np.zeros(3);g=np.array([[4.,.4,0.],[.4,2.,.5],[0.,.5,1.]])
    y=np.array([.7,-.2]);h=np.array([1.,2.]);noise=np.eye(2)*.4
    q=conditional_phase(a,g,1,[2],0)['precision']
    def density(phi):
        prior=conditional_phase(a,g,1,[2],phi)['negative_twice_phase_log_density']
        return np.exp(-.5*prior+multivariate_normal.logpdf(y,mean=h*phi,cov=noise))
    integral=quad(density,-10,10,epsabs=1e-12)[0]
    assert np.log(integral)==pytest.approx(multivariate_normal.logpdf(y,cov=noise+np.outer(h,h)/q),abs=1e-9)


def test_predictive_constants_only_keep_cross_point_covariance():
    raw=np.array([20.,-40.,90.]);sigma=np.array([50.,60.,70.]);groups=np.array([0,0,1])
    result=predictive_residual(raw,np.empty((3,0)),np.empty((0,0)),sigma*np.sqrt(2),groups)
    covariance=np.diag(2*sigma*sigma)+300**2*(groups[:,None]==groups[None,:])
    assert result['objective']==pytest.approx(-2*multivariate_normal.logpdf(raw,cov=covariance))


def test_invalid_phase_or_bias_coordinates_are_rejected():
    for biases in ([1],[0,0],[3]):
        with pytest.raises(ValueError):conditional_phase(np.zeros(3),np.eye(3),1,biases,0.)


def test_noise_and_power_ablation_factors_are_isolated_without_mutation():
    from types import SimpleNamespace
    from explicit_shared_phase import evidence_context
    scan=SimpleNamespace(fixed_window_noise={'extra_parameter_BIC_gain':12.},radio_sigma_hz=61.)
    d=dict(scan=scan,powers=np.array([.2,1.]))
    original=evidence_context(d,'original');weights=evidence_context(d,'unit_weights_only')
    noise=evidence_context(d,'fixed_noise_only');both=evidence_context(d,'annotation_fixed')
    assert original is d and weights['scan'] is scan
    np.testing.assert_array_equal(weights['powers'],[1.,1.]);np.testing.assert_array_equal(noise['powers'],[.2,1.])
    for q in (noise,both):assert q['scan'].radio_sigma_hz==150. and q['scan'].fixed_window_noise['extra_parameter_BIC_gain']==0.
    np.testing.assert_array_equal(both['powers'],[1.,1.])
    assert scan.radio_sigma_hz==61. and scan.fixed_window_noise['extra_parameter_BIC_gain']==12.
    np.testing.assert_array_equal(d['powers'],[.2,1.])
