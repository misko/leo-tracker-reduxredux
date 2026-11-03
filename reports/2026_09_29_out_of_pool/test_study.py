import unittest

from study import choose


class SelectionTests(unittest.TestCase):
    def test_exclusion_timestamp_sort_and_floor_quantiles(self):
        rows = [dict(session_id=str(i), capture_start_utc_ns=i, error=999 - i) for i in range(12)]
        outside, selected = choose(rows[::-1], {"0", "11"})
        self.assertEqual([r["session_id"] for r in selected], ["1", "3", "5", "7", "10"])
        self.assertEqual(len(outside), 10)
        for row in rows:
            row["error"] = -row["error"]
        self.assertEqual(choose(rows, {"0", "11"})[1], selected)

    def test_reject_duplicate_or_too_few(self):
        row = dict(session_id="same", capture_start_utc_ns=0)
        for rows in ([row] * 6, [row]):
            with self.assertRaises(ValueError):
                choose(rows, set())


if __name__ == "__main__":
    unittest.main()
