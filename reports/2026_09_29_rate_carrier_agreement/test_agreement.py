import unittest
from run import agreement


def result(rate,qualified=True):
    return dict(rate_hz_s=rate,qualified=qualified)


class AgreementTests(unittest.TestCase):
    def test_sign_scale_and_limits(self):
        self.assertEqual(agreement(result(2),result(2)),1)
        self.assertEqual(agreement(result(-2),result(-2)),1)
        self.assertEqual(agreement(result(-2),result(2)),0)
        self.assertEqual(agreement(result(0),result(0)),0)
        self.assertAlmostEqual(agreement(result(2),result(4)),.8)
        self.assertAlmostEqual(agreement(result(2e200),result(4e200)),.8)

    def test_failed_fit_fallback_and_nonfinite(self):
        self.assertEqual(agreement(result(2,False),result(2)),0)
        with self.assertRaises(ValueError):
            agreement(result(float('nan')),result(2))
