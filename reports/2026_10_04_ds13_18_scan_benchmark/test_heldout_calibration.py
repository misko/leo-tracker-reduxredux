import copy
import unittest
from render_heldout_calibration import summarize


class HeldoutCalibrationTests(unittest.TestCase):
    def fixture(self):
        return [dict(fold=i,test_original_rows=[2*i,2*i+1],converged=i!=0,arms={'fitted-c':dict(
            heldout_windows=2,heldout_inside600=1,heldout_nearest_rms_inside600_hz=100,
            success=i!=0)}) for i in range(5)]

    def test_coverage_and_rms_keep_denominators_separate(self):
        result=summarize(self.fixture(),'fitted-c')
        self.assertEqual(result['heldout_windows'],10)
        self.assertEqual(result['coverage600'],.5)
        self.assertEqual(result['gated_nearest_rms_hz'],100)
        self.assertEqual(result['postfit_converged_folds'],4)

    def test_overlap_and_incomplete_rejected(self):
        folds=self.fixture()
        with self.assertRaisesRegex(ValueError,'five distinct'):summarize(folds[:4],'fitted-c')
        folds[1]['test_original_rows']=[0,3]
        with self.assertRaisesRegex(ValueError,'overlap'):summarize(folds,'fitted-c')

    def test_no_support_is_missing_rms_not_zero(self):
        folds=self.fixture()
        for f in folds:f['arms']['fitted-c'].update(heldout_inside600=0,heldout_nearest_rms_inside600_hz=None)
        result=summarize(folds,'fitted-c')
        self.assertEqual(result['coverage600'],0)
        self.assertIsNone(result['gated_nearest_rms_hz'])
