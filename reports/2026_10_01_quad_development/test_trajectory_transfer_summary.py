import unittest
from summarize_trajectory_transfer import aggregate

class CoverageTests(unittest.TestCase):
    def test_failed_controls_keep_planned_denominator(self):
        rows=[dict(held_points=10,policy_vs_robust=20.,mixture_selected=True,selected_gain=30.,double_penalty_gain=10.),
              dict(held_points=30,policy_vs_robust=None,mixture_selected=False,selected_gain=0.,double_penalty_gain=0.)]
        result=aggregate(rows)
        self.assertEqual(result['held_points'],40);self.assertEqual(result['valid_robust_points'],10)
        self.assertEqual(result['failed_robust_folds'],1);self.assertEqual(result['gain_vs_robust'],2.)
        self.assertEqual(result['gain_vs_gaussian'],.75)
    def test_empty_selected_subset(self):
        r=aggregate([dict(held_points=3,policy_vs_robust=0.,mixture_selected=False,selected_gain=0.,double_penalty_gain=0.)])
        self.assertIsNone(r['selected_gain_vs_robust'])

if __name__=='__main__':unittest.main()
