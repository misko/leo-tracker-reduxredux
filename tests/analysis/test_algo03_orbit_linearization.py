import numpy as np
from probe_algo03_orbit_linearization import state_doppler


def test_exact_range_rate_has_doppler_sign_and_rotational_invariance():
    position=np.array([[1000.,0.,0.],[0.,1000.,0.]])
    velocity=np.array([[1.,0.,0.],[1.,0.,0.]])
    expected=np.array([-11.5e9/299792.458,0.])
    np.testing.assert_allclose(state_doppler(position,velocity,np.zeros(3)),expected)
    rotation=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    np.testing.assert_allclose(state_doppler(position@rotation.T,velocity@rotation.T,np.zeros(3)),expected)
