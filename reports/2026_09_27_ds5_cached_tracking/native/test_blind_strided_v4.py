import ctypes as ct
import unittest

import numpy as np

from blind_strided_v4 import NativeStridedBlindV4, build_library_v4
from known_state_v3 import build_library_v3
from tools.presence_dwell import NativeDwell, unpack


RATE = 2_500_000


def scientific(value):
    if isinstance(value, ct.Structure):
        return {
            name: scientific(getattr(value, name))
            for name, _ in value._fields_
            if "cpu_ms" not in name and "wall_ms" not in name
        }
    if isinstance(value, ct.Array):
        return [scientific(item) for item in value]
    return value


class BlindStridedV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(20260927)
        cls.raw = rng.integers(
            -32768, 32768, size=(RATE * 120 // 1000, 2, 2), dtype=np.int16
        )
        cls.before = cls.raw.copy()
        cls.v3_library = build_library_v3()
        cls.v4_library = build_library_v4()

    def compare(self, rx, *, seeded, timing_bins=None):
        view = self.raw[:, rx, :]
        packed = np.ascontiguousarray(view)
        with NativeDwell(
            self.v3_library, RATE, "lower", 512, timing_bins=timing_bins
        ) as baseline, NativeStridedBlindV4(
            RATE, "lower", self.v4_library, bins=512, timing_bins=timing_bins
        ) as candidate:
            expected = baseline.run(packed, maximum=1, seeded=seeded)
            actual = candidate.run(view, maximum=1, seeded=seeded)
            self.assertEqual(scientific(actual), scientific(expected))
            self.assertEqual(
                scientific(candidate.screens()), scientific(baseline.screens())
            )

    def test_natural_receiver_views_match_blind_baseline_exactly(self):
        self.compare(0, seeded=False)
        self.compare(1, seeded=False)

    def test_multires_seeded_path_matches_baseline_exactly(self):
        self.compare(1, seeded=True, timing_bins=1024)

    def test_contiguous_path_matches_baseline_exactly(self):
        packed = np.ascontiguousarray(self.raw[:, 0, :])
        with NativeDwell(self.v3_library, RATE, "upper", 512) as baseline, \
                NativeStridedBlindV4(
                    RATE, "upper", self.v4_library, bins=512
                ) as candidate:
            self.assertEqual(
                scientific(candidate.run(packed, maximum=1, seeded=False)),
                scientific(baseline.run(packed, maximum=1, seeded=False)),
            )

    def test_input_is_preserved_and_bad_views_are_rejected(self):
        with NativeStridedBlindV4(RATE, "lower", self.v4_library) as candidate:
            candidate.run(self.raw[:, 0, :], maximum=1, seeded=False)
            with self.assertRaises(ValueError):
                candidate.run(self.raw[::2, 0, :], maximum=1, seeded=False)
            with self.assertRaises(ValueError):
                candidate.run(self.raw[:, :, 0], maximum=1, seeded=False)
        np.testing.assert_array_equal(self.raw, self.before)

    def test_all_confirmations_both_rates_receivers_and_modes_are_exact(self):
        for rate in (2_500_000, 5_000_000):
            count = rate * 120 // 1000
            # Exercise CI16 extrema and alternating receiver lanes. Integer
            # lag products require the same widened arithmetic as production.
            raw = np.empty((count, 2, 2), dtype=np.int16)
            pattern = np.array([-32768, 32767, 32767, -32768], dtype=np.int16)
            flat = raw.reshape(-1)
            flat[:] = np.resize(pattern, len(flat))
            before = raw.copy()
            for rx in (0, 1):
                view = raw[:, rx, :]
                packed = np.ascontiguousarray(view)
                for seeded in (False, True):
                    with NativeDwell(
                        self.v3_library, rate, "lower", 512
                    ) as baseline, NativeStridedBlindV4(
                        rate, "lower", self.v4_library, bins=512
                    ) as candidate:
                        expected = baseline.run(packed, maximum=6, seeded=seeded)
                        actual = candidate.run(view, maximum=6, seeded=seeded)
                        self.assertEqual(scientific(actual), scientific(expected))
                        self.assertEqual(
                            scientific(candidate.screens()),
                            scientific(baseline.screens()),
                        )
            np.testing.assert_array_equal(raw, before)


if __name__ == "__main__":
    unittest.main()
