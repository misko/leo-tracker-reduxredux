import unittest
from features import select_native


class SelectionTest(unittest.TestCase):
    def test_equal_metadata_strata_and_no_duplicates(self):
        rows=[dict(rate_hz=rate,target=dict(edge=edge),visit_index=i)
              for rate in (2500000,5000000,7500000,10000000)
              for edge in ('lower','upper') for i in range(13)]
        selected=select_native(rows)
        self.assertEqual(len(selected),32)
        self.assertEqual([r['visit_index'] for r in selected[:4]],[0,4,8,12])
        self.assertEqual(len({(r['rate_hz'],r['target']['edge'],r['visit_index']) for r in selected}),32)
        with self.assertRaises(ValueError):select_native(rows[:12])


if __name__=='__main__':unittest.main()
