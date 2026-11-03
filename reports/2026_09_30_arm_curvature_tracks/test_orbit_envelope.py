import unittest
import numpy as np
from orbit_envelope import visible_curvature


class EnvelopeTests(unittest.TestCase):
    def test_straight_pass_matches_analytic_curvature(self):
        times = np.arange(-200., 201.)
        speed, altitude = 7.5, 550.
        states = np.zeros((1,len(times),6))
        states[0,:,0] = speed*times
        states[0,:,2] = altitude
        states[0,:,3] = speed
        measured, _ = visible_curvature(states,[0,0,0],[0,0,1],1)
        t = times[1:-1]
        analytic = (3*(11.2e9/299792.458)*speed**4*altitude**2*t /
                    (altitude**2+speed**2*t*t)**2.5)
        np.testing.assert_allclose(measured,analytic,atol=.02,rtol=.002)

    def test_horizon_rejects_below_horizon(self):
        states = np.zeros((1,5,6)); states[:,:,2] = -550
        curvature, _ = visible_curvature(states,[0,0,0],[0,0,1],1)
        self.assertEqual(len(curvature),0)

    def test_invalid_states_are_rejected(self):
        states = np.zeros((1,5,6)); states[:,:,2] = 550
        states[0,0,3] = np.nan
        with self.assertRaises(ValueError):
            visible_curvature(states,[0,0,0],[0,0,1],1)


if __name__ == "__main__":
    unittest.main()
