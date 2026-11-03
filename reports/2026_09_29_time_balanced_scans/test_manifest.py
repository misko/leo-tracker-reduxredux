import unittest

from manifest import balanced


class ManifestTests(unittest.TestCase):
    def test_exact_partition_and_value_independence(self):
        rows = [
            dict(
                session_id=str(i),
                start_utc_ns=i,
                window=("early", "middle", "late")[i // 8],
                measurement=i,
            )
            for i in range(24)
        ]
        groups = balanced(list(reversed(rows)))
        self.assertEqual(
            [[int(r["session_id"]) for r in g] for g in groups],
            [list(range(i, 24, 3)) for i in range(3)],
        )
        for r in rows:
            r["measurement"] = 99999
        self.assertEqual(balanced(rows), groups)
        with self.assertRaises(ValueError):
            balanced(rows[:-1] + [rows[0]])


if __name__ == "__main__":
    unittest.main()
