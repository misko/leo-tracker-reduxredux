import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from weak_publisher_attribution import read_scope, validate_profile


class SavedPublisherAttribution(unittest.TestCase):
    def test_exclusive_partition(self):
        profile = {"stages": {"solve": {"cpu_ns": 20, "elapsed_ns": 22, "calls": 1},
                              "render": {"cpu_ns": 5, "elapsed_ns": 6, "calls": 1},
                              "hash": {"cpu_ns": 2, "elapsed_ns": 3, "calls": 4}},
                   "cpu_ns": 27, "elapsed_ns": 31}
        self.assertEqual(validate_profile(profile), {"cpu_ns": 2, "elapsed_ns": 3})
        with self.assertRaisesRegex(ValueError, "reconcile"):
            validate_profile(dict(profile, elapsed_ns=35))
        profile["stages"]["render"]["calls"] = 2
        with self.assertRaisesRegex(ValueError, "protected boundary"):
            validate_profile(profile)

    def test_waveforms_disallowed_and_output_reads_separate(self):
        out = Path("/dev/shm/request")
        self.assertEqual(read_scope(out/"work/detections.json", out), "detection_read")
        self.assertEqual(read_scope(out/"position-grid.json", out), "sidecar_read")
        self.assertEqual(read_scope(out/"a/b.png", out), "png_read")
        self.assertEqual(read_scope(out/"a/manifest.json", out), "manifest_read")
        self.assertEqual(read_scope(Path("/tmp/archive/body"), out), "source_and_asset_read")
        with self.assertRaisesRegex(ValueError, "waveform"):
            read_scope(Path("/tmp/iq-0000.ci16.zst"), out)


if __name__ == "__main__":
    unittest.main()
