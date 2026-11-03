import numpy as np
from ds23_radio_correlation import correlation,contrasts,whitener,learn


def test_reml_contrasts_remove_polynomial_without_using_orbit_prediction():
    t=np.arange(30.);noise=np.sin(t);y=1e5+20*t+3*t*t+noise
    b,z=contrasts(t,y,2)
    np.testing.assert_allclose(z,b.T@noise,atol=1e-10)
    np.testing.assert_allclose(b.T@b,np.eye(27),atol=1e-14)


def test_whitening_preserves_declared_marginal_variance_and_white_null():
    t=np.array([0.,1.,4.]);sigma=np.array([2.,3.,4.])
    w,ld=whitener(t,sigma,.6,3.)
    covariance=sigma[:,None]*correlation(t,.6,3.)*sigma[None,:]
    np.testing.assert_allclose(w@covariance@w.T,np.eye(3),atol=1e-14)
    np.testing.assert_allclose(ld,np.linalg.slogdet(covariance)[1])
    np.testing.assert_array_equal(whitener(t,sigma,0.,3.)[0],np.diag(1/sigma))


def test_no_eligible_radio_curves_keeps_white_model():
    assert learn([])["alpha"]==0.
