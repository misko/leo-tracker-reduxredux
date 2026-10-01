#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

import compare_membership as subject

NS = 1_000_000_000
RF = 11_200_000_000.0
SPACING = 1.0 / 4.4e-6
LANE = subject.Lane(0, 1, "lower", RF)


def make_side(prefix, visits, *, alias=0, incompatible=()):
    observations, sources, points = {}, {}, []
    for ordinal, visit in enumerate(visits):
        candidate = f"{prefix}-{visit}"
        center = visit * NS
        raw = 10_000.0 + visit * 100.0
        if visit in incompatible:
            raw += 20_000.0
        observations[candidate] = subject.Observation(
            candidate, f"{prefix}-group-{visit}", LANE, center - NS // 10, center,
            center + NS // 10, raw)
        sources[candidate] = (visit, 0, 0)
        normalized = raw + alias * SPACING
        points.append(subject.Point(candidate, f"{prefix}-group-{visit}", normalized,
                                    normalized - alias * SPACING, alias))
    return observations, sources, tuple(points)


def track(index, points, observations, *, rate=0.0, intercept=0.0):
    values = [observations[p.candidate] for p in points]
    return subject.Track(index, LANE, min(x.start_ns for x in values),
                         max(x.end_ns for x in values), values[0].center_ns,
                         rate, intercept, points)


class MembershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = json.loads(Path(subject.__file__).with_name("thresholds.json").read_text())

    def test_alias_consistent_membership_ignores_crossed_linear_summaries(self):
        ref_obs_a, ref_map_a, ref_points_a = make_side("ref", range(10))
        ref_obs_b, ref_map_b, ref_points_b = make_side("ref", range(20, 30))
        out_obs_a, out_map_a, out_points_a = make_side("out", range(8), alias=1)
        out_obs_b, out_map_b, out_points_b = make_side("out", range(20, 28), alias=-1)
        reference_observations = ref_obs_a | ref_obs_b
        output_observations = out_obs_a | out_obs_b
        reference_sources = ref_map_a | ref_map_b
        output_sources = out_map_a | out_map_b
        references = subject.Tracks(20, 20, "server", (
            track(0, ref_points_a, reference_observations, rate=100, intercept=1_000),
            track(1, ref_points_b, reference_observations, rate=-100, intercept=-1_000),
        ))
        # Compatibility summaries deliberately cross: membership must still pair
        # by measured source evidence.
        outputs = subject.Tracks(16, 16, "curved", (
            track(0, out_points_a, output_observations, rate=-100, intercept=-1_000),
            track(1, out_points_b, output_observations, rate=100, intercept=1_000),
        ))
        report = subject.compare(references, outputs, reference_observations,
                                 output_observations, reference_sources, output_sources,
                                 self.settings)
        self.assertEqual(report["primary"]["complete_one_to_one_count"], 2)
        self.assertEqual([(x["reference_track_index"], x["output_track_index"])
                          for x in report["primary"]["matches"]], [(0, 0), (1, 1)])
        self.assertTrue(all(x["reference_source_coverage"] == 0.8
                            for x in report["primary"]["matches"]))

    def test_long_arc_merge_and_fragments_are_visible_without_count_inflation(self):
        ref_obs_a, ref_map_a, ref_points_a = make_side("ra", range(10))
        ref_obs_b, ref_map_b, ref_points_b = make_side("rb", range(20, 30))
        out_obs_a, out_map_a, out_points_a = make_side("oa", range(8), alias=1)
        out_obs_b, out_map_b, out_points_b = make_side("ob", range(20, 28), alias=-1)
        ro, rm = ref_obs_a | ref_obs_b, ref_map_a | ref_map_b
        oo, om = out_obs_a | out_obs_b, out_map_a | out_map_b
        references = subject.Tracks(20, 20, "server", (
            track(0, ref_points_a, ro), track(1, ref_points_b, ro)))
        long_arc = track(0, out_points_a + out_points_b, oo)
        report = subject.compare(references, subject.Tracks(16, 16, "curved", (long_arc,)),
                                 ro, oo, rm, om, self.settings)
        self.assertEqual(report["primary"]["complete_one_to_one_count"], 1)
        self.assertEqual(report["primary"]["merge_evidence"], [{
            "output_track_index": 0, "eligible_reference_indexes": [0, 1]}])
        for reference in report["fragment_union_coverage"]:
            self.assertEqual(reference["union_reference_source_coverage"], 0.8)
        match = report["primary"]["matches"][0]
        self.assertEqual(match["in_span_output_purity"], 1.0)
        self.assertEqual(match["overall_output_purity"], 0.5)

        # Two independently complete fragments create split evidence but still
        # only one conservative one-to-one recovery for this reference.
        one_reference = subject.Tracks(10, 10, "server", (references.values[0],))
        fragment_a = track(0, out_points_a, oo)
        fragment_b = track(1, out_points_a, oo)
        split = subject.compare(one_reference, subject.Tracks(8, 8, "curved",
                                (fragment_a, fragment_b)), ref_obs_a, out_obs_a,
                                ref_map_a, out_map_a, self.settings)
        self.assertEqual(split["primary"]["complete_one_to_one_count"], 1)
        self.assertEqual(split["primary"]["split_evidence"], [{
            "reference_track_index": 0, "eligible_output_indexes": [0, 1]}])

    def test_input_cfo_ceiling_separates_data_limit_from_algorithm_miss(self):
        ro, rm, rp = make_side("ref", range(10))
        oo, om, op = make_side("arm", range(10), incompatible={7, 8, 9})
        reference = subject.Tracks(10, 10, "server", (track(0, rp, ro),))
        output = subject.Tracks(10, 10, "curved", (track(0, op, oo),))
        report = subject.compare(reference, output, ro, oo, rm, om, self.settings)
        support = report["reference_input_support"][0]
        self.assertEqual(support["input_available_source_coverage"], 1.0)
        self.assertEqual(support["cfo_consistent_input_ceiling_coverage"], 0.7)
        self.assertTrue(support["data_limited_for_primary_coverage"])
        self.assertEqual(report["primary"]["input_unsupported_reference_indexes"], [0])

    def test_dense_tied_matching_is_bounded_and_maximum(self):
        dummy = subject.Track(0, LANE, 0, NS, 0, 0, 0, ())
        references = tuple(subject.Track(i, LANE, 0, NS, 0, 0, 0, ()) for i in range(64))
        outputs = tuple(subject.Track(i, LANE, 0, NS, 0, 0, 0, ()) for i in range(64))
        pairs = subject.maximum_matching(references, outputs, lambda _a, _b: True,
                                         lambda _a, _b: 0.0)
        self.assertEqual(len(pairs), 64)
        self.assertEqual(len({a for a, _ in pairs}), 64)
        self.assertEqual(len({b for _, b in pairs}), 64)

    def test_duplicate_canonical_source_in_one_track_is_rejected(self):
        ro, rm, rp = make_side("ref", range(8))
        oo, om, op = make_side("out", range(8))
        duplicate_candidate = "out-duplicate"
        original = oo["out-0"]
        oo[duplicate_candidate] = subject.Observation(
            duplicate_candidate, "distinct-group", original.lane, original.start_ns,
            original.center_ns, original.end_ns, original.measured_cfo_hz)
        om[duplicate_candidate] = om["out-0"]
        duplicate = subject.Point(duplicate_candidate, "distinct-group", op[0].raw_cfo_hz,
                                  op[0].dealiased_cfo_hz, op[0].alias)
        reference = subject.Tracks(8, 8, "server", (track(0, rp, ro),))
        output_track = track(0, op + (duplicate,), oo)
        with self.assertRaisesRegex(ValueError, "duplicate canonical sources"):
            subject.compare(reference, subject.Tracks(9, 9, "curved", (output_track,)),
                            ro, oo, rm, om, self.settings)


if __name__ == "__main__":
    unittest.main()
