import unittest
from training_union import union_modes


class TrainingUnionTests(unittest.TestCase):
    def test_both_arms_modes_kept_exact_duplicates_once(self):
        def p(t):return dict(catalog_number=100,satellite_index=2,total_timing_s=t)
        d=[dict(original_rows=[1,4],proposals=[p(1),p(2)]),dict(original_rows=[1,4],proposals=[p(2),p(3)])]
        self.assertEqual([x['total_timing_s'] for x in union_modes(d)],[1,2,3])

    def test_different_training_rows_rejected(self):
        with self.assertRaises(ValueError):union_modes([dict(original_rows=[1],proposals=[]),dict(original_rows=[2],proposals=[])])


if __name__=='__main__':unittest.main()
