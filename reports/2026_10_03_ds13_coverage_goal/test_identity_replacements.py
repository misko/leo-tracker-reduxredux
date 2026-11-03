import unittest
from audit_identity_replacements import collision_groups


class ReplacementTests(unittest.TestCase):
    def test_shared_probe_rejected_even_with_distinct_rows(self):
        self.assertEqual(collision_groups([0,2],[1,3],[4,4,5,6]),[4])

    def test_disjoint_probes_and_empty_destination(self):
        self.assertEqual(collision_groups([0],[1],[4,5]),[])
        self.assertEqual(collision_groups([0],[],[4,5]),[])
