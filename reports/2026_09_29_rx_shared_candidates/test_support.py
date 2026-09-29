import unittest

from support import compare


def item(ids, weights, snapshot="one"):
    return dict(ids=ids, weights=weights, snapshot=snapshot, catalogue_size=100)


class Tests(unittest.TestCase):
    def test_known_overlap(self):
        r = compare(item([1, 2], [0.25, 0.75]), item([2, 3], [0.6, 0.4]))
        self.assertEqual(r["intersection"], 1)
        self.assertAlmostEqual(r["agreement_mass"], 0.45)
        self.assertEqual(r["left_common_mass"], 0.75)
        self.assertTrue(r["map_equal"])

    def test_disjoint(self):
        r = compare(item([1], [1]), item([2], [1]))
        self.assertEqual(r["intersection"], 0)
        self.assertEqual(r["agreement_mass"], 0)

    def test_zero_weight_is_not_absent_support(self):
        r = compare(item([1, 2], [1, 0]), item([2, 3], [0, 1]))
        self.assertEqual(r["intersection"], 1)
        self.assertEqual(r["positive_product_rows"], 0)

    def test_order_and_swap(self):
        a, b = item([2, 1], [0.5, 0.5]), item([1, 3], [0.75, 0.25])
        r = compare(a, b)
        self.assertEqual(r, compare(item([1, 2], [0.5, 0.5]), b))
        self.assertEqual(r["agreement_mass"], compare(b, a)["agreement_mass"])
        self.assertEqual(r["left_map"], 1)

    def test_namespace(self):
        with self.assertRaises(ValueError):
            compare(item([1], [1]), item([1], [1], "other"))

    def test_invalid_candidates(self):
        for ids, weights in (
            ([1, 1], [0.5, 0.5]),
            ([100], [1]),
            ([1], [0.9]),
            ([1], [-1]),
            ([1.0], [1]),
        ):
            with self.assertRaises(ValueError):
                compare(item(ids, weights), item([1], [1]))


if __name__ == "__main__":
    unittest.main()
