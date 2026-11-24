"""Causal admission tests for reuse between the two saved DS30 requests."""

from dataclasses import dataclass
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from historical_orbit_index import HOUR_NS
from portable_orbit_0316 import chronology, distinct_sources


@dataclass(order=True)
class Ref:
    collected_utc_ns: int
    sha256: str


class ChronologicalIndexTests(unittest.TestCase):
    def test_earlier_admission_is_strictly_before_target(self):
        earlier = {"same": True, "earlier only": True}
        target = {"same": True, "future only": True}
        self.assertEqual(chronology(8, 9, earlier, target), ["same"])
        for cutoff in (9, 10):
            with self.assertRaises(ValueError):
                chronology(cutoff, 9, earlier, target)

    def test_body_reuse_starts_with_earliest_authentic_reference(self):
        first, duplicate = Ref(HOUR_NS, "same"), Ref(2*HOUR_NS, "same")
        consumer_only = Ref(3*HOUR_NS, "different")
        result = distinct_sources([duplicate, consumer_only, first], 4*HOUR_NS)
        self.assertEqual(result, {"same": first, "different": consumer_only})

    def test_future_or_out_of_window_source_aborts_producer_admission(self):
        cutoff = 73*HOUR_NS
        valid = Ref(HOUR_NS, "valid")
        self.assertEqual(distinct_sources([valid], cutoff), {"valid": valid})
        for invalid in (Ref(HOUR_NS-1, "too old"), Ref(cutoff+1, "future")):
            with self.assertRaises(ValueError):
                distinct_sources([valid, invalid], cutoff)


if __name__ == "__main__":
    unittest.main()
