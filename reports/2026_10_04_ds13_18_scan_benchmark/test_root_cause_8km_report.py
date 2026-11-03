import copy
import unittest
from render_root_cause_8km import reconcile_best


class MinimumEvidenceTests(unittest.TestCase):
    def test_lower_final_roof_does_not_become_false_joint_minimum(self):
        best=dict(objective=100.,point_km=[3.,0.],success=True,fixed_location=False)
        roof=dict(objective=90.,point_km=[0.,0.],success=True,fixed_location=True)
        arm=dict(best=best,roof=roof,records=[best,roof],best_minus_original_2km_nll=-5.)
        source=dict(arms={'fitted-c':copy.deepcopy(arm),'zero-c':copy.deepcopy(arm)})
        result=reconcile_best(source)
        for r in result['arms'].values():
            self.assertEqual(r['radius_m'],0.)
            self.assertFalse(r['best_is_joint_stationary'])
            self.assertTrue(r['reconciled_lower_fixed_site'])
            self.assertEqual(r['best_minus_original_2km_nll'],-15.)
        self.assertEqual(source['arms']['fitted-c']['best']['objective'],100.)
