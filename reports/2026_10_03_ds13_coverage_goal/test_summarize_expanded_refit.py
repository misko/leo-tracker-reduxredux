import unittest
from summarize_expanded_refit import aggregate


class RefitSummaryTests(unittest.TestCase):
    def test_keeps_losses_and_nonconverged_folds(self):
        rows=[dict(arm='fitted-c',converged=True,change_after_refit=10.,gain_vs_clutter=20.),
              dict(arm='fitted-c',converged=False,change_after_refit=-12.,gain_vs_clutter=-3.)]
        a=aggregate(rows)['fitted-c']
        self.assertEqual(a['folds'],2);self.assertEqual(a['converged'],1)
        self.assertEqual(a['improved_folds'],1);self.assertEqual(a['change_after_refit'],-2.)
        self.assertEqual(a['gain_vs_clutter'],17.)


if __name__=='__main__':unittest.main()
