#!/usr/bin/env python3
import json
import math
import tempfile
import unittest
from pathlib import Path

import compare_tracks as subject


RF = 11_200_000_000.0
NS = 1_000_000_000


def observation(candidate, group, visit, begin, end, cfo=1000.0, receiver=0):
    return {
        "candidate": candidate, "group": group, "visit": visit, "receiver": receiver,
        "begin": begin, "end": end, "cfo": cfo,
    }


def write_observations(path, rows):
    lines = ["\t".join(subject.OBSERVATION_HEADER)]
    for row in rows:
        lines.append("\t".join(map(str, (
            row["candidate"], row["group"], row["receiver"], 1, "lower", RF,
            row["begin"], (row["begin"] + row["end"]) // 2, row["end"], row["cfo"],
            10.0, 1.0, 9.0,
        ))))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_sources(path, rows, side):
    lines = ["\t".join(subject.SOURCE_HEADER)]
    for rank, row in enumerate(rows):
        lines.append("\t".join(map(str, (
            row["candidate"], row["group"], row["visit"], row["receiver"], 0,
            rank, "fractional" if side == "server" else "integer", side,
        ))))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def track(index, begin, end, candidates, *, rate=100.0, intercept=2000.0, receiver=0):
    return {"index": index, "begin": begin, "end": end, "candidates": candidates,
            "rate": rate, "intercept": intercept, "receiver": receiver}


def write_tracks(path, rows, tracks):
    used_count = len({candidate for item in tracks for candidate in item["candidates"]})
    lines = [f"SUMMARY\t{len(rows)}\t{used_count}\t{len(tracks)}", "CONFIG\ttest-config"]
    by_candidate = {row["candidate"]: row for row in rows}
    for item in tracks:
        values = (
            "TRACK", item["index"], f"segment-{item['index']}", f"track-{item['index']}",
            item["receiver"], 1, "lower", RF, item["begin"], item["end"], item["begin"],
            item["rate"], item["intercept"], 1.0, 2.0, len(item["candidates"]),
            len(item["candidates"]),
        )
        lines.append("\t".join(map(str, values)))
        for candidate in item["candidates"]:
            row = by_candidate[candidate]
            raw = row["cfo"]
            lines.append("\t".join(map(str, (
                "POINT", item["index"], candidate, row["group"], 0, raw, raw,
            ))))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.settings = json.loads(Path(subject.__file__).with_name("thresholds.json").read_text())

    def tearDown(self):
        self.directory.cleanup()

    def load(self, prefix, observations, tracks, side):
        obs_path = self.root / f"{prefix}-observations.tsv"
        map_path = self.root / f"{prefix}-map.tsv"
        track_path = self.root / f"{prefix}-tracks.tsv"
        write_observations(obs_path, observations)
        write_sources(map_path, observations, side)
        write_tracks(track_path, observations, tracks)
        parsed_obs = subject.read_observations(obs_path)
        return (parsed_obs, subject.read_source_map(map_path, parsed_obs),
                subject.read_tracks(track_path, parsed_obs))

    def test_alias_aligned_curve_and_threshold_boundaries(self):
        lane = subject.Lane(0, 1, "lower", RF)
        left = subject.Track(0, "a", "a", lane, 0, 10 * NS, 0, 100.0, 2000.0, ())
        spacing = self.settings["alias_spacing_hz"]
        right = subject.Track(0, "b", "b", lane, 0, 10 * NS, 0, 350.0,
                              2000.0 + spacing, ())
        metrics = subject.pair_metrics(left, right, self.settings)
        self.assertEqual(metrics["curve_alias_shift"], 1)
        self.assertEqual(metrics["slope_difference_hz_per_s"], 250.0)
        self.assertAlmostEqual(metrics["maximum_alias_aligned_curve_difference_hz"], 2500.0)
        self.assertTrue(subject.eligible(metrics, self.settings["strict"]))

    def test_one_to_one_split_fragment_union_and_unsupported(self):
        ref_rows = []
        native_rows = []
        # One strict match with different candidate identities and ranks.
        for index in range(6):
            ref_rows.append(observation(f"r0-{index}", f"rg0-{index}", index, index * NS,
                                        index * NS + NS))
            native_rows.append(observation(f"n0-{index}", f"ng0-{index}", index, index * NS,
                                           index * NS + NS))
        # One reference interval represented by two relaxed-consistent fragments.
        for index in range(12):
            visit = 100 + index
            ref_rows.append(observation(f"r1-{index}", f"rg1-{index}", visit,
                                        (20 + index) * NS, (20 + index) * NS + NS))
            native_rows.append(observation(f"n1-{index}", f"ng1-{index}", visit,
                                           (20 + index) * NS, (20 + index) * NS + NS))
        # A reference track whose recording sources do not occur in native input.
        for index in range(6):
            ref_rows.append(observation(f"ru-{index}", f"rgu-{index}", 300 + index,
                                        (40 + index) * NS, (40 + index) * NS + NS))
        # A native extra in a different receiver lane.
        for index in range(6):
            native_rows.append(observation(f"ne-{index}", f"nge-{index}", 400 + index,
                                           (60 + index) * NS, (60 + index) * NS + NS,
                                           receiver=1))
        refs = [
            track(0, 0, 6 * NS, [f"r0-{i}" for i in range(6)]),
            track(1, 20 * NS, 32 * NS, [f"r1-{i}" for i in range(12)]),
            track(2, 40 * NS, 46 * NS, [f"ru-{i}" for i in range(6)]),
        ]
        natives = [
            track(0, 0, 6 * NS, [f"n0-{i}" for i in range(6)]),
            track(1, 20 * NS, 26 * NS, [f"n1-{i}" for i in range(6)]),
            track(2, 26 * NS, 32 * NS, [f"n1-{i}" for i in range(6, 12)]),
            track(3, 60 * NS, 66 * NS, [f"ne-{i}" for i in range(6)], receiver=1),
        ]
        robs, rmap, rtracks = self.load("reference", ref_rows, refs, "server")
        nobs, nmap, ntracks = self.load("native", native_rows, natives, "arm")
        report = subject.compare(rtracks, ntracks, robs, nobs, rmap, nmap, self.settings)
        self.assertEqual(report["strict"]["match_count"], 1)
        self.assertEqual(report["relaxed"]["match_count"], 2)
        self.assertEqual(report["relaxed"]["unsupported_reference_track_indexes"], [2])
        self.assertEqual(report["relaxed"]["extra_native_track_indexes"], [2, 3])
        self.assertEqual(report["relaxed"]["split_evidence"], [{
            "reference_track_index": 1, "eligible_native_track_indexes": [1, 2]}])
        self.assertEqual(report["fragment_union_coverage"][1][
            "reference_interval_union_coverage"], 1.0)
        matched = report["strict"]["matches"][0]["source_evidence"]
        self.assertEqual(matched["shared_canonical_source_count"], 6)
        self.assertEqual(matched["cfo_consistent_shared_source_count"], 6)

    def test_parser_rejects_nonfinite_and_source_authority_mismatch(self):
        row = observation("a", "g", 1, 0, NS)
        obs_path = self.root / "observations.tsv"
        write_observations(obs_path, [row])
        text = obs_path.read_text().replace("1000.0", "nan")
        obs_path.write_text(text)
        with self.assertRaisesRegex(ValueError, "non-finite measured_cfo_hz"):
            subject.read_observations(obs_path)

        write_observations(obs_path, [row])
        observations = subject.read_observations(obs_path)
        map_path = self.root / "map.tsv"
        write_sources(map_path, [row], "server")
        map_path.write_text(map_path.read_text().replace("\tg\t", "\twrong\t"))
        with self.assertRaisesRegex(ValueError, "authority mismatch"):
            subject.read_source_map(map_path, observations)

    def test_cross_track_boundary_reuse_and_polynomial_large_lane(self):
        rows = [observation(f"c-{i}", f"g-{i}", i, i * NS, (i + 1) * NS)
                for i in range(6)]
        observations, _, parsed = self.load(
            "reuse", rows,
            [track(0, 0, 6 * NS, [f"c-{i}" for i in range(6)]),
             track(1, 0, 6 * NS, [f"c-{i}" for i in range(6)])], "server")
        self.assertEqual(parsed.used_count, 6)
        self.assertEqual(sum(len(item.points) for item in parsed.tracks), 12)
        lane = subject.Lane(0, 1, "lower", RF)
        references = tuple(subject.Track(i, str(i), str(i), lane, 0, 10 * NS, 0,
                                                 100.0, 2000.0, ())
                           for i in range(32))
        natives = tuple(subject.Track(i, str(i), str(i), lane, 0, 10 * NS, 0,
                                              100.0, 2000.0, ())
                        for i in range(32))
        metrics = [[subject.pair_metrics(left, right, self.settings)
                    for right in natives] for left in references]
        pairs = subject.assignment(references, natives, metrics, self.settings["strict"])
        self.assertEqual(len(pairs), 32)
        self.assertEqual({left for left, _ in pairs}, set(range(32)))
        self.assertEqual({right for _, right in pairs}, set(range(32)))

    def test_relaxed_merge_evidence_is_not_extra_match(self):
        lane = subject.Lane(0, 1, "lower", RF)
        refs = tuple(subject.Track(i, str(i), str(i), lane, i * 5 * NS, (i + 1) * 5 * NS,
                                   0, 100.0, 2000.0, ()) for i in range(2))
        natives = (subject.Track(0, "n", "n", lane, 0, 10 * NS, 0, 100.0, 2000.0, ()),)
        report = subject.compare(subject.TrackFile(0, 0, "r", refs),
                                 subject.TrackFile(0, 0, "n", natives), {}, {}, {}, {},
                                 self.settings)
        self.assertEqual(report["relaxed"]["match_count"], 1)
        self.assertEqual(report["relaxed"]["merge_evidence"], [{
            "native_track_index": 0, "eligible_reference_track_indexes": [0, 1]}])

    def test_research_profile_missing_identity_is_explicit(self):
        rows = [observation(f"c-{i}", f"g-{i}", i, i * NS, (i + 1) * NS)
                for i in range(6)]
        obs_path = self.root / "observations.tsv"
        track_path = self.root / "tracks.tsv"
        write_observations(obs_path, rows)
        write_tracks(track_path, rows, [track(0, 0, 6 * NS, [f"c-{i}" for i in range(6)])])
        text = track_path.read_text().replace("CONFIG\ttest-config", "CONFIG\t")
        text = text.replace("\ttrack-0\t", "\t\t")
        track_path.write_text(text)
        observations = subject.read_observations(obs_path)
        parsed = subject.read_tracks(track_path, observations)
        report = subject.compare(parsed, parsed, observations, observations,
                                 {name: (i, 0, 0) for i, name in enumerate(observations)},
                                 {name: (i, 0, 0) for i, name in enumerate(observations)},
                                 self.settings)
        self.assertFalse(report["native"]["config_identity_available"])
        self.assertEqual(report["native"]["tracklet_identity_missing_count"], 1)


if __name__ == "__main__":
    unittest.main()
