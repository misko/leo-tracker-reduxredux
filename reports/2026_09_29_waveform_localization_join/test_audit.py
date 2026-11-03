import unittest

from audit import selected_partition


class PartitionTests(unittest.TestCase):
    def test_whole_visit(self):
        t = dict(visits=[1, 1, 2], training_mask=[True, True, False])
        self.assertEqual(selected_partition(t, 1), "training")
        self.assertEqual(selected_partition(t, 2), "held")
        with self.assertRaises(ValueError):
            selected_partition(t, 3)

    def test_inconsistent_visit_rejected(self):
        with self.assertRaises(ValueError):
            selected_partition(dict(visits=[1, 1], training_mask=[True, False]), 1)


if __name__ == "__main__":
    unittest.main()
