import collections
import unittest

from manifest import groups


class BudgetTests(unittest.TestCase):
    def test_sizes_coverage_and_temporal_balance(self):
        rows = [dict(session_id=str(i), start_utc_ns=i, window=i // 8) for i in range(24)]
        for count, multiplicity in ((8, 1), (12, 1), (16, 2), (24, 1)):
            sets = groups(list(reversed(rows)), count)
            self.assertTrue(all(len(s) == count for s in sets))
            coverage = collections.Counter(r["session_id"] for s in sets for r in s)
            self.assertEqual(coverage, {str(i): multiplicity for i in range(24)})
            self.assertTrue(all({r["window"] for r in s} == {0, 1, 2} for s in sets))
        with self.assertRaises(ValueError):
            groups(rows[:-1] + [rows[0]], 12)


if __name__ == "__main__":
    unittest.main()
