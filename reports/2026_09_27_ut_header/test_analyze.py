"""Synthetic checks of recovery and controls; independent of the private IQ file."""

import unittest

import numpy as np
from analyze import FS, acquire, bpsk_score, remove_blind_slope


class RecoveryTests(unittest.TestCase):
    def test_recovers_offset_and_frequency_in_noise(self):
        rng = np.random.default_rng(117)
        replica = np.exp(0.5j * np.pi * rng.integers(0, 4, 2048))
        x = 0.03 * (rng.normal(size=3200) + 1j * rng.normal(size=3200))
        x[531 : 531 + len(replica)] += replica
        x *= np.exp(2j * np.pi * 173456 * np.arange(len(x)) / FS)
        k, cfo, rho = acquire(x, replica)
        self.assertEqual(k, 531)
        self.assertLess(abs(cfo - 173456), 200)
        self.assertGreater(rho, 0.995)

    def test_blind_timing_fit_without_reference(self):
        rng = np.random.default_rng(812)
        f = np.fft.fftfreq(1024)
        q = np.exp(0.5j * np.pi * rng.integers(0, 4, 1024))
        y = q * np.exp(2j * np.pi * f * 0.37 + 0.23j)
        corrected, delay, score = remove_blind_slope(y, f)
        self.assertAlmostEqual(delay, 0.37, places=4)
        self.assertGreater(score, 0.99999)
        self.assertLess(np.std(np.angle(corrected / q)), 1e-4)

    def test_bpsk_template_positive_and_wrong_template(self):
        rng = np.random.default_rng(77)
        tr = np.exp(0.5j * np.pi * rng.integers(0, 4, 1024))
        y = tr * rng.choice([-1, 1], 1024) * np.exp(0.31j)
        y += 0.08 * (rng.normal(size=1024) + 1j * rng.normal(size=1024))
        self.assertGreater(bpsk_score(y, tr), 0.97)
        self.assertLess(bpsk_score(y, np.roll(tr, 19)), 0.12)

    def test_noise_is_not_bpsk_template_evidence(self):
        rng = np.random.default_rng(78)
        tr = np.exp(0.5j * np.pi * rng.integers(0, 4, 1024))
        noise = rng.normal(size=1024) + 1j * rng.normal(size=1024)
        self.assertLess(bpsk_score(noise, tr), 0.12)


if __name__ == "__main__":
    unittest.main()
