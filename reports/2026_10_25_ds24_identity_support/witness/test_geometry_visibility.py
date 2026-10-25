import unittest
import numpy as np
import geometry_support_snapshot as g


class VisibilityContractTests(unittest.TestCase):
    def bank(self,z):
        return dict(time_s=np.array([-30.,30.]),position_km=np.array([[[0.,0.,z],[0.,0.,z]]]))

    def test_constant_below_horizon_has_certified_empty_support(self):
        r=g.support(self.bank(0.),[0.],[0.,0.,1.],[0.,0.,1.])
        self.assertTrue(r['certified']);self.assertEqual(r['inner_visible_intervals'],[]);self.assertEqual(r['root_brackets'],[])

    def test_constant_above_horizon_preserves_full_domain(self):
        r=g.support(self.bank(2.),[0.],[0.,0.,1.],[0.,0.,1.])
        self.assertTrue(r['certified']);self.assertEqual(r['inner_visible_intervals'],[[-15.,15.]])

    def test_original_bank_is_never_extrapolated(self):
        with self.assertRaises(ValueError):g.support(self.bank(0.),[20.],[0.,0.,1.],[0.,0.,1.])


if __name__=='__main__':unittest.main()
