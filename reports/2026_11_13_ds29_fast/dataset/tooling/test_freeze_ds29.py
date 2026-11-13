"""Observable membership, metadata-only inventory, and sealing guarantees."""

import json
import tempfile
import unittest
from pathlib import Path

import freeze_ds29 as freeze


class DatasetFreezeTests(unittest.TestCase):
    def test_boundaries_deduplication_and_failures(self):
        def member(identity, stamp, root):
            return dict(case_id=root, captured_utc_ns=stamp, recording_state="incomplete",
                        tracking_inputs=[], raw_recording=dict(identity_sha256=identity, root=root, duplicate_roots=[]))
        parent = dict(cutoff_utc_ns=20, members=[member("parent", 10, "old")])
        values = [member("a", 20, "a"), member("a", 20, "copy"), member("b", 29, "b"),
                  member("earlier", 19, "earlier"), member("later", 30, "later")]
        result = freeze.pinned.freeze_members(values, parent, 30, "DS29")
        self.assertEqual([r["dataset_label"] for r in result], ["DS29-0001", "DS29-0002"])
        self.assertEqual(result[0]["raw_recording"]["duplicate_roots"], ["copy"])
        self.assertTrue(all(r["recording_state"] == "incomplete" and not r["tracking_inputs"] for r in result))
        with self.assertRaises(ValueError):
            freeze.pinned.freeze_members([member("parent", 21, "overlap")], parent, 30, "DS29")

    def test_real_inventory_retains_empty_failures_and_all_rates(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            roots = []
            for name, rate in [("one", 1250000), ("two", 10000000)]:
                root = base / name
                segment = root / "segment"
                segment.mkdir(parents=True)
                freeze.write(segment / "manifest.json", dict(kind="short_window_iq_recording", created_utc_ns=28,
                    timing=dict(first_sample_estimate_utc_ns=21), status="failed", sample_rate_hz=rate,
                    configuration=dict(targets=[dict(channel=3)]), chunks=[]))
                roots.append(root)
            values = freeze.collect_members(roots, base)
            self.assertEqual(len(values), 2)
            self.assertEqual({r["sample_rate_hz"] for r in values}, {1250000, 10000000})
            self.assertEqual({r["captured_utc_ns"] for r in values}, {21})
            self.assertTrue(all(r["recording_state"] == "incomplete" and not r["glrt_availability"]["available"] for r in values))

    def test_whole_acquisition_boundary_and_adaptive_format_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for acquisition, stamps in [("old", [19, 21]), ("new", [20, 31]), ("future", [30])]:
                for number, stamp in enumerate(stamps):
                    segment = root / acquisition / str(number)
                    segment.mkdir(parents=True)
                    freeze.write(segment / "manifest.json", dict(kind="short_window_iq_recording", created_utc_ns=stamp))
            adaptive = root / "adaptive"
            adaptive.mkdir()
            freeze.write(adaptive / "manifest.json", dict(kind="starlink_adaptive_hop_iq", created_utc_ns=22))
            audit, roots = freeze.census([root], 20, 30)
            self.assertEqual(roots, [root / "new"])
            self.assertEqual(audit["adaptive_excluded_by_recording_format"], 1)
            self.assertEqual(audit["errors"], [])


if __name__ == "__main__":
    unittest.main()
