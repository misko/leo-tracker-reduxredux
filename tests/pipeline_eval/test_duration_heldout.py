from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[2]/'reports/ALGO08/v3/duration_heldout.py'
SPEC = spec_from_file_location('duration_heldout', MODULE)
HOLDOUT = module_from_spec(SPEC)
SPEC.loader.exec_module(HOLDOUT)


class TestDurationHoldout(unittest.TestCase):
    def test_rank_uses_duration_and_bytes_and_keeps_unsplit_rows(self):
        rows = [dict(case=case, windows=n, compressed_MB=Decimal(size), stages=split,
                     members=1, inventory_sha256=case)
                for case, n, size, split in [('a', 8, '14', [99., 0.2, 1.]), ('b', 10, '18', [2., 6., 1.]),
                                             ('c', 10, '16.000001', [1., 21., 1.]), ('d', 11, '16', [2., 3., 1.]),
                                             ('e', 10, '17', [0., 0., 8.]), ('DS30-0008', 10, '17', [4., 2., 1.])]]
        chosen = HOLDOUT.plan(rows)
        self.assertEqual(chosen['case'], 'c')
        self.assertEqual(chosen['compressed_bytes'], 16000001)
        self.assertEqual(chosen['split_known_positive_count'], 5)
        self.assertEqual(chosen['eligible'], 4)
        self.assertEqual(chosen['unsplit'], ['e'])
        self.assertEqual(chosen['ledger_count'], len(rows))

    def test_raw_payload_descriptors_never_read_the_body(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as root:
            path = Path(root)/'iq-000000.ci16.zst'
            path.write_bytes(b'test')
            with patch.object(HOLDOUT.os, 'pread', side_effect=AssertionError('unexpected read')):
                pages, body = HOLDOUT.inspect(path, expected=4)
            self.assertEqual(pages['resident_pages'], 1)
            self.assertIsNone(body)

    def test_incomplete_metadata_residency_prevents_body_read(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as root:
            path = Path(root)/'manifest.json'
            path.write_bytes(b'{}')
            with (patch.object(HOLDOUT, 'sample', return_value=(1, 0)),
                  patch.object(HOLDOUT.os, 'pread', side_effect=AssertionError('unexpected read'))):
                pages, body = HOLDOUT.inspect(path, saved_json=True)
            self.assertEqual(pages['resident_pages'], 0)
            self.assertIsNone(body)

    def test_scope_hash_rejects_same_extent_with_changed_contents(self):
        with self.assertRaisesRegex(ValueError, 'pinned digest'):
            HOLDOUT.verified(b'{"a":1}', HOLDOUT.tagged(b'{"a":0}'))


if __name__ == '__main__':
    unittest.main()
