import unittest
import numpy as np
from plot_complete_overlay import wrapped_curve
from benchmark import ALIAS_HZ


class OverlayTests(unittest.TestCase):
    def test_wrap_seam_is_not_drawn_as_vertical_trajectory(self):
        y=wrapped_curve([ALIAS_HZ/2-10,ALIAS_HZ/2+10,ALIAS_HZ/2+20])
        self.assertTrue(np.isnan(y[1]));self.assertTrue(np.isfinite(y[0]));self.assertTrue(np.isfinite(y[2]))


if __name__=='__main__':unittest.main()
