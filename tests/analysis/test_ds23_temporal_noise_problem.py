import numpy as np
from ds23_radio_correlation import correlation
from ds23_predictive_linear import predictive_residual
from ds23_temporal_noise_problem import correlated_prediction


def test_temporal_prediction_matches_dense_gaussian_and_independent_null():
    rng=np.random.default_rng(2);y=rng.normal(size=6)*100
    design=rng.normal(size=(6,2))*30;gram=np.array([[2.,.1],[.1,3.]])
    sigma=np.full(6,40.);times=np.array([0.,1.,3.,0.,2.,4.]);slices=[slice(0,3),slice(3,6)]
    for alpha in (0.,.6):
        result=correlated_prediction(y,design,gram,sigma,times,slices,alpha,3.)
        covariance=design@np.linalg.solve(gram,design.T)
        for sl in slices:
            covariance[sl,sl]+=2*40**2*correlation(times[sl],alpha,3.)+300**2*np.ones((3,3))
        expected=y@np.linalg.solve(covariance,y)+np.linalg.slogdet(covariance)[1]+6*np.log(2*np.pi)
        np.testing.assert_allclose(result["objective"],expected,rtol=1e-12)
        if not alpha:
            null=predictive_residual(y,design,gram,sigma*np.sqrt(2),np.repeat([0,1],3))
            np.testing.assert_allclose(result["objective"],null["objective"],rtol=1e-12)
