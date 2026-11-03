import copy
import unittest
from position_evidence import joint_stationary_at_best,eligible


class PositionEvidenceTests(unittest.TestCase):
    def fixture(self):
        best=dict(success=True,fixed_location=True,objective=2.,point_km=[.1,.2])
        joint=dict(success=True,fixed_location=False,objective=2.+1e-9,point_km=[.1,.2])
        return dict(best_found=best,records=[best,joint],boundary=False)

    def test_last_bit_fixed_profile_tie_does_not_invalidate_joint_fit(self):
        self.assertTrue(joint_stationary_at_best(self.fixture()))
        self.assertTrue(eligible(self.fixture(),{}))

    def test_other_location_score_boundary_or_calibration_not_certified(self):
        for changes in ({'point_km':[.11,.2]},{'objective':2.001},{'success':False}):
            case=self.fixture();case['records'][1].update(changes)
            self.assertFalse(joint_stationary_at_best(case))
        case=self.fixture();case['boundary']=True
        self.assertFalse(eligible(case,{}))
        self.assertFalse(eligible(self.fixture(),{'calibration_warnings':['failure']}))
