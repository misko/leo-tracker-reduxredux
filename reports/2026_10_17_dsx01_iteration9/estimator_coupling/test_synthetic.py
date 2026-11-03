import unittest
import numpy as np
from numpy.testing import assert_allclose
from synthetic import waveform,cases,FS,SAMPLES,TRUE_EPOCH


class InjectionTests(unittest.TestCase):
    def test_carrier_rotation_is_after_warp_and_preserves_envelope(self):
        positions=np.arange(SAMPLES)
        for warp in [-2000,0,2000]:
            base=waveform(0.,warp);shifted=waveform(100000.,warp)
            assert_allclose(abs(base),abs(shifted),atol=2e-15,rtol=0)
            assert_allclose(base,shifted*np.exp(-2j*np.pi*100000*positions/FS),atol=2e-15,rtol=0)

    def test_conditioning_controls_are_identical_iq_and_no_extra_cases(self):
        declared=cases();self.assertEqual(len(declared),11)
        reference=waveform(100000.,0.)
        for case in declared[-2:]:
            self.assertTrue(np.array_equal(reference,waveform(case['carrier_hz'],case['warp_ppm'])))
        self.assertEqual(TRUE_EPOCH,500.25)


if __name__=='__main__':unittest.main()
