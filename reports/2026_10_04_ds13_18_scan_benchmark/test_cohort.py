"""Metadata selection tests; no hardware, PostgreSQL, QNAP, or IQ required."""
import copy
import unittest

from cohort import BLOCK_NS, ROOF, canonical, digest, select_new, verify_capture


def fixture():
    authority = dict(valid_from_utc_ns=0, valid_until_utc_ns=1000,
                     fixture_part_id="LT3D-004B", nominal_outward_tilt_deg=20,
                     latitude_deg=ROOF[0], longitude_deg=ROOF[1],
                     receivers=[dict(receiver_id=0, azimuth_deg=270), dict(receiver_id=1, azimuth_deg=90)])
    manifest = dict(session_id="example", receipt=dict(plan=dict(geometry=dict(sample_rate_hz=2500000,
                    receiver_ids=[0, 1], profiles=[dict(target=dict(channel=i)) for i in range(1, 5)]))),
                    timing=dict(first_sample_earliest_utc_ns=10, first_sample_estimate_utc_ns=11, terminal_realtime_ns=100))
    wrapper = dict(manifest=manifest, sha256=digest(canonical(manifest)))
    pose = dict(session_id="example", pose_authority=authority, pose_authority_digest=digest(canonical(authority)),
                manifest_sha256=wrapper["sha256"], capture_start_earliest_utc_ns=10, capture_end_utc_ns=100)
    pose["binding_digest"] = digest(canonical(pose))
    return wrapper, pose


class CohortTests(unittest.TestCase):
    def test_valid_binding(self):
        row = verify_capture(*fixture(), 2500000)
        self.assertTrue(all(row["metadata_checks"].values()))
        self.assertEqual(row["iq_readiness"], "not_checked")

    def test_tampered_pose_rejected(self):
        wrapper, pose = fixture()
        pose["pose_authority"]["nominal_outward_tilt_deg"] = 30
        with self.assertRaisesRegex(ValueError, "pose_binding_digest"):
            verify_capture(wrapper, pose, 2500000)

    def test_tampered_manifest_rejected(self):
        wrapper, pose = fixture()
        wrapper["manifest"]["receipt"]["plan"]["geometry"]["sample_rate_hz"] = 10000000
        with self.assertRaisesRegex(ValueError, "manifest_digest"):
            verify_capture(wrapper, pose, 2500000)

    def test_inventory_rate_rejected(self):
        with self.assertRaisesRegex(ValueError, "sample_rate"):
            verify_capture(*fixture(), 10000000)

    def test_deterministic_balanced_and_separated(self):
        rows = [dict(session_id=f"scan-{i}", capture_start_ns=i * BLOCK_NS,
                     capture_end_ns=i * BLOCK_NS + 300 * 10**9, time_block=i) for i in range(30)]
        expected = select_new(rows, [])
        self.assertEqual(expected, select_new(list(reversed(copy.deepcopy(rows))), []))
        self.assertEqual(len({r["time_block"] for r in expected}), 16)
        self.assertEqual([sum(r["split"] == s for r in expected) for s in ("development", "validation", "locked_test")], [8, 4, 4])
        self.assertTrue(all("split" not in r for r in rows))

    def test_insufficient_blocks_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "do not relax"):
            select_new([], [])


if __name__ == "__main__":
    unittest.main()
