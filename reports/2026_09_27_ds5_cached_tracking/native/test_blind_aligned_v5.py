import ctypes as ct
import unittest

import numpy as np

from blind_aligned_v5 import NativeAlignedBlindV5, build_library_v5
from blind_strided_v4 import NativeStridedBlindV4, build_library_v4


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


class BlindAlignedV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v4_library = build_library_v4()
        cls.v5_library = build_library_v5()

    def test_both_rates_receivers_modes_and_extrema_match_v4(self):
        for rate in (2_500_000, 5_000_000):
            count = rate * 120 // 1000
            raw = np.empty((count, 2, 2), dtype=np.int16)
            flat = raw.reshape(-1)
            extrema = np.array([-32768, 32767, 32767, -32768], dtype=np.int16)
            flat[:] = np.resize(extrema, len(flat))
            before = raw.copy()
            for receiver in (0, 1):
                for seeded in (False, True):
                    with NativeStridedBlindV4(
                        rate, "lower", self.v4_library, bins=512
                    ) as baseline, NativeAlignedBlindV5(
                        rate, "lower", self.v5_library, bins=512
                    ) as candidate:
                        expected = baseline.run(
                            raw[:, receiver, :], maximum=6, seeded=seeded
                        )
                        actual = candidate.run(
                            raw, receiver, maximum=6, seeded=seeded
                        )
                        self.assertEqual(scientific(actual), scientific(expected))
                        self.assertEqual(
                            scientific(candidate.screens()),
                            scientific(baseline.screens()),
                        )
            np.testing.assert_array_equal(raw, before)

    def test_multires_seeded_path_matches_v4(self):
        rate = 2_500_000
        rng = np.random.default_rng(5)
        raw = rng.integers(
            -32768, 32768, size=(rate * 120 // 1000, 2, 2), dtype=np.int16
        )
        with NativeStridedBlindV4(
            rate, "upper", self.v4_library, bins=512, timing_bins=1024
        ) as baseline, NativeAlignedBlindV5(
            rate, "upper", self.v5_library, bins=512, timing_bins=1024
        ) as candidate:
            self.assertEqual(
                scientific(candidate.run(raw, 1, maximum=2, seeded=True)),
                scientific(baseline.run(raw[:, 1, :], maximum=2, seeded=True)),
            )

    def test_layout_and_receiver_bounds(self):
        rate = 2_500_000
        raw = np.zeros((rate * 120 // 1000, 2, 2), dtype=np.int16)
        with NativeAlignedBlindV5(rate, "lower", self.v5_library) as candidate:
            for receiver in (-1, 2):
                with self.assertRaises(ValueError):
                    candidate.run(raw, receiver, maximum=1, seeded=False)
            with self.assertRaises(ValueError):
                candidate.run(raw[:, ::-1, :], 0, maximum=1, seeded=False)
            with self.assertRaises(ValueError):
                candidate.run(raw[:, 0, :], 0, maximum=1, seeded=False)


if __name__ == "__main__":
    unittest.main()
