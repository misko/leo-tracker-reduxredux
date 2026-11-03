import unittest

import numpy as np
from tracking import TS, peaks, select


class PeakTests(unittest.TestCase):
    def test_signed_recovery_and_held_isolation(self):
        for f in [173, -67123, 113620]:
            y = (
                np.exp(2j * np.pi * f * np.arange(300) * TS)[:, None]
                * np.exp(1j * np.arange(8))[None, :]
            )
            a = peaks(y)
            delta = (a[0]["frequency_hz"] - f + 0.5 / TS) % (1 / TS) - 0.5 / TS
            self.assertLess(abs(delta), 0.02)
            y[220:] *= -3j
            self.assertEqual(a, peaks(y))

    def test_transient_and_real_jump(self):
        a = [dict(frequency_hz=50000, score=0.71), dict(frequency_hz=100, score=0.70)]
        self.assertEqual(select(a, 90)[0]["frequency_hz"], 100)
        a[0]["score"] = 0.95
        self.assertEqual(select(a, 90)[0]["frequency_hz"], 50000)

    def test_low_evidence_reset(self):
        c = [dict(frequency_hz=50000, score=0.1)]
        self.assertIsNone(select(c, 100)[1])
        self.assertEqual(select([dict(frequency_hz=-30000, score=0.8)], None)[1], -30000)


if __name__ == "__main__":
    unittest.main()
