import unittest
from types import SimpleNamespace
import numpy as np
from polish_owner_mixture import active_noise_bounds


class ActiveNoiseTests(unittest.TestCase):
    def test_only_outward_active_bounds_are_held(self):
        obj=SimpleNamespace(bounds=[(-5.,5.),(-2.,2.)],evaluate=lambda v:(0.,np.array([-1.,1.])))
        original,active=active_noise_bounds(obj,[5.,-2.])
        self.assertEqual(active,[(5.,5.),(-2.,-2.)]);self.assertEqual(original,obj.bounds)
        _,active=active_noise_bounds(obj,[0.,0.])
        self.assertEqual(active,original)
        obj.evaluate=lambda v:(0.,np.array([1.,-1.]))
        self.assertEqual(active_noise_bounds(obj,[5.,-2.])[1],original)


if __name__=='__main__':unittest.main()
