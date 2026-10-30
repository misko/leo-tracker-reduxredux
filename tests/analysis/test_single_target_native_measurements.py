import numpy as np
import pytest
from audit_single_target_native_measurements import polynomial_measurements


def test_native_polynomial_replay_respects_legendre_and_time_scaling():
    t=np.array([2.,3.,4.]);z=(t-3)/2
    y=np.polynomial.legendre.legval(z,[10,4,2])
    track=dict(times=t,values=y+[1,-1,2],pieces=[dict(coefficients_hz=[10,4,2],reference_time_s=3,time_scale_s=2)])
    r,rate=polynomial_measurements(track)
    np.testing.assert_allclose(r,[1,-1,2])
    np.testing.assert_allclose(rate,(4+6*z)/2)
    with pytest.raises(ValueError):polynomial_measurements(dict(track,pieces=[]))
