import unittest
from expanded_training_refit import assert_row_lineage


class ExpandedRefitTests(unittest.TestCase):
    def test_lineage_and_separation(self):
        r=dict(original_train_rows=[1,3],original_test_rows=[2,4])
        assert_row_lineage([1,3],[2,4],r)
        with self.assertRaises(AssertionError):assert_row_lineage([1,4],[2,3],r)
        with self.assertRaises(ValueError):assert_row_lineage([1],[1],dict(original_train_rows=[1],original_test_rows=[1]))


if __name__=='__main__':unittest.main()
