import numpy as np
from audit import range_doppler,REFERENCE_RF_HZ,LIGHT_KM_S

def test_known_radial_velocity_sign_and_scale():
    h=.05;receiver=np.array([6378.,0.,0.]);times=np.array([-h,h])
    positions=np.zeros((1,2,3,3));positions[...,0]=7000+2*times[None,:,None]
    np.testing.assert_allclose(range_doppler(positions,receiver,h),-2*REFERENCE_RF_HZ/LIGHT_KM_S,rtol=1e-10)
