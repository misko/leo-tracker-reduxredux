from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from tempfile import TemporaryDirectory
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import integrated_original_batch as batch


class IntegratedOriginalBatchTest(TestCase):
    def test_explicit_request_keeps_original_path_and_frozen_ports(self):
        args = SimpleNamespace(recording=Path("/recording"), archive=Path("/tle"),
                               region=Path("/region.json"), bulk_root=Path("/result"))
        artifact = {"path": "/checked.so", "sha256": "b" * 64}
        book = {"native": {flag: artifact for flag in (*batch.PATH_OPTIONS, *batch.SIGNED_OPTIONS)},
                "portable_producer": artifact}
        argv = batch.original_argv(args, book, {"archive_sha256": "sha256:" + "a" * 64})
        self.assertEqual(argv[argv.index("--recording") + 1], "/recording")
        self.assertEqual(argv[argv.index("--output") + 1], "/result")
        self.assertTrue(set(batch.FLAGS) <= set(argv))
        self.assertEqual(argv[argv.index("--portable-orbit-index-sha256") + 1], "sha256:" + "b" * 64)
        self.assertEqual(argv[argv.index("--portable-orbit-producer-sha256") + 1], "b" * 64)
        self.assertNotIn("--strict-packed-eight", argv)

    def test_different_inventory_and_clock_fail_closed(self):
        authority = dict(session_id="fast-one", inventory_sha256="I", raw_authority_sha256="R",
                         window_count=2, causal_cutoff_utc_ns=75)
        batch.match_inventory(authority, "fast-one", "I", {"window_count": 2})
        with self.assertRaises(ValueError):
            batch.match_inventory(authority, "fast-one", "I", {"window_count": 1})
        native = dict(clock_anchor={"before": {"realtime_ns": 75}},
                      source=dict(session_id="fast-one", input_manifest_sha256="I",
                                  raw_recording_authority_digest="R"))
        batch.match_native(authority, native)
        native["clock_anchor"]["before"]["realtime_ns"] = 76
        with self.assertRaises(ValueError):
            batch.match_native(authority, native)

    def test_direct_paths_and_read_only_originals(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            recording, archive = root / "recording", root / "archive"
            recording.mkdir()
            archive.mkdir()
            member = recording / "one"
            member.write_bytes(b"signed")
            link = recording / "link"
            link.symlink_to(member)
            args = SimpleNamespace(recording=recording, archive=archive, region=root / "region",
                                   bulk_root=root / "out", build=root / "build", authority=root / "authority")
            approved, guard = batch.paths_for(args, frozenset())
            self.assertEqual(approved(recording), recording)
            self.assertEqual(approved(member, root=recording), member)
            with self.assertRaises(ValueError):
                approved(link, root=recording)
            guard("open", (str(member), "r", os.O_RDONLY))
            with self.assertRaises(ValueError):
                guard("open", (str(member), "w", os.O_WRONLY))
            with self.assertRaises(ValueError):
                guard("open", ("/srv/bulk/unrelated", "r", os.O_RDONLY))
            with self.assertRaises(ValueError):
                guard("open", ("/mnt/qnap01/unrelated", "r", os.O_RDONLY))
