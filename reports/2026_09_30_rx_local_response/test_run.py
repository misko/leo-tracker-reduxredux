import unittest
from run import calibrate


class CalibrationTests(unittest.TestCase):
    def test_empty_calibration_retains_prior(self):
        self.assertEqual(calibrate([], [.1,.2,.3,.4]),[.1,.2,.3,.4])

    def test_missing_categories_remain_possible(self):
        p=calibrate([0]*20,[.25]*4)
        self.assertEqual(p,[.625,.125,.125,.125])
        self.assertAlmostEqual(sum(p),1)

    def test_invalid_category_rejected(self):
        with self.assertRaises(ValueError): calibrate([4],[.25]*4)
