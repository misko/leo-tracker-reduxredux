import numpy as np
import pytest
from audit_independent_receiver_transfer import trend_projection


def test_shared_intercept_uncertainty_does_not_explain_a_drift():
    times=np.array([0.,2.,5.,9.]);r=400+3*times;correction=100+times
    intercept_cov=np.full((4,4),10000.)
    result=trend_projection(times,r,correction,intercept_cov)
    assert result['original_slope_hz_s']==pytest.approx(3)
    assert result['remaining_slope_hz_s']==pytest.approx(2)
    assert result['receiver_slope_sigma_hz_s']<1e-6
    drift_cov=.25*np.outer(times,times)
    assert trend_projection(times,r,correction,drift_cov)['receiver_slope_sigma_hz_s']==pytest.approx(.5)
    with pytest.raises(ValueError,match='time span'):
        trend_projection(np.ones(4),r,correction,drift_cov)
