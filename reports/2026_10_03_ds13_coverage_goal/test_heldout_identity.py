import unittest
from summarize_heldout_identity import checked_partition


class IdentityPartitionTests(unittest.TestCase):
    def test_partition(self):
        self.assertEqual(checked_partition(dict(accepted_rows=[1],ambiguous_rows=[2],untested_rows=[3]),[3,2,1]),[1,1,1])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            checked_partition(dict(accepted_rows=[1],ambiguous_rows=[1],untested_rows=[]),[1])

    def test_missing_rejected(self):
        with self.assertRaises(ValueError):
            checked_partition(dict(accepted_rows=[1],ambiguous_rows=[],untested_rows=[]),[1,2])
