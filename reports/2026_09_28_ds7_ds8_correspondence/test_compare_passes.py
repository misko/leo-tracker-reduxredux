"""Encounter counting should not confuse receiver replicas with repeat passes."""

import unittest

from compare_passes import encounters


class EncounterTests(unittest.TestCase):
    def test_replicas_and_fragments_merge(self):
        rows = [
            dict(start_s=0, end_s=30),
            dict(start_s=1, end_s=31),
            dict(start_s=45, end_s=60),
            dict(start_s=18000, end_s=18030),
        ]
        result = encounters(rows)
        self.assertEqual([len(e["rows"]) for e in result], [3, 1])

    def test_nested_interval_does_not_shorten_encounter(self):
        rows = [
            dict(start_s=0, end_s=900),
            dict(start_s=50, end_s=60),
            dict(start_s=1490, end_s=1500),
        ]
        self.assertEqual(len(encounters(rows)), 1)
        self.assertEqual(len(encounters(rows, gap_s=300)), 2)


if __name__ == "__main__":
    unittest.main()
