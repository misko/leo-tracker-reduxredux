#!/usr/bin/env python3
"""Compare two native tracking TSV results without relying on result identities."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

OBSERVATION_HEADER = [
    "candidate_id", "source_group_id", "receiver_id", "channel", "edge",
    "actual_rf_hz", "support_start_utc_ns", "support_center_utc_ns",
    "support_end_utc_ns", "measured_cfo_hz", "exact_score", "control_score",
    "margin",
]
SOURCE_HEADER = [
    "candidate_id", "source_group_id", "visit", "receiver_id", "probe_index",
    "candidate_rank", "epoch_kind", "detector_side",
]


def fail(message: str) -> ValueError:
    return ValueError(message)


def parse_int(text: str, name: str) -> int:
    if not text or (text[0] == "-" and not text[1:].isdigit()) or (
        text[0] != "-" and not text.isdigit()
    ):
        raise fail(f"invalid {name}")
    return int(text)


def parse_float(text: str, name: str) -> float:
    if not text or text != text.strip():
        raise fail(f"invalid {name}")
    try:
        value = float(text)
    except ValueError as error:
        raise fail(f"invalid {name}") from error
    if not math.isfinite(value):
        raise fail(f"non-finite {name}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class Lane:
    receiver_id: int
    channel: int
    edge: str
    actual_rf_hz: float


@dataclass(frozen=True)
class Observation:
    candidate_id: str
    source_group_id: str
    lane: Lane
    start_ns: int
    center_ns: int
    end_ns: int
    measured_cfo_hz: float


@dataclass(frozen=True)
class Point:
    candidate_id: str
    source_group_id: str
    relative_alias_index: int
    normalized_raw_cfo_hz: float
    normalized_dealiased_cfo_hz: float


@dataclass(frozen=True)
class Track:
    index: int
    segment_id: str
    tracklet_id: str
    lane: Lane
    start_ns: int
    end_ns: int
    reference_ns: int
    rate: float
    intercept: float
    points: tuple[Point, ...]


@dataclass(frozen=True)
class TrackFile:
    input_count: int
    used_count: int
    config_digest: str
    tracks: tuple[Track, ...]


def read_observations(path: Path) -> dict[str, Observation]:
    result: dict[str, Observation] = {}
    with path.open(newline="", encoding="ascii") as source:
        rows = csv.reader(source, delimiter="\t")
        try:
            header = next(rows)
        except StopIteration as error:
            raise fail("empty observation TSV") from error
        if header != OBSERVATION_HEADER:
            raise fail("unsupported observation header")
        for number, row in enumerate(rows, 2):
            if len(row) != 13:
                raise fail(f"observation line {number} must contain 13 fields")
            if not row[0] or not row[1] or row[4] not in ("lower", "upper"):
                raise fail(f"invalid observation identity on line {number}")
            candidate = row[0]
            if candidate in result:
                raise fail(f"duplicate observation candidate_id {candidate}")
            lane = Lane(parse_int(row[2], "receiver_id"), parse_int(row[3], "channel"),
                        row[4], parse_float(row[5], "actual_rf_hz"))
            start = parse_int(row[6], "support_start_utc_ns")
            center = parse_int(row[7], "support_center_utc_ns")
            end = parse_int(row[8], "support_end_utc_ns")
            if not start <= center <= end or start == end:
                raise fail(f"invalid observation support on line {number}")
            result[candidate] = Observation(candidate, row[1], lane, start, center, end,
                                            parse_float(row[9], "measured_cfo_hz"))
            for index, name in ((10, "exact_score"), (11, "control_score"), (12, "margin")):
                parse_float(row[index], name)
    return result


def read_source_map(path: Path, observations: dict[str, Observation]) -> dict[str, tuple[int, int, int]]:
    result: dict[str, tuple[int, int, int]] = {}
    with path.open(newline="", encoding="ascii") as source:
        rows = csv.reader(source, delimiter="\t")
        try:
            header = next(rows)
        except StopIteration as error:
            raise fail("empty source map") from error
        if header != SOURCE_HEADER:
            raise fail("unsupported source-map header")
        for number, row in enumerate(rows, 2):
            if len(row) != 8 or not row[0] or not row[1] or not row[6] or not row[7]:
                raise fail(f"invalid source-map line {number}")
            if row[0] not in observations:
                raise fail(f"source map references unknown candidate {row[0]}")
            if row[0] in result:
                raise fail(f"duplicate source-map candidate {row[0]}")
            observation = observations[row[0]]
            receiver = parse_int(row[3], "source receiver_id")
            if row[1] != observation.source_group_id or receiver != observation.lane.receiver_id:
                raise fail(f"source-map authority mismatch on line {number}")
            visit = parse_int(row[2], "source visit")
            probe = parse_int(row[4], "source probe_index")
            rank = parse_int(row[5], "source candidate_rank")
            if visit < 0 or receiver < 0 or probe < 0 or rank < 0:
                raise fail(f"negative source-map coordinate on line {number}")
            result[row[0]] = (visit, receiver, probe)
    missing = observations.keys() - result.keys()
    if missing:
        raise fail(f"source map omits {len(missing)} observations")
    return result


def read_tracks(path: Path, observations: dict[str, Observation]) -> TrackFile:
    lines = [line.rstrip("\n").split("\t") for line in path.read_text(encoding="ascii").splitlines()]
    if len(lines) < 2 or len(lines[0]) != 4 or lines[0][0] != "SUMMARY":
        raise fail("track output must begin with SUMMARY")
    if len(lines[1]) != 2 or lines[1][0] != "CONFIG":
        raise fail("track output must contain CONFIG after SUMMARY")
    input_count = parse_int(lines[0][1], "input_candidate_count")
    used_count = parse_int(lines[0][2], "used_candidate_count")
    expected_tracks = parse_int(lines[0][3], "track_count")
    if input_count != len(observations) or not 0 <= used_count <= input_count:
        raise fail("track SUMMARY does not agree with observations")
    mutable: list[dict] = []
    for number, fields in enumerate(lines[2:], 3):
        if not fields or fields == [""]:
            raise fail(f"blank track line {number}")
        if fields[0] == "TRACK":
            if len(fields) != 17:
                raise fail(f"TRACK line {number} must contain 17 fields")
            index = parse_int(fields[1], "track_index")
            if index != len(mutable):
                raise fail("TRACK indexes must be contiguous")
            edge = fields[6]
            if edge not in ("lower", "upper"):
                raise fail("invalid TRACK edge")
            start = parse_int(fields[8], "start_utc_ns")
            end = parse_int(fields[9], "end_utc_ns")
            reference = parse_int(fields[10], "reference_utc_ns")
            if start >= end:
                raise fail("invalid TRACK support interval")
            numerical = [parse_float(fields[i], f"TRACK field {i}") for i in range(11, 16)]
            point_count = parse_int(fields[16], "point_count")
            mutable.append({
                "track": Track(index, fields[2], fields[3],
                               Lane(parse_int(fields[4], "receiver_id"),
                                    parse_int(fields[5], "channel"), edge,
                                    parse_float(fields[7], "actual_rf_hz")),
                               start, end, reference, numerical[0], numerical[1], ()),
                "expected": point_count,
                "points": [],
            })
        elif fields[0] == "POINT":
            if len(fields) != 7:
                raise fail(f"POINT line {number} must contain 7 fields")
            index = parse_int(fields[1], "point track_index")
            if index >= len(mutable) or index != len(mutable) - 1:
                raise fail("POINT must follow its TRACK")
            candidate = fields[2]
            if candidate not in observations:
                raise fail(f"POINT references unknown candidate {candidate}")
            observation = observations[candidate]
            track = mutable[index]["track"]
            if fields[3] != observation.source_group_id or observation.lane != track.lane:
                raise fail("POINT authority does not agree with observation")
            mutable[index]["points"].append(Point(
                candidate, fields[3], parse_int(fields[4], "relative_alias_index"),
                parse_float(fields[5], "normalized_raw_cfo_hz"),
                parse_float(fields[6], "normalized_dealiased_cfo_hz")))
        else:
            raise fail(f"unsupported track row {fields[0]}")
    if len(mutable) != expected_tracks:
        raise fail("SUMMARY track count mismatch")
    tracks: list[Track] = []
    for item in mutable:
        if len(item["points"]) != item["expected"] or not item["points"]:
            raise fail("TRACK point count mismatch")
        if len({point.candidate_id for point in item["points"]}) != len(item["points"]):
            raise fail("duplicate POINT candidate")
        old = item["track"]
        for point in item["points"]:
            observation = observations[point.candidate_id]
            scale = 11_200_000_000.0 / old.lane.actual_rf_hz
            spacing = (1.0 / 4.4e-6) * scale
            expected_raw = observation.measured_cfo_hz * scale
            expected_dealiased = point.normalized_raw_cfo_hz - point.relative_alias_index * spacing
            if not math.isclose(point.normalized_raw_cfo_hz, expected_raw,
                                rel_tol=2e-15, abs_tol=1e-7):
                raise fail("POINT normalized raw CFO disagrees with observation")
            if not math.isclose(point.normalized_dealiased_cfo_hz, expected_dealiased,
                                rel_tol=2e-15, abs_tol=1e-7):
                raise fail("POINT alias conversion is inconsistent")
        point_observations = [observations[point.candidate_id] for point in item["points"]]
        if (old.start_ns != min(point.start_ns for point in point_observations) or
                old.end_ns != max(point.end_ns for point in point_observations)):
            raise fail("TRACK interval disagrees with POINT observations")
        tracks.append(Track(old.index, old.segment_id, old.tracklet_id, old.lane,
                            old.start_ns, old.end_ns, old.reference_ns, old.rate,
                            old.intercept, tuple(item["points"])))
    return TrackFile(input_count, used_count, lines[1][1], tuple(tracks))


def interval_metrics(left: Track, right: Track) -> tuple[float, float, int]:
    overlap = max(0, min(left.end_ns, right.end_ns) - max(left.start_ns, right.start_ns))
    left_duration = left.end_ns - left.start_ns
    right_duration = right.end_ns - right.start_ns
    union = left_duration + right_duration - overlap
    return overlap / union, overlap / min(left_duration, right_duration), overlap


def curve_metrics(reference: Track, native: Track, alias_spacing_hz: float,
                  canonical_rf_hz: float) -> tuple[float, float, int]:
    begin = max(reference.start_ns, native.start_ns)
    end = min(reference.end_ns, native.end_ns)
    if begin >= end:
        return math.inf, abs(reference.rate - native.rate), 0
    middle = begin + (end - begin) // 2
    spacing = alias_spacing_hz * canonical_rf_hz / reference.lane.actual_rf_hz

    def value(track: Track, when: int) -> float:
        return track.intercept + track.rate * ((when - track.reference_ns) / 1e9)

    middle_delta = value(native, middle) - value(reference, middle)
    alias = round(middle_delta / spacing)
    differences = [abs(value(native, when) - value(reference, when) - alias * spacing)
                   for when in (begin, middle, end)]
    return max(differences), abs(reference.rate - native.rate), alias


def pair_metrics(reference: Track, native: Track, settings: dict) -> dict:
    same_lane = reference.lane == native.lane
    jaccard, shorter, overlap_ns = interval_metrics(reference, native)
    curve, slope, alias = curve_metrics(reference, native, settings["alias_spacing_hz"],
                                         settings["canonical_rf_hz"])
    return {
        "same_lane": same_lane,
        "interval_jaccard": jaccard,
        "shorter_interval_coverage": shorter,
        "overlap_ns": overlap_ns,
        "slope_difference_hz_per_s": slope,
        "maximum_alias_aligned_curve_difference_hz": curve,
        "curve_alias_shift": alias,
    }


def eligible(metrics: dict, limits: dict, *, fragments: bool = False) -> bool:
    if not metrics["same_lane"] or metrics["overlap_ns"] <= 0:
        return False
    if metrics["slope_difference_hz_per_s"] > limits["maximum_slope_difference_hz_per_s"]:
        return False
    if metrics["maximum_alias_aligned_curve_difference_hz"] > limits[
        "maximum_alias_aligned_curve_difference_hz"
    ]:
        return False
    return fragments or (
        metrics["interval_jaccard"] >= limits["minimum_interval_jaccard"]
        and metrics["shorter_interval_coverage"] >= limits["minimum_shorter_interval_coverage"]
    )


def assignment(reference: tuple[Track, ...], native: tuple[Track, ...], metrics: list[list[dict]],
               limits: dict) -> list[tuple[int, int]]:
    # Cost-ordered augmenting paths provide deterministic maximum cardinality
    # without floating residual cycles on duplicate/tied hypotheses.
    lanes = sorted({track.lane for track in reference} | {track.lane for track in native},
                   key=lambda lane: (lane.receiver_id, lane.channel, lane.edge, lane.actual_rf_hz))
    output: list[tuple[int, int]] = []
    for lane in lanes:
        reference_indexes = [index for index, track in enumerate(reference) if track.lane == lane]
        native_indexes = [index for index, track in enumerate(native) if track.lane == lane]
        adjacency: list[list[tuple[float, int]]] = [[] for _ in reference_indexes]
        for local_reference, reference_index in enumerate(reference_indexes):
            for local_native, native_index in enumerate(native_indexes):
                item = metrics[reference_index][native_index]
                if not eligible(item, limits):
                    continue
                cost = ((1.0 - item["interval_jaccard"])
                        + (1.0 - item["shorter_interval_coverage"])
                        + item["slope_difference_hz_per_s"] /
                        limits["maximum_slope_difference_hz_per_s"]
                        + item["maximum_alias_aligned_curve_difference_hz"] /
                        limits["maximum_alias_aligned_curve_difference_hz"])
                adjacency[local_reference].append((cost, local_native))
            adjacency[local_reference].sort(
                key=lambda item: (item[0], native_indexes[item[1]]))
        matched_native = [-1] * len(native_indexes)

        def augment(local_reference: int, seen: list[bool]) -> bool:
            for _, local_native in adjacency[local_reference]:
                if seen[local_native]:
                    continue
                seen[local_native] = True
                previous = matched_native[local_native]
                if previous < 0 or augment(previous, seen):
                    matched_native[local_native] = local_reference
                    return True
            return False

        order = sorted(range(len(reference_indexes)),
                       key=lambda local: (len(adjacency[local]), reference_indexes[local]))
        for local_reference in order:
            augment(local_reference, [False] * len(native_indexes))
        for local_native, local_reference in enumerate(matched_native):
            if local_reference >= 0:
                output.append((reference_indexes[local_reference], native_indexes[local_native]))
    return sorted(output)


def merged_intervals(intervals: Iterable[tuple[int, int]]) -> int:
    ordered = sorted((a, b) for a, b in intervals if a < b)
    if not ordered:
        return 0
    total = 0
    begin, end = ordered[0]
    for next_begin, next_end in ordered[1:]:
        if next_begin > end:
            total += end - begin
            begin, end = next_begin, next_end
        else:
            end = max(end, next_end)
    return total + end - begin


def circular_distance(value: float, spacing: float) -> float:
    return abs(value - round(value / spacing) * spacing)


def source_text(source: tuple[int, int, int]) -> str:
    return f"{source[0]}:{source[1]}:{source[2]}"


def evidence(reference: Track, native: Track, ref_sources: dict[str, tuple[int, int, int]],
             native_sources: dict[str, tuple[int, int, int]], settings: dict) -> dict:
    native_by_source = {native_sources[p.candidate_id]: p for p in native.points}
    spacing = settings["alias_spacing_hz"] * settings["canonical_rf_hz"] / reference.lane.actual_rf_hz
    shared = []
    consistent = []
    for point in reference.points:
        source = ref_sources[point.candidate_id]
        other = native_by_source.get(source)
        if other is None:
            continue
        shared.append(source)
        if circular_distance(other.normalized_raw_cfo_hz - point.normalized_raw_cfo_hz,
                             spacing) <= settings["source_evidence_circular_cfo_gate_hz"]:
            consistent.append(source)
    return {
        "shared_canonical_source_count": len(set(shared)),
        "cfo_consistent_shared_source_count": len(set(consistent)),
        "shared_canonical_sources": [source_text(value) for value in sorted(set(shared))],
        "cfo_consistent_shared_sources": [source_text(value) for value in sorted(set(consistent))],
    }


def compare(ref_file: TrackFile, native_file: TrackFile,
            ref_observations: dict[str, Observation], native_observations: dict[str, Observation],
            ref_sources: dict[str, tuple[int, int, int]],
            native_sources: dict[str, tuple[int, int, int]], settings: dict) -> dict:
    refs, natives = ref_file.tracks, native_file.tracks
    metrics = [[pair_metrics(ref, native, settings) for native in natives] for ref in refs]
    native_available: dict[Lane, set[str]] = {}
    for candidate, observation in native_observations.items():
        native_available.setdefault(observation.lane, set()).add(native_sources[candidate])
    reference_support = []
    for ref in refs:
        sources = {ref_sources[p.candidate_id] for p in ref.points}
        represented = sources & native_available.get(ref.lane, set())
        reference_support.append({
            "reference_track_index": ref.index,
            "reference_source_count": len(sources),
            "native_available_source_count": len(represented),
            "supported": len(represented) >= settings["minimum_tracking_support"],
        })

    modes = {}
    for name in ("strict", "relaxed"):
        pairs = assignment(refs, natives, metrics, settings[name])
        matched_refs = {a for a, _ in pairs}
        matched_native = {b for _, b in pairs}
        edges_by_ref = [[b for b in range(len(natives)) if eligible(metrics[a][b], settings[name])]
                        for a in range(len(refs))]
        edges_by_native = [[a for a in range(len(refs)) if eligible(metrics[a][b], settings[name])]
                           for b in range(len(natives))]
        matches = []
        for a, b in pairs:
            item = dict(metrics[a][b])
            item.update({"reference_track_index": refs[a].index,
                         "native_track_index": natives[b].index,
                         "source_evidence": evidence(refs[a], natives[b], ref_sources,
                                                     native_sources, settings)})
            matches.append(item)
        modes[name] = {
            "match_count": len(matches),
            "matches": matches,
            "unmatched_supported_reference_track_indexes": [
                refs[a].index for a in range(len(refs))
                if a not in matched_refs and reference_support[a]["supported"]],
            "unsupported_reference_track_indexes": [
                refs[a].index for a in range(len(refs))
                if a not in matched_refs and not reference_support[a]["supported"]],
            "extra_native_track_indexes": [natives[b].index for b in range(len(natives))
                                             if b not in matched_native],
            "split_evidence": [{"reference_track_index": refs[a].index,
                                 "eligible_native_track_indexes": [natives[b].index for b in edges]}
                                for a, edges in enumerate(edges_by_ref) if len(edges) > 1],
            "merge_evidence": [{"native_track_index": natives[b].index,
                                 "eligible_reference_track_indexes": [refs[a].index for a in edges]}
                                for b, edges in enumerate(edges_by_native) if len(edges) > 1],
        }

    fragment_coverage = []
    for a, ref in enumerate(refs):
        indexes = [b for b in range(len(natives))
                   if eligible(metrics[a][b], settings["relaxed"], fragments=True)]
        intervals = [(max(ref.start_ns, natives[b].start_ns), min(ref.end_ns, natives[b].end_ns))
                     for b in indexes]
        covered = merged_intervals(intervals)
        fragment_coverage.append({
            "reference_track_index": ref.index,
            "consistent_native_fragment_indexes": [natives[b].index for b in indexes],
            "reference_interval_union_coverage": covered / (ref.end_ns - ref.start_ns),
            "covered_ns": covered,
        })
    return {
        "schema": "leo-arm-fast-track-comparison/v1",
        "warning": "Equal track counts are not evidence of track recovery.",
        "thresholds": {
            "strict": settings["strict"],
            "relaxed": settings["relaxed"],
            "source_evidence_circular_cfo_gate_hz": settings[
                "source_evidence_circular_cfo_gate_hz"],
            "minimum_tracking_support": settings["minimum_tracking_support"],
        },
        "reference": {"input_observations": ref_file.input_count,
                      "used_observations": ref_file.used_count,
                      "track_count": len(refs), "config_digest": ref_file.config_digest,
                      "config_identity_available": bool(ref_file.config_digest),
                      "tracklet_identity_missing_count": sum(not track.tracklet_id for track in refs)},
        "native": {"input_observations": native_file.input_count,
                   "used_observations": native_file.used_count,
                   "track_count": len(natives), "config_digest": native_file.config_digest,
                   "config_identity_available": bool(native_file.config_digest),
                   "tracklet_identity_missing_count": sum(not track.tracklet_id for track in natives)},
        "reference_support": reference_support,
        "strict": modes["strict"],
        "relaxed": modes["relaxed"],
        "fragment_union_coverage": fragment_coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-observations", type=Path, required=True)
    parser.add_argument("--reference-tracks", type=Path, required=True)
    parser.add_argument("--reference-source-map", type=Path, required=True)
    parser.add_argument("--native-observations", type=Path, required=True)
    parser.add_argument("--native-tracks", type=Path, required=True)
    parser.add_argument("--native-source-map", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path,
                        default=Path(__file__).with_name("thresholds.json"))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise SystemExit("refusing to overwrite output")
    settings = json.loads(arguments.thresholds.read_text(encoding="utf-8"))
    ref_observations = read_observations(arguments.reference_observations)
    native_observations = read_observations(arguments.native_observations)
    ref_sources = read_source_map(arguments.reference_source_map, ref_observations)
    native_sources = read_source_map(arguments.native_source_map, native_observations)
    ref_tracks = read_tracks(arguments.reference_tracks, ref_observations)
    native_tracks = read_tracks(arguments.native_tracks, native_observations)
    report = compare(ref_tracks, native_tracks, ref_observations, native_observations,
                     ref_sources, native_sources, settings)
    report["inputs"] = {
        name: {"path": str(path), "sha256": sha256(path)} for name, path in (
            ("reference_observations", arguments.reference_observations),
            ("reference_tracks", arguments.reference_tracks),
            ("reference_source_map", arguments.reference_source_map),
            ("native_observations", arguments.native_observations),
            ("native_tracks", arguments.native_tracks),
            ("native_source_map", arguments.native_source_map),
            ("thresholds", arguments.thresholds),
        )
    }
    temporary = arguments.output.with_name(arguments.output.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
