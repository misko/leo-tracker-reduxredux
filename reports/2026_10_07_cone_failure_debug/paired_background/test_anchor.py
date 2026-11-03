import unittest
import numpy as np
from anchor_probe import anchored_clock_seeds
import test_initializer as initializer_fixture
from experiment import clock_metrics

class AnchorInitializerTests(unittest.TestCase):
    def test_both_anchors_retain_selected_rx_and_all_nonclock_state(self):
        obs,base,v,true,pairs=initializer_fixture.ClockInitializerTests().synthetic();original=v.copy()
        anchors,meta=anchored_clock_seeds(obs,base,v,pairs)
        np.testing.assert_array_equal(v,original)
        for anchor,result in anchors.items():
            np.testing.assert_array_equal(result[:2],v[:2])
            np.testing.assert_array_equal(result[6:],v[6:])
            held=[2,3] if anchor=='anchor-rx0' else [4,5]
            np.testing.assert_array_equal(result[held],v[held])
            self.assertAlmostEqual(result[4]-result[2],meta['differential_offset_hz'],places=10)
            self.assertAlmostEqual(result[5]-result[3],meta['differential_slope_hz_s'],places=10)
            self.assertLess(clock_metrics(obs,base,result,pairs)['median_absolute_residual_hz'],1e-5)

if __name__=='__main__':unittest.main()
