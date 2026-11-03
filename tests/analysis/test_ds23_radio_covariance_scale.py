import numpy as np
from ds23_radio_covariance_scale import variance_ratio
from ds23_radio_correlation import contrasts,correlation


def test_white_covariance_keeps_radio_variance_and_correlated_ratio_uses_reml():
    t=np.arange(30.);y=1000+20*t+np.sin(t)
    track=dict(times=t,values=y,observation_ids=[str(k) for k in range(30)],
               pieces=[dict(start_s=0.,end_s=29.,degree=1)])
    np.testing.assert_allclose(variance_ratio([track],0.,10.)["marginal_variance_ratio"],1.)
    b,z=contrasts(t,y,1);covariance=b.T@correlation(t,.6,10.)@b
    expected=z@np.linalg.solve(covariance,z)/(z@z)
    np.testing.assert_allclose(variance_ratio([track],.6,10.)["marginal_variance_ratio"],expected)
    assert variance_ratio([],0.,10.)["marginal_variance_ratio"]==1.
