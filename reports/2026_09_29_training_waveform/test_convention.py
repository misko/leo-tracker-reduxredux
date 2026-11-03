import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "reports/2026_09_27_ds7_header")]
from convention import remove_upconversion_phase  # noqa: E402
from estimator import errors, fit  # noqa: E402
from tcodes import demodulate, geometry, references  # noqa: E402

from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402


class ConventionTests(unittest.TestCase):
    def test_raw_waveform_signed_frequency_both_edges(self):
        for edge in ("upper", "lower"):
            for injected in (-137, 137):
                with self.subTest(edge=edge, injected=injected):
                    fs = 12e6
                    raw = np.pad(qin_edge_pilot_frame(fs, edge), (1200, 1200))
                    raw = raw * np.exp(2j * np.pi * injected * np.arange(len(raw)) / fs)
                    _, pb, center = geometry(edge)
                    _, _, pilot = references(edge)
                    y = demodulate(raw, fs, 1200, 0, center)[1:, pb] / pilot
                    z = remove_upconversion_phase(y, center)[None]
                    frequency = fit(z, np.arange(20, 220))
                    self.assertAlmostEqual(frequency, injected, delta=0.1)
                    self.assertLess(float(errors(z, frequency)[0]), 1e-4)


if __name__ == "__main__":
    unittest.main()
