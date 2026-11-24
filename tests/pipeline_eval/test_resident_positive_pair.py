from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from reports.ALGO08.v3 import resident_positive_pair as pair
from reports.ALGO08.v3 import resident_positive_saved as saved


class PassivePhysicalTests(unittest.TestCase):
    def test_cold_metadata_does_not_authorize_a_payload(self):
        with TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "manifest.json").write_text("invalid JSON")
            (directory / "iq-000000.ci16.zst").write_bytes(b"sample")
            (directory / "windows-000000.jsonl").write_text("test")

            def sample(paths):
                warm = all(name != "manifest.json" for _, name, _ in paths)
                return dict(unavailable={}, members=len(paths), observed_members=len(paths),
                            cached_pages=len(paths) if warm else 0, observed_file_pages=len(paths))

            with patch.object(pair, "BULK", directory):
                observed = pair.official(dict(path=root, manifest_digest="unused"), sample)
            self.assertFalse(observed["admitted"])
            self.assertFalse(observed["manifest_verified"])
            self.assertEqual(observed["data"]["payload"]["bytes"], 6)

    def test_bound_manifest_still_requires_every_payload_page(self):
        with TemporaryDirectory() as root:
            directory = Path(root)
            data = json.dumps(dict(window_count=64, chunks=[
                dict(payload_relative_path="iq-000000.ci16.zst", compressed_bytes=6, compressed_sha256="payload-digest",
                     index_relative_path="windows-000000.jsonl", index_bytes=4, index_sha256="index-digest")])).encode()
            (directory / "manifest.json").write_bytes(data)

            def sample(paths):
                warm = all(not name.endswith(".zst") for _, name, _ in paths)
                return dict(unavailable={}, members=len(paths), observed_members=len(paths),
                            cached_pages=len(paths) if warm else 0, observed_file_pages=len(paths))

            with patch.object(pair, "BULK", directory):
                observed = pair.official(dict(path=root, manifest_digest=sha256(data).hexdigest()), sample)
            self.assertTrue(observed["manifest_verified"])
            self.assertFalse(observed["admitted"])
            self.assertEqual(observed["data"]["payload"]["bound_members"][0]["sha256"], "payload-digest")


class PhysicalRangeTests(unittest.TestCase):
    def test_keeps_both_radios_and_clock_of_the_exact_prefix(self):
        parent = dict(delivery_clocks=list(range(5)), clock_anchor=dict(sample_counter=0, before={"realtime_ns": 42}),
                      source=dict(sample_rate_hz=10_000_000, probe_ms=20, raw_recording_authority_digest="parent",
                                  probes=[dict(visit_index=i, receiver_id=j, probe_start_ms=0,
                                               valid_start_counter=i*200_000, probe_index=0)
                                          for i in (0, 2, 3, 4) for j in (0, 1)]),
                      provenance=dict(window_count=5, detector_sha256="sha256:" + "a"*64,
                                      excluded_windows=[dict(visit=1)]))
        inventory = dict(window_count=5, recording_name="recording",
                         segments=[dict(windows=n) for n in (2, 2, 1)])
        with patch.object(saved, "RANGE", (0, 4)):
            packet, scope, witness = saved.clip(parent, inventory, "parent_native")
        self.assertEqual(len(scope["segments"]), 2)
        self.assertEqual(packet["clock_anchor"], parent["clock_anchor"])
        self.assertEqual(packet["delivery_clocks"], [0, 1, 2, 3])
        self.assertEqual(packet["source"]["probes"], parent["source"]["probes"][:6])
        self.assertEqual(packet["provenance"]["excluded_windows"], parent["provenance"]["excluded_windows"])
        self.assertEqual(witness["last_sample_counter"], 800_000)
        self.assertNotEqual(packet["source"]["raw_recording_authority_digest"], witness["original_raw_authority"])

    def test_rejects_an_absent_lane(self):
        parent = dict(delivery_clocks=[0], source=dict(probes=[dict(visit_index=0, receiver_id=0)]),
                      provenance=dict(window_count=1, excluded_windows=[]))
        with patch.object(saved, "RANGE", (0, 1)), self.assertRaisesRegex(ValueError, "chronology"):
            saved.clip(parent, dict(segments=[dict(windows=1)], window_count=1), "original")
