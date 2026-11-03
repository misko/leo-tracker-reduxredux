import unittest

import numpy as np
from block import TS, block_fit, compare


class BlockTests(unittest.TestCase):
    def signal(self):
        rng = np.random.default_rng(744)
        gains = np.exp(1j * rng.uniform(-np.pi, np.pi, (10, 1, 8)))
        return gains * np.exp(2j * np.pi * (-173) * np.arange(300) * TS)[None, :, None]

    def test_independent_frame_phase_and_frequency(self):
        self.assertAlmostEqual(block_fit(self.signal()), -173, places=3)

    def test_holdout_cannot_change_frequency(self):
        y = self.signal()
        flags = np.arange(10) % 2 == 0
        a = compare(y, flags)
        y[:, 220:] *= -3j
        b = compare(y, flags)
        for key in ["all_frequency_hz", "support_frequency_hz"]:
            self.assertEqual(a[key], b[key])
        self.assertNotEqual(a["rows"][0]["all_nmse"], b["rows"][0]["all_nmse"])

    def test_no_support_keeps_all_rows_as_missing(self):
        r = compare(self.signal(), np.zeros(10, dtype=bool))
        self.assertIsNone(r["support_frequency_hz"])
        self.assertEqual(len(r["rows"]), 10)
        self.assertTrue(
            all(x["abstention_nmse"] == 1 and x["support_fit_nmse"] == 1 for x in r["rows"])
        )

    def test_all_support_exact_equivalence(self):
        r = compare(self.signal(), np.ones(10, dtype=bool))
        self.assertEqual(r["all_frequency_hz"], r["support_frequency_hz"])
        self.assertTrue(all(x["all_nmse"] == x["abstention_nmse"] for x in r["rows"]))


if __name__ == "__main__":
    unittest.main()
