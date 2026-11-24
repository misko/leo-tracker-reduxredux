"""Causal admission tests for reuse between the two saved DS30 requests."""

from dataclasses import dataclass
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from historical_orbit_index import HOUR_NS
from portable_orbit_0316 import chronology, distinct_sources
from portable_orbit_0316_repair import regional_evidence
from portable_orbit_compatibility import (
    LEGACY_SOURCE_INDEX, REPAIRED_SOURCE_INDEX, UnsupportedExport, compatible_versions,
)


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

    def test_repaired_reader_accepts_only_prior_writer_semantics(self):
        def pins(index, native="original"):
            return dict(sgp4_version="2.27", source_sha256={"source_index": index, "native_sgp4": native})

        repaired, previous = pins(REPAIRED_SOURCE_INDEX), pins(LEGACY_SOURCE_INDEX)
        self.assertEqual(compatible_versions(repaired, previous), previous)
        self.assertEqual(compatible_versions(repaired, repaired), repaired)
        for actual, proposed in ((pins("another"), previous), (repaired, pins(LEGACY_SOURCE_INDEX, "modified")),
                                 (previous, repaired)):
            with self.assertRaises(UnsupportedExport):
                compatible_versions(actual, proposed)

    def test_regional_comparison_requires_real_probes_and_preserves_evidence(self):
        proof = dict(complete=False, would_withhold=False, probes_evaluated=24,
                     stop="eligible_exterior_separation", snapshots=list(range(9)),
                     potentially_visible_orbits=626)
        worker = dict(early_regional=[dict(result=proof, cpu_s=0.31, reused=0)],
                      solve=dict(geographic_projector=dict(consumed=24, block_positions=24, block_calls=6,
                                                           scalar_positions=0, fallbacks=0),
                                 prepared_exterior=dict(prepared_catalogues=1, catalogue_handoff=1)))
        self.assertEqual(regional_evidence(worker), dict(result=proof, reused=0))
        worker["early_regional"][0]["result"] = {"complete": False, "diagnostic_error": "must be a Satrec"}
        with self.assertRaises(ValueError):
            regional_evidence(worker)


if __name__ == "__main__":
    unittest.main()
