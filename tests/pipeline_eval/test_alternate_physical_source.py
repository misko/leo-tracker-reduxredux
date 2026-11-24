"""Metadata-only local fixture admission tests."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from alternate_physical_source import bytes_by_inode, compare_lengths, unique_files


class SourceIntrospectionTests(unittest.TestCase):
    def test_length_nomination_ignores_names_and_deduplicates_hard_links(self):
        with TemporaryDirectory() as location:
            root = Path(location)
            regular = root/"renamed-copy"
            regular.write_bytes(b"x"*48)
            os.link(regular, root/"same-inode")
            (root/"too-short").write_bytes(b"123")
            index, audit = unique_files(root, root.stat().st_dev)
            self.assertEqual(audit["unavailable"], [])
            self.assertEqual(bytes_by_inode(index), 51)
            self.assertTrue(compare_lengths([48, 3], index)["all_lengths_present"])
            self.assertEqual(compare_lengths([48, 48, 3], index)["missing_by_length"], {48: 1})

    def test_explicit_local_policy_skips_alias_and_device_change(self):
        with TemporaryDirectory() as location:
            root = Path(location)
            (root/"link").symlink_to("/dev")
            (root/"tle").mkdir()
            (root/"tle"/"known-non-waveform").write_bytes(b"bytes")
            index, audit = unique_files(root, root.stat().st_dev)
            self.assertEqual(index, {})
            self.assertEqual(set(map(Path, audit["policy_skipped"])), {root/"link", root/"tle"})
            index, audit = unique_files(root, -1)
            self.assertEqual(index, {})
            self.assertEqual(audit["policy_skipped"], [str(root)])

    def test_scope_caps_abort_instead_of_searching_more(self):
        with TemporaryDirectory() as location:
            root = Path(location)
            (root/"entry").touch()
            with self.assertRaises(ValueError):
                unique_files(root, root.stat().st_dev, entry_limit=1)


if __name__ == "__main__":
    unittest.main()
