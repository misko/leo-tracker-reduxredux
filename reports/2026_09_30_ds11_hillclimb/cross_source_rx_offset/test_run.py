import unittest
from run import PERIOD, donor_prediction, medoid, wrap


class OffsetTests(unittest.TestCase):
    def test_circular_medoid(self):
        self.assertAlmostEqual(wrap(PERIOD + 20), 20)
        self.assertLess(abs(wrap(medoid([PERIOD/2-10, -PERIOD/2+10, PERIOD/2-20])-PERIOD/2)), 21)

    def test_donor_identity_and_support(self):
        target = dict(scan_index=0, rf_hz=1, norad=1, visits=list(range(6)), offset_hz=900)
        donors = [dict(target, norad=k, offset_hz=100*k) for k in (2, 3, 4)]
        centers, prediction = donor_prediction(target, donors+[target]*10)
        self.assertEqual(len(centers), 3)
        self.assertAlmostEqual(prediction, 300)
        self.assertEqual(donor_prediction(dict(target, offset_hz=-700), donors)[1], prediction)
        self.assertIsNone(donor_prediction(target, donors[:2])[1])
        self.assertIsNone(donor_prediction(dict(target, visits=[0, 1]), donors)[1])


if __name__ == '__main__':
    unittest.main()
