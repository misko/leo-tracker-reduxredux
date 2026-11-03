import unittest
from resume_position_convergence import best_record


class BestRecordTests(unittest.TestCase):
    def test_dont_hide_better_unconverged_result(self):
        low=dict(objective=10.,success=False,fixed_location=False)
        high=dict(objective=11.,success=True,fixed_location=False)
        self.assertIs(best_record([low,high]),low)

    def test_stationary_roundoff_tie(self):
        low=dict(objective=10.,success=False,fixed_location=False)
        close=dict(objective=10.+1e-8,success=True,fixed_location=False)
        self.assertIs(best_record([low,close]),close)

    def test_equal_fixed_nuisance_fit_does_not_mask_joint_audit(self):
        fixed=dict(objective=10.,success=True,fixed_location=True)
        joint=dict(objective=10.,success=False,fixed_location=False)
        self.assertIs(best_record([fixed,joint]),joint)


if __name__=='__main__':unittest.main()
