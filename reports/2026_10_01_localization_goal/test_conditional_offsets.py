"""Check the conditional Student-t density against the raw offset likelihood."""
import unittest

import numpy as np

from audit_conditional_offsets import conditional_offset


class OffsetTests(unittest.TestCase):
    def test_raw_density_ratio_identity(self):
        for n, q, precision in [(2, 0., .01), (8, 7., .001), (8, 70., .0001)]:
            df, scale, _ = conditional_offset(n, q, precision)
            x = np.linspace(-10*scale, 10*scale, 301)
            raw = -(4+n)/2*np.log((4+q+precision*x*x)/(4+q))
            conditional = -(df+1)/2*np.log1p(x*x/(df*scale*scale))
            np.testing.assert_allclose(raw, conditional, atol=1e-12)

    def test_raw_common_mode_is_not_identified_by_contrasts(self):
        n = 8
        c = np.eye(n)*10000
        contrast = np.eye(n)[1:]-np.eye(n)[0]
        shared = c+np.ones((n, n))*40000
        np.testing.assert_allclose(contrast@c@contrast.T, contrast@shared@contrast.T)
        ones = np.ones(n)
        a = conditional_offset(n, 7., ones@np.linalg.solve(c, ones))[2]
        b = conditional_offset(n, 7., ones@np.linalg.solve(shared, ones))[2]
        self.assertGreater(b, 4*a)


if __name__ == '__main__':
    unittest.main()
