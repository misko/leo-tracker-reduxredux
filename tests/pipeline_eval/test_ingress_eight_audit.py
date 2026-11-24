import unittest

import numpy as np

from reports.ALGO08.v3.ingress_eight_audit import Costs, WindowView, byte_budget, split


class IngressEightAudit(unittest.TestCase):
    def test_view_retains_original_bytes_without_payload_copy(self):
        window = WindowView(np, Costs())
        raw = bytes(32)
        observed = window.frombuffer(raw, dtype="<i2")
        self.assertIs(observed.base, raw)
        self.assertEqual((window.owned, window.copied, window.input_bytes), (1, 0, 32))

    def test_nested_costs_subtract_once(self):
        amounts = {"compressed_verified": 10, "compressed_descriptor": 3, "callback": 20, "zstd_read": 8}
        costs = {key: amounts for key in ("cpu_ns", "wall_ns")}
        native = {"full": 5, "short_primary": 8}
        row = dict(acquire_cpu_ns=50, acquire_wall_ns=60, native_cpu_ns=native, native_wall_ns=native)
        result = split(row, costs)
        self.assertEqual(result["cpu_ns"]["compressed_sha_and_framing"], 7)
        self.assertEqual(result["cpu_ns"]["other_callback"], 7)
        self.assertEqual(result["cpu_ns"]["unassigned"], 12)
        self.assertEqual(sum(result["wall_ns"].values()), 60)
        with self.assertRaisesRegex(ValueError, "overlapping"):
            split(dict(row, acquire_cpu_ns=1), costs)

    def test_detector_aperture_coverage_preserves_full_decode_budget(self):
        row = {"native_schedule": {"native_calls": {"full": 16, "short_primary": 86}}}
        budget = byte_budget(row, dict(compressed_bytes=78_852_856, uncompressed_bytes=102_400_000))
        self.assertEqual(budget["detector_apertures"], 40_320_000)
        self.assertEqual(budget["out_of_detector"], 62_080_000)
        self.assertEqual(budget["required_decoded"], 102_400_000)


if __name__ == "__main__":
    unittest.main()
