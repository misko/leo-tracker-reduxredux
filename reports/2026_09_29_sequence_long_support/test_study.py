import unittest

import numpy as np
from study import HELD, TS, WORDS, estimate


class LongSupportTests(unittest.TestCase):
    def signal(self):
        mapping = (np.arange(24)[None, :] - 16 * np.arange(2, 302)[:, None]) % 60
        wave = np.exp(2j * np.pi * 173 * np.arange(300) * TS)[:, None]
        rng = np.random.default_rng(313)
        g = np.exp(1j * rng.normal(size=24))
        pilots = wave * np.ones((1, 8))
        data = wave * g * WORDS[23, mapping]
        return pilots, data, mapping

    def test_recovery_and_wrong_control(self):
        p, d, m = self.signal()
        r = estimate(p, d, m)
        self.assertEqual(r["state"], 23)
        self.assertTrue(r["qualified"])
        self.assertEqual(r["first_symbol"], 42)
        self.assertAlmostEqual(r["arms"]["hybrid"]["frequency_hz"], 173, places=3)
        self.assertLess(r["arms"]["hybrid"]["held_pilot_nmse"], 1e-8)

    def test_held_changes_do_not_select_or_fit(self):
        p, d, m = self.signal()
        a = estimate(p, d, m)
        p[HELD] *= -2j
        d[HELD] *= 3j
        b = estimate(p, d, m)
        for key in ["state", "first_symbol", "qualified", "candidates"]:
            self.assertEqual(a[key], b[key])
        for arm in a["arms"]:
            self.assertEqual(a["arms"][arm]["frequency_hz"], b["arms"][arm]["frequency_hz"])
        self.assertNotEqual(
            a["arms"]["hybrid"]["held_pilot_nmse"], b["arms"]["hybrid"]["held_pilot_nmse"]
        )

    def test_unstructured_data_falls_back(self):
        p, d, m = self.signal()
        rng = np.random.default_rng(12)
        d = rng.normal(size=d.shape) + 1j * rng.normal(size=d.shape)
        r = estimate(p, d, m)
        self.assertFalse(r["qualified"])
        self.assertEqual(r["arms"]["gated"], r["arms"]["pilot"])


if __name__ == "__main__":
    unittest.main()
