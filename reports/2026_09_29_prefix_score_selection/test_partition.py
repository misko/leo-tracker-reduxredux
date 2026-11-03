import unittest

from run import partition


class Tests(unittest.TestCase):
    def test_prefix_and_strict_future_cutoff(self):
        scans = [
            dict(start_utc_ns=i * 400_000_000_000, input=dict(session_id=str(i))) for i in range(24)
        ]
        cutoff = scans[11]["start_utc_ns"] + 300_000_000_000
        targets = [
            dict(start_utc_ns=cutoff + i, input=dict(session_id=f"t{i}")) for i in (-1, 0, 1)
        ]
        result = partition(list(reversed(scans)), targets)
        self.assertEqual(result["scans"], scans[:12])
        self.assertEqual(result["targets"], [targets[-1]])


if __name__ == "__main__":
    unittest.main()
