import unittest
import numpy as np
from run import compare,observation_key


class OverlapTest(unittest.TestCase):
    def test_mean_offset_is_removed_and_different_slope_retained(self):
        t=np.arange(10,dtype=np.int64)*1_000_000_000
        y=np.arange(10.)*100
        self.assertAlmostEqual(compare(t,y,t,y+800)['centered_rms_hz'],0)
        r=compare(t,y,t,y+np.arange(10.)*20)
        self.assertGreater(r['centered_rms_hz'],10)
        self.assertAlmostEqual(r['detrended_rms_hz'],0)

    def test_support_and_identity(self):
        t=np.arange(7,dtype=np.int64)*1_000_000_000
        self.assertIsNone(compare(t,np.zeros(7),t,np.zeros(7)))
        self.assertNotEqual(observation_key(0,1e9,1.,2.),observation_key(1,1e9,1.,2.))
        self.assertNotEqual(observation_key(0,1e9,1.,2.),observation_key(0,1e9,1.,3.))


if __name__=='__main__':
    unittest.main()
