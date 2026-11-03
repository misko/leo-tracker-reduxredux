import unittest

import numpy as np
from estimator import FIT, HELD, TS, WORDS, evaluate, fit, held_error, rotation, select_state


class EstimatorTests(unittest.TestCase):
    def setup_signal(self):
        rng = np.random.default_rng(718)
        bins = np.arange(32)
        mapping = (bins[None, :] - 16 * np.arange(2, 302)[:, None]) % 60
        freq = np.linspace(-4, 4, 32)
        gain = np.exp(1j * rng.uniform(-np.pi, np.pi, 32)) * rng.uniform(0.8, 1.2, 32)
        signal = rotation(np.arange(300) * TS, freq, [137, 23]) * gain
        return mapping, freq, signal

    def test_signed_frequency_and_drift(self):
        _, freq, y = self.setup_signal()
        for sign in [1, -1]:
            z = y if sign == 1 else y.conj()
            p, ok = fit(z, freq, sign * 100)
            self.assertTrue(ok)
            np.testing.assert_allclose(p, sign * np.array([137, 23]), atol=0.01)
            self.assertLess(held_error(z, freq, p), 1e-8)

    def test_state_recovery_and_wrong_prediction(self):
        mapping, freq, y = self.setup_signal()
        data = y * WORDS[37, mapping]
        state, coherence, margin = select_state(data, mapping, 137)
        self.assertEqual(state, 37)
        self.assertGreater(coherence, 0.99)
        self.assertGreater(margin, 0)
        wrong = data * WORDS[38, mapping]
        self.assertGreater(held_error(wrong, freq, [137, 23]), 0.5)

    def test_held_mutation_cannot_change_selection_or_fit(self):
        mapping, freq, y = self.setup_signal()
        pilots = y[:, :8]
        data = y[:, 8:] * WORDS[37, mapping[:, 8:]]
        a = evaluate(pilots, data, mapping[:, 8:], freq[:8], freq[8:])
        pilots2, data2 = pilots.copy(), data.copy()
        pilots2[HELD] *= np.exp(1.9j)
        data2[HELD] *= -3j
        b = evaluate(pilots2, data2, mapping[:, 8:], freq[:8], freq[8:])
        self.assertEqual(a["state"], b["state"])
        self.assertEqual(a["qualified"], b["qualified"])
        for arm in a["arms"]:
            for key in ["frequency_hz", "drift_ppm"]:
                self.assertEqual(a["arms"][arm][key], b["arms"][arm][key])
        self.assertNotEqual(
            a["arms"]["sequence"]["held_sequence_nmse"], b["arms"]["sequence"]["held_sequence_nmse"]
        )

    def test_disjoint_intervals(self):
        self.assertFalse(set(FIT) & set(HELD))

    def test_fixed_and_hybrid_estimation_and_holdout(self):
        from followup import fixed_fit, hybrid_fit

        _, freq, _ = self.setup_signal()
        y = rotation(np.arange(300) * TS, freq, [237, 0])
        self.assertAlmostEqual(fixed_fit(y, freq, 200, FIT), 237, places=3)
        a = hybrid_fit(y[:, :8], y[:, 8:], freq[:8], freq[8:], 200)
        self.assertAlmostEqual(a, 237, places=3)
        y[HELD] *= -2j
        b = hybrid_fit(y[:, :8], y[:, 8:], freq[:8], freq[8:], 200)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
