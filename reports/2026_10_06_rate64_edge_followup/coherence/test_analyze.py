"""Independent analytic checks for report-only waveform/projection helpers."""

import unittest

import numpy as np
from analyze import TG, TS, bias, center, per_tone_projection, physical_frame

from leo.analysis.starlink.templates import (
    qin_edge_pilot_frame,
    qin_edge_pilot_indices,
    qin_edge_pilot_symbols,
)


class AnalyticChecks(unittest.TestCase):
    def test_continuous_mixer_equals_full_carrier_construction(self):
        for fs in (2500000, 10000000):
            for edge in ("lower", "upper"):
                frame = physical_frame(fs, edge)
                codes = qin_edge_pilot_symbols(edge)
                indices = qin_edge_pilot_indices(edge)
                # Independently sum full RF-offset carriers at selected times,
                # including the prefix, and only then apply continuous mixing.
                for i in (round(3.1 * TS * fs), round(25.6 * TS * fs), round(65.3 * TS * fs)):
                    t = i / fs
                    s = int(t // TS)
                    expected = sum(
                        codes[s - 2, k]
                        * np.exp(
                            2j
                            * np.pi
                            * (index if index < 512 else index - 1024)
                            * 234375
                            * (t - s * TS - TG)
                        )
                        for k, index in enumerate(indices)
                    ) / np.sqrt(8)
                    expected *= np.exp(-2j * np.pi * center(edge) * t)
                    self.assertAlmostEqual(abs(frame[i] - expected), 0, places=7)

    def test_frame_phase_identity_and_cfo_bias(self):
        for edge in ("lower", "upper"):
            fs = 10000000
            t = np.arange(round(fs / 750)) / fs
            symbol = np.floor(t / TS).astype(int)
            valid = (symbol >= 2) & (symbol < 302)
            phase = np.exp(-2j * np.pi * center(edge) * (symbol[valid] * TS + TG))
            np.testing.assert_allclose(
                physical_frame(fs, edge)[valid],
                qin_edge_pilot_frame(fs, edge)[valid] * phase,
                atol=2e-7,
            )
            # Exact rational remainders of -492.5 / +491.5 carriers on the
            # 1/4.4us symbol-frequency ring (the edge centers are asymmetric).
            expected = -2187500 / 88 if edge == "lower" else 2812500 / 88
            self.assertAlmostEqual(bias(edge), expected, places=5)

    def test_eight_tone_projection_recovers_known_gain_spread(self):
        fs, edge, epoch = 10000000, "lower", 40
        t = np.arange(round(fs / 750)) / fs
        symbol = np.floor(t / TS).astype(int)
        valid = (symbol >= 2) & (symbol < 302)
        local = t[valid] - symbol[valid] * TS
        indices = qin_edge_pilot_indices(edge)
        f = np.array([i - 1024 for i in indices]) * 234375
        known = np.linspace(0.6, 1.3, 8) * np.exp(1j * np.linspace(-0.2, 0.2, 8))
        codes = qin_edge_pilot_symbols(edge)[symbol[valid] - 2]
        template = np.zeros(len(t), complex)
        template[valid] = np.sum(
            codes
            * known
            * np.exp(2j * np.pi * ((local[:, None] - TG) * f - center(edge) * t[valid, None])),
            axis=1,
        ) / np.sqrt(8)
        iq = np.zeros(fs // 50, complex)
        for frame in range(14):
            start = epoch + round(frame * fs / 750)
            iq[start : start + len(template)] += template
        # Last incomplete/no-signal frame can be excluded by using finite
        # length corresponding exactly to the 14 signal frames.
        iq = iq[: epoch + round(13 * fs / 750) + round(66 * TS * fs) + 9]
        result = per_tone_projection(iq, fs, edge, epoch, 0, 0)
        np.testing.assert_allclose(result["tone_coherence_median"], 1, atol=1e-9)
        self.assertAlmostEqual(result["amplitude_spread_db"], 20 * np.log10(1.3 / 0.6), places=7)


if __name__ == "__main__":
    unittest.main()
