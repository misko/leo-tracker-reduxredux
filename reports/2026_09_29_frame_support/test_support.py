import unittest

import numpy as np
from support import decision, threshold


class SupportTests(unittest.TestCase):
    def test_envelope_boundary_and_abstention_accounting(self):
        a = np.linspace(0.01, 0.03, 90).reshape(30, 3)
        q = threshold(a)
        self.assertEqual(q, 0.03)
        r = decision(q, 100, 1.02, q)
        self.assertFalse(r["accepted"])
        self.assertIsNone(r["frequency_hz"])
        self.assertEqual(r["nmse"], 1)
        self.assertTrue(decision(q + 0.001, 100, 0.7, q)["accepted"])

    def test_evaluation_error_does_not_choose_support(self):
        a = decision(0.2, 100, 0.5, 0.03)
        b = decision(0.2, 100, 2, 0.03)
        self.assertEqual(a["accepted"], b["accepted"])
        self.assertEqual(a["frequency_hz"], b["frequency_hz"])
        self.assertNotEqual(a["nmse"], b["nmse"])

    def test_invalid_calibration_rejected(self):
        for a in [np.zeros((29, 3)), np.full((30, 3), np.nan)]:
            with self.assertRaises(ValueError):
                threshold(a)


if __name__ == "__main__":
    unittest.main()
