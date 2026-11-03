import numpy as np
import pytest

from ds23_fast_family_prediction import fast_gaussian_predictive
from ds23_family_predictive_selection import gaussian_predictive


@pytest.mark.parametrize('n,width',[(7,12),(90,8),(200,40)])
def test_low_rank_family_prediction_matches_dense_normalization_and_covariance(n,width):
    r=np.random.default_rng(715);a=r.normal(size=(100,width));u=r.normal(size=(n,width))
    y=r.normal(size=n);w=r.uniform(.1,2.,100);prior=r.uniform(.01,3.,width);sigma=r.uniform(.2,2.,n)
    expected=gaussian_predictive(y,u,a,w,prior,sigma)
    actual=fast_gaussian_predictive(y,u,a,w,prior,sigma)
    for key in ['negative_twice_log_density','quadratic','RMS_hz','marginal_sigma_hz']:
        np.testing.assert_allclose(actual[key],expected[key],atol=1e-9,rtol=1e-11)
