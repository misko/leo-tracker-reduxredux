import unittest

from run import check_partition


class Tests(unittest.TestCase):
    def test_rejects_source_target_overlap_in_time(self):
        rows = [
            dict(
                window=["early", "middle", "late"][i // 8],
                start_utc_ns=i * 400_000_000_000,
                input=dict(session_id=str(i)),
            )
            for i in range(24)
        ]
        check_partition(rows)
        rows[16]["start_utc_ns"] = rows[15]["start_utc_ns"] + 1
        with self.assertRaises(AssertionError):
            check_partition(rows)


if __name__ == "__main__":
    unittest.main()
