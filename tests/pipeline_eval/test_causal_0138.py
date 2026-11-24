from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

from leo.operations.tle_archive import TleArchiveReader

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'reports/ALGO08/v3'))
from causal_0138 import exact_plan, HISTORY_NS, snapshot_digest, write_projection


class TestCausal0138(unittest.TestCase):
    def test_copy_deduplicates_bodies_and_preserves_collection_timestamps(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as name:
            root = Path(name)
            archives = [root/f'donor{index}' for index in range(2)]
            cutoff = 5*HISTORY_NS
            original_a, original_b = cutoff-10, cutoff-5
            body = b'retained exact original\n'
            checksum = sha256(body).hexdigest()
            for archive, stamp in zip(archives, (original_a, original_b), strict=True):
                folder = archive/'archive/space-track'
                folder.mkdir(parents=True)
                (folder/f'{stamp}-{checksum}.tle').write_bytes(body)
                # The ordinary collection bound is exclusive at the cutoff.
                (folder/f'{cutoff}-{checksum}.tle').write_bytes(body)
            readers = {reader: reader.list_snapshots('space-track') for reader in map(TleArchiveReader, archives)}
            eligible = [ref for refs in readers.values() for ref in refs if ref.collected_utc_ns < cutoff]
            pin = snapshot_digest(eligible)
            planned = exact_plan(readers, cutoff, pin)
            summary = write_projection(root/'dst', planned)
            self.assertEqual(summary['snapshots_sha256'], pin)
            self.assertEqual(summary['distinct_bodies'], 1)
            self.assertEqual(summary['bytes'], 2*len(body))
            self.assertEqual(summary['distinct_body_bytes'], len(body))
            copies = TleArchiveReader(root/'dst').list_snapshots()
            self.assertEqual([r.collected_utc_ns for r in copies], [original_a, original_b])
            self.assertTrue(copies[0].path.samefile(copies[1].path))
            self.assertFalse(copies[0].path.samefile(eligible[0].path))

    def test_a_locally_present_subset_does_not_invent_archive_members(self):
        with self.assertRaisesRegex(ValueError, 'sealed roster'):
            exact_plan({}, 5*HISTORY_NS, 'sha256:'+'0'*64)


if __name__ == '__main__':
    unittest.main()
