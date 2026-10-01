#!/usr/bin/env python3
"""Membership-first comparison of nonlinear tracks to server track segments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

OBSERVATION_HEADER = [
    "candidate_id", "source_group_id", "receiver_id", "channel", "edge",
    "actual_rf_hz", "support_start_utc_ns", "support_center_utc_ns",
    "support_end_utc_ns", "measured_cfo_hz", "exact_score", "control_score", "margin",
]
SOURCE_HEADER = [
    "candidate_id", "source_group_id", "visit", "receiver_id", "probe_index",
    "candidate_rank", "epoch_kind", "detector_side",
]


def integer(text: str, name: str) -> int:
    if not text or (text[0] == "-" and not text[1:].isdigit()) or (
        text[0] != "-" and not text.isdigit()
    ):
        raise ValueError(f"invalid {name}")
    return int(text)


def finite(text: str, name: str) -> float:
    if not text or text != text.strip():
        raise ValueError(f"invalid {name}")
    try:
        value = float(text)
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error
    if not math.isfinite(value):
        raise ValueError(f"non-finite {name}")
    return value


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


@dataclass(frozen=True)
class Lane:
    receiver: int
    channel: int
    edge: str
    rf_hz: float


@dataclass(frozen=True)
class Observation:
    candidate: str
    source_group: str
    lane: Lane
    start_ns: int
    center_ns: int
    end_ns: int
    measured_cfo_hz: float


@dataclass(frozen=True)
class Point:
    candidate: str
    source_group: str
    raw_cfo_hz: float
    dealiased_cfo_hz: float
    alias: int


@dataclass(frozen=True)
class Track:
    index: int
    lane: Lane
    start_ns: int
    end_ns: int
    reference_ns: int
    rate_hz_per_s: float
    intercept_hz: float
    points: tuple[Point, ...]


@dataclass(frozen=True)
class Tracks:
    input_count: int
    used_count: int
    config: str
    values: tuple[Track, ...]


def read_observations(path: Path) -> dict[str, Observation]:
    output: dict[str, Observation] = {}
    with path.open(encoding="ascii", newline="") as source:
        rows = csv.reader(source, delimiter="\t")
        if next(rows, None) != OBSERVATION_HEADER:
            raise ValueError("unsupported observation header")
        for line, row in enumerate(rows, 2):
            if len(row) != 13 or not row[0] or not row[1] or row[4] not in ("lower", "upper"):
                raise ValueError(f"invalid observation line {line}")
            if row[0] in output:
                raise ValueError("duplicate observation candidate")
            lane = Lane(integer(row[2], "receiver"), integer(row[3], "channel"), row[4],
                        finite(row[5], "RF"))
            start, center, end = (integer(row[i], "support time") for i in (6, 7, 8))
            if not start <= center <= end or start == end:
                raise ValueError("invalid observation support")
            for index in (10, 11, 12):
                finite(row[index], "score")
            output[row[0]] = Observation(row[0], row[1], lane, start, center, end,
                                         finite(row[9], "measured CFO"))
    return output


def read_sources(path: Path, observations: dict[str, Observation]) -> dict[str, tuple[int, int, int]]:
    output: dict[str, tuple[int, int, int]] = {}
    with path.open(encoding="ascii", newline="") as source:
        rows = csv.reader(source, delimiter="\t")
        if next(rows, None) != SOURCE_HEADER:
            raise ValueError("unsupported source-map header")
        for line, row in enumerate(rows, 2):
            if len(row) != 8 or not row[0] or not row[1] or not row[6] or not row[7]:
                raise ValueError(f"invalid source-map line {line}")
            if row[0] not in observations or row[0] in output:
                raise ValueError("source-map candidate authority failure")
            visit, receiver, probe, rank = (integer(row[i], "source coordinate")
                                             for i in (2, 3, 4, 5))
            observation = observations[row[0]]
            if min(visit, receiver, probe, rank) < 0 or row[1] != observation.source_group or (
                receiver != observation.lane.receiver
            ):
                raise ValueError("source-map row disagrees with observation")
            output[row[0]] = (visit, receiver, probe)
    if output.keys() != observations.keys():
        raise ValueError("source map must cover every observation")
    return output


def read_tracks(path: Path, observations: dict[str, Observation]) -> Tracks:
    rows = [line.split("\t") for line in path.read_text(encoding="ascii").splitlines()]
    if len(rows) < 2 or len(rows[0]) != 4 or rows[0][0] != "SUMMARY":
        raise ValueError("track output must begin with SUMMARY")
    if len(rows[1]) != 2 or rows[1][0] != "CONFIG":
        raise ValueError("track output must contain CONFIG")
    input_count, used_count, track_count = (integer(rows[0][i], "SUMMARY") for i in (1, 2, 3))
    if input_count != len(observations) or not 0 <= used_count <= input_count:
        raise ValueError("SUMMARY disagrees with observations")
    pending: list[dict] = []
    for line, row in enumerate(rows[2:], 3):
        if row[0] == "TRACK":
            if len(row) != 17 or integer(row[1], "track index") != len(pending):
                raise ValueError(f"invalid TRACK line {line}")
            if row[6] not in ("lower", "upper"):
                raise ValueError("invalid track edge")
            lane = Lane(integer(row[4], "receiver"), integer(row[5], "channel"), row[6],
                        finite(row[7], "RF"))
            start, end, reference = (integer(row[i], "track time") for i in (8, 9, 10))
            if start >= end:
                raise ValueError("invalid track interval")
            numbers = [finite(row[i], "track numeric field") for i in range(11, 16)]
            pending.append({"track": Track(len(pending), lane, start, end, reference,
                                                   numbers[0], numbers[1], ()),
                            "count": integer(row[16], "point count"), "points": []})
        elif row[0] == "POINT":
            if len(row) != 7:
                raise ValueError(f"invalid POINT line {line}")
            index = integer(row[1], "point track index")
            if index != len(pending) - 1 or row[2] not in observations:
                raise ValueError("POINT does not follow its TRACK or candidate is unknown")
            observation = observations[row[2]]
            track = pending[index]["track"]
            if row[3] != observation.source_group or track.lane != observation.lane:
                raise ValueError("POINT authority disagrees with observation")
            point = Point(row[2], row[3], finite(row[5], "raw CFO"),
                          finite(row[6], "dealiased CFO"), integer(row[4], "alias"))
            scale = 11_200_000_000.0 / track.lane.rf_hz
            spacing = scale / 4.4e-6
            if not math.isclose(point.raw_cfo_hz, observation.measured_cfo_hz * scale,
                                rel_tol=2e-15, abs_tol=1e-7):
                raise ValueError("POINT raw CFO disagrees with observation")
            if not math.isclose(point.dealiased_cfo_hz, point.raw_cfo_hz - point.alias * spacing,
                                rel_tol=2e-15, abs_tol=1e-7):
                raise ValueError("POINT alias conversion is inconsistent")
            pending[index]["points"].append(point)
        else:
            raise ValueError(f"unsupported track row {row[0]}")
    if len(pending) != track_count:
        raise ValueError("track count mismatch")
    output = []
    for item in pending:
        old, points = item["track"], tuple(item["points"])
        if not points or len(points) != item["count"] or len({p.candidate for p in points}) != len(points):
            raise ValueError("point count or identity mismatch")
        source_groups = {point.source_group for point in points}
        if len(source_groups) != len(points):
            raise ValueError("track contains multiple candidates from one source group")
        point_observations = [observations[point.candidate] for point in points]
        if old.start_ns != min(point.start_ns for point in point_observations) or (
            old.end_ns != max(point.end_ns for point in point_observations)
        ):
            raise ValueError("track interval disagrees with points")
        output.append(Track(old.index, old.lane, old.start_ns, old.end_ns, old.reference_ns,
                            old.rate_hz_per_s, old.intercept_hz, points))
    return Tracks(input_count, used_count, rows[1][1], tuple(output))


def circular_distance(value: float, spacing: float) -> float:
    return abs(value - round(value / spacing) * spacing)


def union_duration(intervals: list[tuple[int, int]]) -> int:
    intervals = sorted((a, b) for a, b in intervals if a < b)
    if not intervals:
        return 0
    total, begin, end = 0, *intervals[0]
    for next_begin, next_end in intervals[1:]:
        if next_begin > end:
            total += end - begin
            begin, end = next_begin, next_end
        else:
            end = max(end, next_end)
    return total + end - begin


def membership_metrics(reference: Track, output: Track,
                       reference_observations: dict[str, Observation],
                       output_observations: dict[str, Observation],
                       reference_sources: dict[str, tuple[int, int, int]],
                       output_sources: dict[str, tuple[int, int, int]], settings: dict) -> dict:
    same_lane = reference.lane == output.lane
    reference_by_source = {reference_sources[p.candidate]: p for p in reference.points}
    output_by_source = {output_sources[p.candidate]: p for p in output.points}
    spacing = settings["alias_spacing_hz"] * settings["canonical_rf_hz"] / reference.lane.rf_hz
    shared = reference_by_source.keys() & output_by_source.keys()
    consistent = {source for source in shared if circular_distance(
        output_by_source[source].raw_cfo_hz - reference_by_source[source].raw_cfo_hz,
        spacing) <= settings["same_source_circular_cfo_gate_hz"]}
    in_span_output = {source for source, point in output_by_source.items()
                      if reference.start_ns <= output_observations[point.candidate].center_ns <=
                      reference.end_ns}
    consistent_in_span = consistent & in_span_output
    intervals = []
    for source in consistent:
        observation = reference_observations[reference_by_source[source].candidate]
        intervals.append((max(reference.start_ns, observation.start_ns),
                          min(reference.end_ns, observation.end_ns)))
    duration = reference.end_ns - reference.start_ns
    centers = sorted(reference_observations[reference_by_source[source].candidate].center_ns
                     for source in consistent)
    return {
        "same_lane": same_lane,
        "reference_source_count": len(reference_by_source),
        "output_source_count": len(output_by_source),
        "shared_source_count": len(shared),
        "consistent_source_count": len(consistent),
        "reference_source_coverage": len(consistent) / len(reference_by_source),
        "in_span_output_count": len(in_span_output),
        "in_span_consistent_count": len(consistent_in_span),
        "in_span_output_purity": (len(consistent_in_span) / len(in_span_output)
                                  if in_span_output else 0.0),
        "overall_output_purity": len(consistent) / len(output_by_source),
        "reference_interval_union_time_coverage": union_duration(intervals) / duration,
        "consistent_source_center_span_fraction": ((centers[-1] - centers[0]) / duration
                                                   if len(centers) > 1 else 0.0),
        "consistent_sources": sorted(f"{a}:{b}:{c}" for a, b, c in consistent),
    }


def complete(metrics: dict, settings: dict) -> bool:
    return (metrics["same_lane"] and
            metrics["reference_source_coverage"] >= settings["minimum_reference_source_coverage"] and
            metrics["in_span_output_purity"] >= settings["minimum_in_span_output_purity"])


def maximum_matching(reference: tuple[Track, ...], outputs: tuple[Track, ...],
                     allowed: Callable[[int, int], bool], cost: Callable[[int, int], float]) -> list[tuple[int, int]]:
    result = []
    lanes = sorted({x.lane for x in reference} | {x.lane for x in outputs},
                   key=lambda x: (x.receiver, x.channel, x.edge, x.rf_hz))
    for lane in lanes:
        refs = [i for i, value in enumerate(reference) if value.lane == lane]
        outs = [i for i, value in enumerate(outputs) if value.lane == lane]
        edges = [[local for local, output_index in enumerate(outs)
                  if allowed(reference_index, output_index)] for reference_index in refs]
        for local, reference_index in enumerate(refs):
            edges[local].sort(key=lambda output_local: (cost(reference_index, outs[output_local]),
                                                        outs[output_local]))
        matched = [-1] * len(outs)

        def augment(ref_local: int, seen: list[bool]) -> bool:
            for out_local in edges[ref_local]:
                if seen[out_local]:
                    continue
                seen[out_local] = True
                if matched[out_local] < 0 or augment(matched[out_local], seen):
                    matched[out_local] = ref_local
                    return True
            return False

        for ref_local in sorted(range(len(refs)), key=lambda i: (len(edges[i]), refs[i])):
            augment(ref_local, [False] * len(outs))
        result.extend((refs[ref_local], outs[out_local])
                      for out_local, ref_local in enumerate(matched) if ref_local >= 0)
    return sorted(result)


def linear_metrics(reference: Track, output: Track, settings: dict) -> dict:
    overlap = max(0, min(reference.end_ns, output.end_ns) - max(reference.start_ns, output.start_ns))
    left, right = reference.end_ns - reference.start_ns, output.end_ns - output.start_ns
    jaccard = overlap / (left + right - overlap)
    shorter = overlap / min(left, right)
    if not overlap:
        curve = math.inf
    else:
        begin, end = max(reference.start_ns, output.start_ns), min(reference.end_ns, output.end_ns)
        middle = begin + (end - begin) // 2
        spacing = settings["alias_spacing_hz"] * settings["canonical_rf_hz"] / reference.lane.rf_hz
        def value(track: Track, when: int) -> float:
            return track.intercept_hz + track.rate_hz_per_s * ((when - track.reference_ns) / 1e9)
        alias = round((value(output, middle) - value(reference, middle)) / spacing)
        curve = max(abs(value(output, when) - value(reference, when) - alias * spacing)
                    for when in (begin, middle, end))
    return {"same_lane": reference.lane == output.lane, "interval_jaccard": jaccard,
            "shorter_interval_coverage": shorter,
            "slope_difference_hz_per_s": abs(reference.rate_hz_per_s - output.rate_hz_per_s),
            "maximum_alias_aligned_curve_difference_hz": curve}


def linear_allowed(metrics: dict, limits: dict) -> bool:
    return (metrics["same_lane"] and
            metrics["interval_jaccard"] >= limits["minimum_interval_jaccard"] and
            metrics["shorter_interval_coverage"] >= limits["minimum_shorter_interval_coverage"] and
            metrics["slope_difference_hz_per_s"] <= limits["maximum_slope_difference_hz_per_s"] and
            metrics["maximum_alias_aligned_curve_difference_hz"] <=
            limits["maximum_alias_aligned_curve_difference_hz"])


def compare(reference: Tracks, outputs: Tracks,
            reference_observations: dict[str, Observation], output_observations: dict[str, Observation],
            reference_sources: dict[str, tuple[int, int, int]],
            output_sources: dict[str, tuple[int, int, int]], settings: dict) -> dict:
    refs, outs = reference.values, outputs.values
    for name, tracks, sources in (("reference", refs, reference_sources),
                                  ("output", outs, output_sources)):
        for track in tracks:
            identities = [sources[point.candidate] for point in track.points]
            if len(set(identities)) != len(identities):
                raise ValueError(f"{name} track contains duplicate canonical sources")
    metrics = [[membership_metrics(r, o, reference_observations, output_observations,
                                   reference_sources, output_sources, settings) for o in outs] for r in refs]
    matches = maximum_matching(refs, outs, lambda a, b: complete(metrics[a][b], settings),
                               lambda a, b: 2.0 - metrics[a][b]["reference_source_coverage"] -
                               metrics[a][b]["in_span_output_purity"])
    matched_refs, matched_outs = {a for a, _ in matches}, {b for _, b in matches}
    eligible_by_ref = [[b for b in range(len(outs)) if complete(metrics[a][b], settings)]
                       for a in range(len(refs))]
    eligible_by_out = [[a for a in range(len(refs)) if complete(metrics[a][b], settings)]
                       for b in range(len(outs))]
    available: dict[Lane, set[tuple[int, int, int]]] = {}
    input_by_source: dict[tuple[Lane, tuple[int, int, int]], list[Observation]] = {}
    for candidate, observation in output_observations.items():
        available.setdefault(observation.lane, set()).add(output_sources[candidate])
        input_by_source.setdefault((observation.lane, output_sources[candidate]), []).append(observation)
    support = []
    union_rows = []
    for a, ref in enumerate(refs):
        ref_sources_set = {reference_sources[p.candidate] for p in ref.points}
        available_count = len(ref_sources_set & available.get(ref.lane, set()))
        spacing = settings["alias_spacing_hz"] * settings["canonical_rf_hz"] / ref.lane.rf_hz
        reference_by_source = {reference_sources[p.candidate]: p for p in ref.points}
        ceiling_sources = set()
        for source, point in reference_by_source.items():
            if any(circular_distance(observation.measured_cfo_hz *
                                     settings["canonical_rf_hz"] / ref.lane.rf_hz -
                                     point.raw_cfo_hz, spacing) <=
                   settings["same_source_circular_cfo_gate_hz"]
                   for observation in input_by_source.get((ref.lane, source), [])):
                ceiling_sources.add(source)
        ceiling_coverage = len(ceiling_sources) / len(ref_sources_set)
        support.append({"reference_track_index": ref.index,
                        "input_available_source_coverage": available_count / len(ref_sources_set),
                        "input_available_source_count": available_count,
                        "cfo_consistent_input_ceiling_count": len(ceiling_sources),
                        "cfo_consistent_input_ceiling_coverage": ceiling_coverage,
                        "data_limited_for_primary_coverage": ceiling_coverage <
                        settings["minimum_reference_source_coverage"]})
        consistent_union = set()
        intervals = []
        fragments = []
        for b, out in enumerate(outs):
            item = metrics[a][b]
            if not item["same_lane"] or not item["consistent_source_count"]:
                continue
            fragments.append(out.index)
            values = {tuple(map(int, text.split(":"))) for text in item["consistent_sources"]}
            consistent_union |= values
        for point in ref.points:
            if reference_sources[point.candidate] in consistent_union:
                observation = reference_observations[point.candidate]
                intervals.append((max(ref.start_ns, observation.start_ns),
                                  min(ref.end_ns, observation.end_ns)))
        centers = sorted(reference_observations[point.candidate].center_ns for point in ref.points
                         if reference_sources[point.candidate] in consistent_union)
        union_rows.append({"reference_track_index": ref.index,
                           "consistent_fragment_output_indexes": fragments,
                           "union_reference_source_coverage": len(consistent_union & ref_sources_set) /
                           len(ref_sources_set),
                           "union_reference_support_interval_occupancy": union_duration(intervals) /
                           (ref.end_ns - ref.start_ns),
                           "union_consistent_source_center_span_fraction":
                           ((centers[-1] - centers[0]) / (ref.end_ns - ref.start_ns)
                            if len(centers) > 1 else 0.0)})
    primary_matches = []
    for a, b in matches:
        row = dict(metrics[a][b])
        row.update(reference_track_index=refs[a].index, output_track_index=outs[b].index)
        primary_matches.append(row)

    linear = [[linear_metrics(r, o, settings) for o in outs] for r in refs]
    linear_report = {}
    for name, limits in settings["legacy_linear_diagnostic"].items():
        pairs = maximum_matching(refs, outs, lambda a, b, lim=limits: linear_allowed(linear[a][b], lim),
                                 lambda a, b: 2.0 - linear[a][b]["interval_jaccard"] -
                                 linear[a][b]["shorter_interval_coverage"])
        linear_report[name] = {"match_count": len(pairs),
                               "pairs": [{"reference_track_index": refs[a].index,
                                          "output_track_index": outs[b].index} for a, b in pairs]}
    eligible_reference_indexes = sorted({a for a, values in enumerate(eligible_by_ref) if values})
    merge_displaced = sorted(set(eligible_reference_indexes) - matched_refs)
    supported_no_complete = sorted(a for a in range(len(refs)) if a not in matched_refs and
        not eligible_by_ref[a] and support[a]["cfo_consistent_input_ceiling_coverage"] >=
        settings["minimum_reference_source_coverage"])
    return {
        "schema": "leo-arm-curvature-track-membership-comparison/v1",
        "scope": "Comparison proxy against maintained server segmentation; no physical identity labels.",
        "thresholds": {key: settings[key] for key in (
            "same_source_circular_cfo_gate_hz", "minimum_reference_source_coverage",
            "minimum_in_span_output_purity")},
        "reference": {"input_observations": reference.input_count,
                      "used_observations": reference.used_count, "tracks": len(refs),
                      "config": reference.config},
        "output": {"input_observations": outputs.input_count,
                   "used_observations": outputs.used_count, "tracks": len(outs),
                   "config": outputs.config},
        "primary": {
            "complete_one_to_one_count": len(matches),
            "reference_segments_with_any_complete_output_count": len(eligible_reference_indexes),
            "reference_segments_with_any_complete_output_indexes":
            [refs[a].index for a in eligible_reference_indexes],
            "one_to_one_unmatched_but_complete_merge_indexes":
            [refs[a].index for a in merge_displaced],
            "supported_without_complete_output_indexes":
            [refs[a].index for a in supported_no_complete],
            "matches": primary_matches,
            "supported_unmatched_reference_indexes": [refs[a].index for a in range(len(refs))
                if a not in matched_refs and support[a]["cfo_consistent_input_ceiling_coverage"] >=
                settings["minimum_reference_source_coverage"]],
            "input_unsupported_reference_indexes": [refs[a].index for a in range(len(refs))
                if a not in matched_refs and support[a]["cfo_consistent_input_ceiling_coverage"] <
                settings["minimum_reference_source_coverage"]],
            "unmatched_output_indexes": [outs[b].index for b in range(len(outs)) if b not in matched_outs],
            "split_evidence": [{"reference_track_index": refs[a].index,
                                "eligible_output_indexes": [outs[b].index for b in values]}
                               for a, values in enumerate(eligible_by_ref) if len(values) > 1],
            "merge_evidence": [{"output_track_index": outs[b].index,
                                "eligible_reference_indexes": [refs[a].index for a in values]}
                               for b, values in enumerate(eligible_by_out) if len(values) > 1],
        },
        "reference_input_support": support,
        "fragment_union_coverage": union_rows,
        "secondary_legacy_linear_diagnostic": linear_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-observations", type=Path, required=True)
    parser.add_argument("--reference-tracks", type=Path, required=True)
    parser.add_argument("--reference-source-map", type=Path, required=True)
    parser.add_argument("--output-observations", type=Path, required=True)
    parser.add_argument("--output-tracks", type=Path, required=True)
    parser.add_argument("--output-source-map", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, default=Path(__file__).with_name("thresholds.json"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit("refusing to overwrite report")
    settings = json.loads(args.thresholds.read_text(encoding="utf-8"))
    reference_observations = read_observations(args.reference_observations)
    output_observations = read_observations(args.output_observations)
    reference_sources = read_sources(args.reference_source_map, reference_observations)
    output_sources = read_sources(args.output_source_map, output_observations)
    reference = read_tracks(args.reference_tracks, reference_observations)
    outputs = read_tracks(args.output_tracks, output_observations)
    report = compare(reference, outputs, reference_observations, output_observations,
                     reference_sources, output_sources, settings)
    report["inputs"] = {name: {"path": str(path), "sha256": digest(path)} for name, path in (
        ("reference_observations", args.reference_observations),
        ("reference_tracks", args.reference_tracks),
        ("reference_source_map", args.reference_source_map),
        ("output_observations", args.output_observations),
        ("output_tracks", args.output_tracks), ("output_source_map", args.output_source_map),
        ("thresholds", args.thresholds))}
    temporary = args.report.with_name(args.report.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
