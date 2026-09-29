import unittest

from grouping import available, groups


class Tests(unittest.TestCase):
    def test_target_hole_splits(self):
        records = [dict(dataset="DS7", session_id=str(i)) for i in range(20)]
        result = groups(records, {"6", "13"})
        self.assertEqual(
            [[r["session_id"] for r in g] for g in result],
            [
                [str(i) for i in range(6)],
                [str(i) for i in range(7, 13)],
                [str(i) for i in range(14, 20)],
            ],
        )

    def test_maximum_and_dataset_boundaries(self):
        records = [
            dict(dataset=ds, session_id=ds + str(i)) for ds in ("DS7", "DS8") for i in range(10)
        ]
        result = groups(records, set())
        self.assertEqual([len(g) for g in result], [8, 2, 8, 2])
        self.assertEqual(len({r["session_id"] for g in result for r in g}), 20)

    def test_whole_group_causality(self):
        g = dict(available_utc_ns=100)
        self.assertFalse(available(g, 99))
        self.assertFalse(available(g, 100))
        self.assertTrue(available(g, 101))


if __name__ == "__main__":
    unittest.main()
