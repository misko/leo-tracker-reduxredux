"""Tests for bounded first and last member admission."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from end_member_admission import end_observation, members


class EndMemberTests(unittest.TestCase):
    def test_captured_tail_arithmetic(self):
        self.assertEqual([members(n) for n in (1,64,65,123,199,216,512)], [1,1,2,2,4,4,8])
        for count in (0, 513, True):
            with self.assertRaises(ValueError):
                members(count)

    def test_checks_extent_before_passive_query(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/"fixture"
            path.write_bytes(b"wave")
            invoked = []

            def query(fd, size):
                invoked.append((os.fstat(fd).st_size,size))
                return 1, 0

            self.assertIn("unavailable", end_observation(path,"local-test-pin",query,3))
            self.assertEqual(invoked, [])
            result = end_observation(path,"local-test-pin",query,4)
            self.assertEqual(invoked, [(4,4)])
            self.assertEqual((result["file_pages"],result["cached_pages"]), (1,0))

    def test_rejects_symlink_without_query(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"fixture").touch()
            alias = root/"alias"
            alias.symlink_to(root/"fixture")
            self.assertIn("unavailable", end_observation(alias,"local-test-pin",self.fail))


if __name__ == "__main__":
    unittest.main()
