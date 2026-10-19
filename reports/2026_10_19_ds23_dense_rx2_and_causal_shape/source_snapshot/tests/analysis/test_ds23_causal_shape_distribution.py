import numpy as np
from ds23_causal_shape_distribution import nll,fit_covariance,select


def test_student_density_normalization_and_unit_variance_parameterization():
    from math import lgamma
    z=np.zeros((1,1));expected=np.log(np.pi)+2*lgamma(1.5)-2*lgamma(2.)
    np.testing.assert_allclose(nll(z,np.eye(1),3),[expected])


def test_fitted_covariance_recovers_correlated_heavy_tailed_parameter_errors():
    rng=np.random.default_rng(31);cov=np.array([[2.,.7],[.7,.6]])
    z=rng.normal(size=(20000,2))@np.linalg.cholesky(cov).T/np.sqrt(rng.chisquare(3,20000)[:,None])
    estimated=fit_covariance(z)
    np.testing.assert_allclose(estimated,cov,rtol=.1,atol=.05)


def test_causal_validation_can_reject_a_training_selected_distribution():
    rng=np.random.default_rng(17);rows=[]
    for event in range(10):
        z=rng.normal(size=(100,5))*(.2 if event<7 else 1)
        rows += [dict(validation_time_ns=event,z=v) for v in z]
    selected=select(rows)
    assert selected['trained_model']!='Gaussian_I'
    assert not selected['qualified'] and selected['model']=='Gaussian_I'


def test_shape_prior_transform_leaves_phase_hardware_and_other_families_separate():
    from probe_ds23_history_shape_prior import shape_coordinates
    cov=np.diag([1,2,3,4,5]);t,g=shape_coordinates(8,3,2,4,cov,True)
    np.testing.assert_allclose(t[:11,:11],np.eye(11))
    np.testing.assert_allclose(t[-4:,-4:],np.eye(4))
    first=[11,12,13,17,18];second=[14,15,16,19,20]
    np.testing.assert_allclose((t@t.T)[np.ix_(first,first)],cov)
    np.testing.assert_allclose((t@t.T)[np.ix_(first,second)],0)
    assert set(g[first])=={3} and set(g[second])=={4}
