import unittest
from polish_position_summary import best_record


class PositionPolishTests(unittest.TestCase):
    def test_last_bit_tie_prefers_joint_stationarity(self):
        fixed=dict(objective=2.,success=True,fixed_location=True)
        joint=dict(objective=2.+1e-9,success=True,fixed_location=False)
        self.assertIs(best_record([fixed,joint]),joint)

    def test_meaningfully_better_unconverged_score_remains_visible(self):
        lower=dict(objective=1.,success=False,fixed_location=False)
        stationary=dict(objective=2.,success=True,fixed_location=False)
        self.assertIs(best_record([lower,stationary]),lower)
