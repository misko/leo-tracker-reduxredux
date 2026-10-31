import unittest
from types import SimpleNamespace
import numpy as np
from run_inclusion import check_domains,qualified_points,select_route


class InclusionSafetyTests(unittest.TestCase):
    def test_routes_follow_actual_family_evidence(self):
        self.assertEqual(select_route(True,False),'shared')
        self.assertEqual(select_route(False,False),'new_family')
        with self.assertRaisesRegex(ValueError,'separate shared conditioning'):
            select_route(False,True)

    def test_numerical_reference_cannot_extrapolate(self):
        p=SimpleNamespace(sky={'time_s':np.array([-20.,40.])},flat_times=np.array([0.,10.]),flat_labels=np.array([0,0]))
        self.assertTrue(check_domains(p,np.array([-15.2]),[])['curved']['in_domain'])
        with self.assertRaisesRegex(ValueError,'extrapolation prohibited'):
            check_domains(p,np.array([-20.]),[])

    def test_proposals_require_control_addition_and_exact_owner_checks(self):
        self.assertEqual(qualified_points(True,True,True,30),30)
        for gates in ((False,True,True),(True,False,True),(True,True,False)):
            self.assertEqual(qualified_points(*gates,30),0)


if __name__=='__main__':unittest.main()
