import unittest
from summarize_training_calibration import aggregate


class CalibrationSummaryTests(unittest.TestCase):
    def fixture(self):
        return [dict(fold=i,test_rows=10,test_groups=5,arms={name:dict(heldout_log_likelihood=value,
            heldout_gain_vs_clutter=value+10,attempts=[dict(success=(i!=2))])
            for name,value in [('fitted-c',-1),('zero-c',-2)]}) for i in range(5)]

    def test_counts_and_failure_visible(self):
        r=aggregate(self.fixture());self.assertEqual(r['test_rows'],50)
        self.assertEqual(r['fitted_c_gain_over_zero_c'],5)
        self.assertEqual(r['arms']['fitted-c']['converged_folds'],4)

    def test_duplicate_fold_rejected(self):
        r=self.fixture();r[4]['fold']=0
        with self.assertRaises(ValueError):aggregate(r)


if __name__=='__main__':unittest.main()
