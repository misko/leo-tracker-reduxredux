import unittest
from summarize_training_union import validate_partition


class UnionSummaryTests(unittest.TestCase):
    def fixture(self):return [dict(fold=i,original_test_rows=[i],original_train_rows=[j for j in range(5) if j!=i]) for i in range(5)]

    def test_full_partition(self):validate_partition(self.fixture(),range(5))

    def test_equal_counts_do_not_hide_duplicate_test_rows(self):
        r=self.fixture();r[4]['original_test_rows']=[0]
        with self.assertRaises(ValueError):validate_partition(r,range(5))

    def test_train_overlap_rejected(self):
        r=self.fixture();r[0]['original_train_rows'].append(0)
        with self.assertRaises(ValueError):validate_partition(r,range(5))


if __name__=='__main__':unittest.main()
