import numpy as np
import pytest
from ds23_gate_null import GateState,gate_score,profiled,calibration_cutoff,unit_shape
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile


def test_gate_score_exactly_reproduces_all_legacy_statistical_decisions():
    rng=np.random.default_rng(9);t=np.linspace(0,50,31);r=rng.normal(size=(31,200))*120
    r[:,30:50]+=unit_shape(t,'slope')[:,None]*150
    np.testing.assert_array_equal(gate_score(r,t)<=1,batch_noise_screen(r.T,t)['noise_screen_pass'])


def test_profile_projection_matches_existing_noise_innovations():
    rng=np.random.default_rng(11);r=rng.normal(size=(23,15))*100+300
    for bias in (300.,1000.):
        expected=profile(r.T[0],np.zeros(23),np.eye(23)/150,bias_sigma=bias)['innovations'][0]
        np.testing.assert_allclose(profiled(r,bias)[:,0],expected,atol=1e-12)


def test_fixed_precision_refit_matches_dense_augmented_ridge_for_each_draw():
    rng=np.random.default_rng(5);u=rng.normal(size=(12,3));p=np.array([2.,3.,4.]);w=np.linspace(.2,2,12)
    mean=np.array([.1,.2,.3]);truth=np.array([.7,-.1,.8]);e=rng.normal(size=(12,7))
    state=GateState(u,p,w,mean,truth,[],np.zeros((0,3)),[],3,0)
    rc,_,fit=state.residuals(e,np.zeros((0,7)),np.zeros((0,7)),mode='fitted_plugin')
    for k in range(7):
        a=np.vstack((u*np.sqrt(w)[:,None],np.diag(np.sqrt(p))))
        b=np.r_[(u@(truth-mean)+e[:,k])*np.sqrt(w),np.zeros(3)]
        expected=mean+np.linalg.lstsq(a,b,rcond=None)[0]
        np.testing.assert_allclose(fit[:,k],expected,atol=1e-12)
        np.testing.assert_allclose(rc[:,k],e[:,k]+u@(truth-expected),atol=1e-12)


def test_monte_carlo_quantile_uses_separate_validation_and_never_tightens_legacy():
    rng=np.random.default_rng(16);train=rng.exponential(size=4096);test=rng.exponential(size=16384)
    cutoff=calibration_cutoff(train)
    assert .035<np.mean(test>cutoff)<.065
    assert calibration_cutoff(np.zeros(1024))==1.
    with pytest.raises(ValueError):calibration_cutoff(np.zeros(2),.01)


def test_shapes_have_unit_RMS_and_quadratic_has_no_affine_component():
    t=np.linspace(0,100,33)
    for name in ('slope','quadratic','step'):
        v=unit_shape(t,name);assert np.mean(v)==pytest.approx(0,abs=1e-12)
        assert np.mean(v*v)==pytest.approx(1)
    assert unit_shape(t,'quadratic')@(t-t.mean())==pytest.approx(0,abs=1e-10)
