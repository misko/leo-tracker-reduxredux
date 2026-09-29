import unittest

from core import map_rows, support_counts


class Tests(unittest.TestCase):
    def test_row_reordering(self):
        self.assertEqual(map_rows([100, 200], [0], 2), map_rows([200, 100], [1], 2))
        self.assertNotEqual(map_rows([100, 200], [0], 2), map_rows([200, 100], [0], 2))

    def test_size_and_duplicates(self):
        for numbers, rows, size in (([1], [0], 2), ([1, 1], [0], 2), ([1, 2], [0, 0], 2)):
            with self.assertRaises(ValueError):
                map_rows(numbers, rows, size)

    def test_invalid_indices(self):
        for row in (-1, 2, True, 0.5):
            with self.assertRaises(ValueError):
                map_rows([1, 2], [row], 2)

    def test_causal_distinct_scans(self):
        scans = {
            k: dict(start_utc_ns=t, block=b)
            for k, t, b in [
                ("a", 1, "old"),
                ("b", 2, "current"),
                ("target", 3, "current"),
                ("tie", 3, "old"),
                ("future", 4, "old"),
            ]
        }
        index = {100: set(scans)}
        self.assertEqual(support_counts(scans["target"], index, scans), {100: 2})
        self.assertEqual(support_counts(scans["target"], index, scans, True), {100: 1})


if __name__ == "__main__":
    unittest.main()
