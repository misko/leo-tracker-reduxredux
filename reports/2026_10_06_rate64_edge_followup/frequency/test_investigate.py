"""Component-owned independent frequency-coordinate invariants; no RF required."""

import os
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, os.environ.get("LEO_AUDIT_SOURCE", "/opt/leo-adaptive-memory/9181d637d/src"))
sys.path.insert(0, str(Path(__file__).parent))
import investigate as audit


class FrequencyCoordinateTests(unittest.TestCase):
    def test_physical_carriers_have_symbol_phase_missing_from_legacy_template(self):
        from leo.analysis.starlink.templates import qin_edge_pilot_frame

        for fs in (2500000, 10000000):
            for edge in ("lower", "upper"):
                physical = audit.physical_frame(fs, edge)
                legacy = qin_edge_pilot_frame(fs, edge)
                t = np.arange(physical.size) / fs
                symbols = np.floor(t / audit.TS)
                predicted = legacy * np.exp(
                    -2j * np.pi * audit.center(edge) * (symbols * audit.TS + audit.TG)
                )
                np.testing.assert_allclose(physical, predicted, atol=2e-7, rtol=2e-7)

    def test_tuning_then_bias_then_wrap_is_independent_of_capture_center(self):
        from leo.analysis.starlink.pilot_search_geometry import canonicalize_pilot_cfo
        from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz

        for channel in (1, 4, 8):
            for edge in ("lower", "upper"):
                for nominal in (-312500, 0, 312500):
                    tuned = (
                        starlink_edge_rf_center_frequency_hz(channel, edge) - 9750000000 - nominal
                    )
                    for truth in (-400000, -112636.363636, 0, 112636.363636, 400000):
                        raw = nominal + truth + audit.bias(edge)
                        coordinate = canonicalize_pilot_cfo(
                            raw,
                            starlink_channel=channel,
                            edge=edge,
                            tuned_center_frequency_hz=tuned,
                        )
                        actual = audit.wrap(coordinate.canonical_residual_cfo_hz - audit.bias(edge))
                        self.assertAlmostEqual(float(actual), float(audit.wrap(truth)), places=7)

    def test_alias_lifts_must_change_when_correction_moves_seam(self):
        examples = audit.alias_examples()
        self.assertTrue(
            any(
                abs(r["naive_subtract_hz"] - r["physical_wrapped_hz"]) > audit.PERIOD - 1
                for r in examples
            )
        )
        self.assertTrue(any(r["physical_lift"] != r["detector_lift"] for r in examples))
        for row in examples:
            self.assertAlmostEqual(row["reconstructed_hz"], row["truth_hz"], places=7)
        self.assertAlmostEqual(
            float(audit.wrap(400000)), float(audit.wrap(400000 - audit.PERIOD)), places=7
        )

    def test_recession_has_negative_doppler_and_edge_difference_scales_with_rf(self):
        rows = audit.doppler_rows()
        for row in rows:
            velocity = row["illustrative_range_rate_m_s"]
            self.assertAlmostEqual(
                row["upper_minus_lower_hz"], -230625000 * velocity / audit.LIGHT, places=7
            )
            if velocity > 0:
                self.assertLess(row["upper_doppler_hz"], row["lower_doppler_hz"])

    def test_dilation_is_tone_dependent_and_grows_with_duration(self):
        rows = audit.dilation_rows()
        zero = [r for r in rows if r["scale_ppm"] == 0]
        self.assertTrue(all(r["fixed_cfo_combined_coherence"] == 1 for r in zero))
        for ppm in (1, 10, 25, 100):
            short, long = [r for r in rows if r["scale_ppm"] == ppm]
            self.assertGreater(
                short["fixed_cfo_combined_coherence"], long["fixed_cfo_combined_coherence"]
            )
            self.assertLess(long["fixed_cfo_combined_coherence"], long["time_scaled_coherence"])
        # First-order physical Doppler at illustrative 7 km/s is modest over
        # GLRT's actual 64-symbol support, not a 300-symbol integration claim.
        illustrative = [r for r in rows if 23 < r["scale_ppm"] < 24 and r["symbols"] == 64][0]
        self.assertLess(1 - illustrative["fixed_cfo_combined_coherence"], 0.00005)

    def test_known_scale_correction_of_symbols_and_frame_folding(self):
        rows = audit.repeated_waveform_stress()
        self.assertEqual(len(rows), 12)
        for row in rows:
            if row["illustrative_range_rate_m_s"] == 0:
                self.assertAlmostEqual(
                    row["fixed_frame_exact_score"], row["known_scale_exact_score"], places=12
                )
            else:
                self.assertGreater(row["known_scale_exact_score"], row["fixed_frame_exact_score"])
                self.assertAlmostEqual(
                    row["accumulated_timing_drift_samples"],
                    row["accumulated_timing_drift_ns"] * row["rate_hz"] / 1e9,
                    places=10,
                )


if __name__ == "__main__":
    unittest.main()
