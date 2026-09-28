"""Synthetic checks for restricted-band demodulation and header discrimination."""

import unittest

import numpy as np
from analyze import PILOT_CENTER, demodulate, score
from scipy.signal import resample_poly


class NarrowbandTests(unittest.TestCase):
    def test_filtered_ofdm_header_and_payload(self):
        rng = np.random.default_rng(942)
        template = np.exp(0.5j * np.pi * rng.integers(0, 4, (1024, 301)))
        sss = np.exp(0.5j * np.pi * rng.integers(0, 4, 1024))
        symbols = np.exp(0.5j * np.pi * rng.integers(0, 4, (302, 1024)))
        symbols[1] = sss
        symbols[2:10] = template[:, 1:9].T * rng.choice([-1, 1], (8, 1024))
        td = np.fft.ifft(symbols, axis=1)
        stream = np.r_[np.zeros(2400), np.c_[td[:, -32:], td].ravel(), np.zeros(2400)]
        cfo = 83000
        stream *= np.exp(2j * np.pi * (cfo - PILOT_CENTER) * np.arange(len(stream)) / 240e6)
        x = resample_poly(stream, 1, 24)
        sy = demodulate(x, 1e7, 100, cfo)
        exact, controls = score(sy, sss, template, np.r_[476:488, 496:508])
        self.assertGreater(exact[:8].mean(), 0.95)
        self.assertLess(exact[20:].mean(), 0.3)
        self.assertLess(controls[:, :8].mean(axis=1).max(), 0.5)

    def test_noise_does_not_pass(self):
        rng = np.random.default_rng(81)
        sy = rng.normal(size=(301, 1024)) + 1j * rng.normal(size=(301, 1024))
        tr = np.exp(0.5j * np.pi * rng.integers(0, 4, (1024, 301)))
        exact, control = score(sy, np.ones(1024), tr, np.r_[476:488, 496:508])
        self.assertLess(exact[:8].mean(), 0.4)
        self.assertLess(abs(exact.mean() - control.mean()), 0.05)


if __name__ == "__main__":
    unittest.main()
