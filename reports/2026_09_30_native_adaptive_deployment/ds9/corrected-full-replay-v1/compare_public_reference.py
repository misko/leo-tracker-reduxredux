#!/usr/bin/env python3
"""Compare corrected native public products with the frozen public reference products."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / "tracking"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_number(value: str | float | int, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite {label}")
    return number


def candidate_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    for row in rows:
        for field in ("actual_rf_hz", "measured_cfo_hz", "exact_score", "control_score", "margin"):
            finite_number(row[field], f"candidate {field}")
    return rows


def graph_rows(path: Path) -> dict[str, list[str]]:
    with path.open() as source:
        metadata = source.readline().rstrip("\n").split("\t")
        header = source.readline().rstrip("\n").split("\t")
        if len(metadata) != 4 or metadata[0] != "META" or len(header) != 8:
            raise ValueError(f"invalid graph authority: {path}")
        rows: dict[str, list[str]] = {}
        for line in source:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 8 or fields[0] in rows:
                raise ValueError(f"invalid graph row: {path}")
            for index in range(4, 8):
                finite_number(fields[index], f"graph field {index}")
            rows[fields[0]] = fields
        return rows


def track_rows(path: Path) -> list[dict[str, object]]:
    tracks: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if fields[0] == "TRACK":
            if len(fields) != 17:
                raise ValueError(f"invalid track row: {path}")
            current = {
                "index": int(fields[1]),
                "tracklet_id": fields[2],
                "episode_id": fields[3],
                "receiver_id": int(fields[4]),
                "channel": int(fields[5]),
                "edge": fields[6],
                "actual_rf_hz": int(fields[7]),
                "support_start_utc_ns": int(fields[8]),
                "support_end_utc_ns": int(fields[9]),
                "reference_utc_ns": int(fields[10]),
                "slope": finite_number(fields[11], "track slope"),
                "intercept": finite_number(fields[12], "track intercept"),
                "rms": finite_number(fields[13], "track rms"),
                "max": finite_number(fields[14], "track maximum residual"),
                "weight": finite_number(fields[15], "track weight"),
                "declared_points": int(fields[16]),
                "points": [],
            }
            tracks.append(current)
        elif fields[0] == "POINT":
            if current is None or len(fields) != 7:
                raise ValueError(f"invalid track point: {path}")
            current["points"].append(
                {
                    "candidate_id": fields[2],
                    "source_group_id": fields[3],
                    "relative_alias_index": int(fields[4]),
                    "dealiased_cfo_hz": finite_number(fields[5], "point dealiased CFO"),
                    "normalized_dealiased_cfo_hz": finite_number(fields[6], "point normalized CFO"),
                }
            )
    for track in tracks:
        if len(track["points"]) != track["declared_points"]:
            raise ValueError(f"track point count mismatch: {path}")
    return tracks


def evidence_rows(path: Path) -> list[dict[str, object]]:
    tracks: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if fields[0] == "TRACK":
            if len(fields) != 6:
                raise ValueError(f"invalid location-track row: {path}")
            current = {
                "index": int(fields[1]),
                "tracklet_id": fields[2],
                "support_digest": fields[3],
                "partition_seed": fields[4],
                "declared_points": int(fields[5]),
                "points": [],
            }
            tracks.append(current)
        elif fields[0] == "POINT":
            if current is None or len(fields) != 6:
                raise ValueError(f"invalid location-track point: {path}")
            current["points"].append(
                {
                    "observation_id": fields[2],
                    "time_s": finite_number(fields[3], "location-track time"),
                    "measured_hz": finite_number(fields[4], "location-track measurement"),
                    "training": int(fields[5]),
                }
            )
    for track in tracks:
        if len(track["points"]) != track["declared_points"]:
            raise ValueError(f"location-track point count mismatch: {path}")
    return tracks


def physical_track_key(track: dict[str, object]) -> tuple[tuple[str, int], ...]:
    return tuple(
        sorted(
            (point["source_group_id"], point["relative_alias_index"]) for point in track["points"]
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", type=Path, default=HERE / "full-public-c3-c4")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    native_dir = args.native.resolve()
    output = args.output.resolve() if args.output else native_dir / "reference-comparison.json"
    native_candidates = candidate_rows(native_dir / "candidates.tsv")
    reference_candidates = candidate_rows(REFERENCE / "candidates.tsv")
    if len(native_candidates) != len(reference_candidates):
        raise ValueError("candidate count differs")

    paired_fields = (
        "source_group_id",
        "receiver_id",
        "channel",
        "edge",
        "actual_rf_hz",
        "support_start_utc_ns",
        "support_center_utc_ns",
        "support_end_utc_ns",
    )
    numeric_fields = ("measured_cfo_hz", "exact_score", "control_score", "margin")
    maximum_observation_delta = {field: 0.0 for field in numeric_fields}
    exact_candidate_ids = 0
    for native, reference in zip(native_candidates, reference_candidates, strict=True):
        if any(native[field] != reference[field] for field in paired_fields):
            raise ValueError("candidate physical ordering or support differs")
        exact_candidate_ids += native["candidate_id"] == reference["candidate_id"]
        for field in numeric_fields:
            maximum_observation_delta[field] = max(
                maximum_observation_delta[field],
                abs(
                    finite_number(native[field], f"native {field}")
                    - finite_number(reference[field], f"reference {field}")
                ),
            )

    native_graph = graph_rows(native_dir / "graph-candidates.tsv")
    reference_graph = graph_rows(REFERENCE / "graph-candidates.tsv")
    exact_moment2 = 0
    exact_moment3 = 0
    exact_graph_support = 0
    max_moment2 = 0.0
    max_moment3 = 0.0
    for native, reference in zip(native_candidates, reference_candidates, strict=True):
        ng = native_graph[native["candidate_id"]]
        rg = reference_graph[reference["candidate_id"]]
        exact_graph_support += ng[1:4] == rg[1:4]
        exact_moment2 += ng[6] == rg[6]
        exact_moment3 += ng[7] == rg[7]
        max_moment2 = max(
            max_moment2,
            abs(finite_number(ng[6], "native moment2") - finite_number(rg[6], "reference moment2")),
        )
        max_moment3 = max(
            max_moment3,
            abs(finite_number(ng[7], "native moment3") - finite_number(rg[7], "reference moment3")),
        )

    native_tracks = track_rows(native_dir / "tracks.tsv")
    reference_tracks = track_rows(REFERENCE / "native-tracks.tsv")
    native_by_key = {physical_track_key(track): track for track in native_tracks}
    reference_by_key = {physical_track_key(track): track for track in reference_tracks}
    if len(native_by_key) != len(native_tracks) or len(reference_by_key) != len(reference_tracks):
        raise ValueError("physical track key is not unique")
    common_keys = set(native_by_key) & set(reference_by_key)
    if len(common_keys) != len(native_tracks) or len(common_keys) != len(reference_tracks):
        raise ValueError("physical track memberships differ")

    max_track_delta = {field: 0.0 for field in ("slope", "intercept", "rms", "max", "weight")}
    exact_tracklets = 0
    exact_support_bounds = 0
    exact_aliases = 0
    paired_indexes: list[tuple[int, int]] = []
    for key in sorted(common_keys):
        native = native_by_key[key]
        reference = reference_by_key[key]
        paired_indexes.append((reference["index"], native["index"]))
        exact_tracklets += native["tracklet_id"] == reference["tracklet_id"]
        exact_support_bounds += all(
            native[field] == reference[field]
            for field in ("support_start_utc_ns", "support_end_utc_ns", "reference_utc_ns")
        )
        exact_aliases += len(key)
        for field in max_track_delta:
            max_track_delta[field] = max(
                max_track_delta[field], abs(native[field] - reference[field])
            )

    native_evidence = evidence_rows(native_dir / "native-e2.loc1.tracks.tsv")
    reference_evidence = evidence_rows(REFERENCE / "native-e2.loc1.tracks.tsv")
    exact_support_digests = 0
    exact_partition_seeds = 0
    exact_training_masks = 0
    same_training_counts = 0
    equal_training_bits = 0
    total_training_bits = 0
    exact_observation_ids = 0
    for reference_index, native_index in paired_indexes:
        native = native_evidence[native_index]
        reference = reference_evidence[reference_index]
        exact_support_digests += native["support_digest"] == reference["support_digest"]
        exact_partition_seeds += native["partition_seed"] == reference["partition_seed"]
        native_mask = [point["training"] for point in native["points"]]
        reference_mask = [point["training"] for point in reference["points"]]
        exact_training_masks += native_mask == reference_mask
        same_training_counts += sum(native_mask) == sum(reference_mask)
        equal_training_bits += sum(
            left == right for left, right in zip(native_mask, reference_mask, strict=True)
        )
        total_training_bits += len(native_mask)
        exact_observation_ids += sum(
            left["observation_id"] == right["observation_id"]
            for left, right in zip(native["points"], reference["points"], strict=True)
        )

    native_scores = json.loads((native_dir / "location-score.json").read_text())
    reference_scores = json.loads((REFERENCE / "native-e2-score.json").read_text())
    point_comparisons = []
    for point_index in range(2):
        native_point = native_scores["points"][point_index]
        reference_point = reference_scores["points"][point_index]
        for label, point in (("native", native_point), ("reference", reference_point)):
            finite_number(point["score_hz"], f"{label} location score")
            for track in point["tracks"]:
                for field in ("tau_s", "held_hz", "fit_hz", "offset_hz"):
                    finite_number(track[field], f"{label} location {field}")
        same_satellite = 0
        same_tau = 0
        same_winner = 0
        for reference_index, native_index in paired_indexes:
            native = native_point["tracks"][native_index]
            reference = reference_point["tracks"][reference_index]
            same_satellite += native["candidate_id"] == reference["candidate_id"]
            same_tau += native["tau_s"] == reference["tau_s"]
            same_winner += (native["candidate_id"], native["tau_s"]) == (
                reference["candidate_id"],
                reference["tau_s"],
            )
        point_comparisons.append(
            {
                "point_index": point_index,
                "native_score_hz": native_point["score_hz"],
                "reference_score_hz": reference_point["score_hz"],
                "score_difference_hz": native_point["score_hz"] - reference_point["score_hz"],
                "matched_tracks_each": native_point["matched_tracks"],
                "same_satellite_winner_tracks": same_satellite,
                "same_tau_tracks": same_tau,
                "same_satellite_and_tau_tracks": same_winner,
            }
        )

    compared_files = [
        native_dir / "candidates.tsv",
        native_dir / "graph-candidates.tsv",
        native_dir / "tracks.tsv",
        native_dir / "native-e2.loc1.tracks.tsv",
        native_dir / "location-score.json",
        REFERENCE / "candidates.tsv",
        REFERENCE / "graph-candidates.tsv",
        REFERENCE / "native-tracks.tsv",
        REFERENCE / "native-e2.loc1.tracks.tsv",
        REFERENCE / "native-e2-score.json",
    ]
    result = {
        "schema": "org.leo.corrected-native-public-reference-comparison/v2",
        "status": "physical_membership_equal_identity_and_partition_different",
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in compared_files},
        "candidate_observations": {
            "native": len(native_candidates),
            "reference": len(reference_candidates),
            "physical_order_and_support_equal": True,
            "source_group_multiset_equal": True,
            "exact_candidate_ids": exact_candidate_ids,
            "maximum_absolute_delta": maximum_observation_delta,
        },
        "tracks": {
            "native": len(native_tracks),
            "reference": len(reference_tracks),
            "exact_lane_source_and_alias_memberships": len(common_keys),
            "exact_support_bounds_and_reference": exact_support_bounds,
            "exact_alias_indices": exact_aliases,
            "exact_tracklet_ids": exact_tracklets,
            "maximum_absolute_fit_delta": max_track_delta,
        },
        "graph_authority": {
            "rows_compared": len(native_candidates),
            "exact_support_bounds": exact_graph_support,
            "exact_moment2_lexemes": exact_moment2,
            "exact_moment3_lexemes": exact_moment3,
            "maximum_moment2_numeric_delta": max_moment2,
            "maximum_moment3_numeric_delta": max_moment3,
            "native_moment_lexemes_preserved": True,
            "reference_moments_injected": False,
        },
        "partition_authority": {
            "tracks_compared_by_physical_membership": len(paired_indexes),
            "exact_observation_ids": exact_observation_ids,
            "exact_support_digests": exact_support_digests,
            "exact_partition_seeds": exact_partition_seeds,
            "exact_training_masks": exact_training_masks,
            "same_training_count_tracks": same_training_counts,
            "equal_training_bits": equal_training_bits,
            "training_bits_compared": total_training_bits,
            "interpretation": (
                "The response-free identities bind candidate and track identities. Tiny native "
                "score/moment changes therefore produce new observation IDs, support digests, "
                "partition seeds, and held-out masks despite equal physical memberships."
            ),
        },
        "fixed_site_location": point_comparisons,
        "identity_note": (
            "Candidate, observation, and track identities intentionally bind each analysis. "
            "Physical source-group and alias membership is the cross-analysis comparison key."
        ),
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
