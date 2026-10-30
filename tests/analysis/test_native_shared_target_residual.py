import numpy as np
import pytest
from audit_single_target_native_measurements import target_residual


def test_shared_target_residual_does_not_subtract_bias_twice():
    times=np.array([1.,2.,3.]);residual=np.array([10.,-15.,5.])
    shared=dict(target_diagnostics=[dict(times_s=times,residual_hz=residual,bias_hz=300.)])
    new=dict(family=dict(diagnostics=[dict(times_s=times,raw_residual_hz=residual+300,profile_bias_hz=300.)]))
    np.testing.assert_array_equal(target_residual(shared,times),residual)
    np.testing.assert_array_equal(target_residual(new,times),residual)
    with pytest.raises(AssertionError):target_residual(shared,times+.1)
    with pytest.raises(ValueError,match='single target'):
        target_residual(dict(target_diagnostics=shared['target_diagnostics']*2),times)
