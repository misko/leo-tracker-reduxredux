#!/usr/bin/env python3
"""Bounded public-contract DS9 timestamp perturbation diagnostic."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import time
from pathlib import Path


AMPLITUDES_MS = (1, 10, 50)
SEARCHES = {
    "sacramento": (38.5816, -121.4944, 250.0),
    "reno": (39.5296, -119.8138, 500.0),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], output: Path, deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("matrix wall-time limit expired")
    started = time.monotonic()
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=remaining,
        check=False,
    )
    output.write_text(result.stdout)
    output.with_suffix(output.suffix + ".stderr").write_text(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return time.monotonic() - started


def load_candidates(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError("candidate header absent")
        return reader.fieldnames, list(reader)


def load_graph(path: Path) -> tuple[str, list[str], list[dict[str, str]]]:
    with path.open(newline="") as stream:
        meta = stream.readline().rstrip("\n")
        reader = csv.DictReader(stream, delimiter="\t")
        if not meta.startswith("META\t") or reader.fieldnames is None:
            raise ValueError("graph authority header absent")
        return meta, reader.fieldnames, list(reader)


def write_variant(
    candidate_path: Path,
    graph_path: Path,
    output_dir: Path,
    name: str,
    kind: str,
    amplitude_ms: int,
) -> tuple[Path, Path, dict[str, int]]:
    fields, candidates = load_candidates(candidate_path)
    meta, graph_fields, graph = load_graph(graph_path)
    groups = sorted({row["source_group_id"] for row in candidates})
    amplitude_ns = amplitude_ms * 1_000_000
    if kind == "baseline":
        deltas = {group: 0 for group in groups}
    elif kind == "common":
        deltas = {group: amplitude_ns for group in groups}
    elif kind == "jitter":
        deltas = {
            group: (-amplitude_ns if rank % 2 == 0 else amplitude_ns)
            for rank, group in enumerate(groups)
        }
    else:
        raise ValueError(f"unsupported perturbation kind: {kind}")

    by_candidate: dict[str, int] = {}
    timestamp_fields = (
        "support_start_utc_ns",
        "support_center_utc_ns",
        "support_end_utc_ns",
    )
    for row in candidates:
        delta = deltas[row["source_group_id"]]
        for field in timestamp_fields:
            row[field] = str(int(row[field]) + delta)
        previous = by_candidate.setdefault(row["candidate_id"], delta)
        if previous != delta:
            raise ValueError("candidate identity spans source groups with different deltas")

    for row in graph:
        try:
            delta = by_candidate[row["candidate_id"]]
        except KeyError as error:
            raise ValueError("graph contains an unknown candidate") from error
        for field in timestamp_fields:
            row[field] = str(int(row[field]) + delta)

    output_dir.mkdir(parents=True, exist_ok=True)
    variant_candidates = output_dir / f"{name}.candidates.tsv"
    variant_graph = output_dir / f"{name}.graph-candidates.tsv"
    with variant_candidates.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(candidates)
    with variant_graph.open("w", newline="") as stream:
        stream.write(meta + "\n")
        writer = csv.DictWriter(
            stream, fieldnames=graph_fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(graph)
    return variant_candidates, variant_graph, deltas


def parse_tracking(path: Path) -> list[dict]:
    tracks: list[dict] = []
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if fields[0] == "TRACK":
            tracks.append(
                {
                    "segment_id": fields[2],
                    "tracklet_id": fields[3],
                    "lane": (int(fields[4]), int(fields[5]), fields[6], float(fields[7])),
                    "rate": float(fields[11]),
                    "intercept": float(fields[12]),
                    "residual_rms": float(fields[13]),
                    "residual_max": float(fields[14]),
                    "points": [],
                }
            )
        elif fields[0] == "POINT":
            tracks[int(fields[1])]["points"].append(
                (fields[2], fields[3], int(fields[4]), float(fields[5]), float(fields[6]))
            )
    return tracks


def signature(track: dict) -> tuple:
    return (*track["lane"], tuple(sorted(point[0] for point in track["points"])))


def parse_pipeline(path: Path) -> list[dict]:
    tracks: list[dict] = []
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if fields[0] == "TRACK":
            tracks.append(
                {
                    "tracklet_id": fields[2],
                    "support_digest": fields[3],
                    "partition_seed": fields[4],
                    "points": [],
                }
            )
        elif fields[0] == "POINT":
            tracks[int(fields[1])]["points"].append(
                (fields[2], float(fields[3]), float(fields[4]), int(fields[5]))
            )
    return tracks


def compare_tracking(baseline: list[dict], current: list[dict]) -> dict:
    left = {signature(track): track for track in baseline}
    right = {signature(track): track for track in current}
    shared = sorted(set(left) & set(right), key=repr)
    alias_changes = 0
    max_rate_delta = 0.0
    max_intercept_delta = 0.0
    max_residual_rms_delta = 0.0
    max_residual_max_delta = 0.0
    segment_id_changes = 0
    tracklet_id_changes = 0
    for key in shared:
        a, b = left[key], right[key]
        pa = {item[0]: item for item in a["points"]}
        pb = {item[0]: item for item in b["points"]}
        alias_changes += sum(pa[candidate][2] != pb[candidate][2] for candidate in pa.keys() & pb.keys())
        max_rate_delta = max(max_rate_delta, abs(a["rate"] - b["rate"]))
        max_intercept_delta = max(max_intercept_delta, abs(a["intercept"] - b["intercept"]))
        max_residual_rms_delta = max(
            max_residual_rms_delta, abs(a["residual_rms"] - b["residual_rms"])
        )
        max_residual_max_delta = max(
            max_residual_max_delta, abs(a["residual_max"] - b["residual_max"])
        )
        segment_id_changes += a["segment_id"] != b["segment_id"]
        tracklet_id_changes += a["tracklet_id"] != b["tracklet_id"]
    return {
        "track_count": len(current),
        "exact_membership_tracks": len(shared),
        "baseline_only_memberships": len(set(left) - set(right)),
        "variant_only_memberships": len(set(right) - set(left)),
        "alias_changes_on_shared_tracks": alias_changes,
        "segment_id_changes_on_shared_tracks": segment_id_changes,
        "tracklet_id_changes_on_shared_tracks": tracklet_id_changes,
        "maximum_rate_delta_hz_per_s": max_rate_delta,
        "maximum_intercept_delta_hz": max_intercept_delta,
        "maximum_residual_rms_delta_hz": max_residual_rms_delta,
        "maximum_residual_max_delta_hz": max_residual_max_delta,
    }


def compare_pipeline(
    baseline_tracking: list[dict],
    current_tracking: list[dict],
    baseline: list[dict],
    current: list[dict],
) -> dict:
    left = {signature(track): index for index, track in enumerate(baseline_tracking)}
    right = {signature(track): index for index, track in enumerate(current_tracking)}
    shared = set(left) & set(right)
    digest_changes = seed_changes = mask_changes = compared_bits = observation_id_changes = 0
    max_time_delta = 0.0
    for key in shared:
        a, b = baseline[left[key]], current[right[key]]
        digest_changes += a["support_digest"] != b["support_digest"]
        seed_changes += a["partition_seed"] != b["partition_seed"]
        if len(a["points"]) != len(b["points"]):
            raise ValueError("shared tracking membership produced unequal pipeline point counts")
        for pa, pb in zip(a["points"], b["points"], strict=True):
            observation_id_changes += pa[0] != pb[0]
            max_time_delta = max(max_time_delta, abs(pa[1] - pb[1]))
            mask_changes += pa[3] != pb[3]
            compared_bits += 1
    return {
        "track_count": len(current),
        "shared_membership_tracks_compared": len(shared),
        "support_digest_changes": digest_changes,
        "partition_seed_changes": seed_changes,
        "training_mask_bit_changes": mask_changes,
        "training_mask_bits_compared": compared_bits,
        "observation_id_changes": observation_id_changes,
        "maximum_relative_time_delta_s": max_time_delta,
    }


def compare_fixed(
    baseline: dict,
    current: dict,
    baseline_tracking: list[dict],
    current_tracking: list[dict],
) -> dict:
    if len(baseline["points"]) != len(current["points"]):
        raise ValueError("fixed-site output count changed")
    left = {signature(track): index for index, track in enumerate(baseline_tracking)}
    right = {signature(track): index for index, track in enumerate(current_tracking)}
    shared = set(left) & set(right)
    result = []
    for a, b in zip(baseline["points"], current["points"], strict=True):
        if len(a["tracks"]) != len(b["tracks"]):
            raise ValueError("fixed-site track output count changed")
        result.append(
            {
                "score_hz": b["score_hz"],
                "absolute_score_delta_hz": abs(a["score_hz"] - b["score_hz"]),
                "matched_tracks": b["matched_tracks"],
                "matched_track_delta": b["matched_tracks"] - a["matched_tracks"],
                "same_ordinal_winner_or_tau_changes": sum(
                    x["candidate_id"] != y["candidate_id"] or x["tau_s"] != y["tau_s"]
                    for x, y in zip(a["tracks"], b["tracks"], strict=True)
                ),
                "shared_membership_tracks_compared": len(shared),
                "shared_membership_winner_or_tau_changes": sum(
                    a["tracks"][left[key]]["candidate_id"]
                    != b["tracks"][right[key]]["candidate_id"]
                    or a["tracks"][left[key]]["tau_s"]
                    != b["tracks"][right[key]]["tau_s"]
                    for key in shared
                ),
            }
        )
    return {"sites": result}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--tracking", type=Path, required=True)
    parser.add_argument("--pipeline", type=Path, required=True)
    parser.add_argument("--location", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wall-limit", type=float, default=590.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.work.exists():
        shutil.rmtree(args.work)
    args.work.mkdir(parents=True)

    source = args.root / "reports/2026_09_30_native_adaptive_deployment/tracking"
    candidate_path = source / "candidates.tsv"
    graph_path = source / "graph-candidates.tsv"
    loc1_authority = source / "native-e2.loc1"
    variants = [("baseline", "baseline", 0)]
    variants += [(f"common-{value}ms", "common", value) for value in AMPLITUDES_MS]
    variants += [(f"jitter-{value}ms", "jitter", value) for value in AMPLITUDES_MS]

    started = time.monotonic()
    deadline = started + args.wall_limit
    records: dict[str, dict] = {}
    for name, kind, amplitude in variants:
        variant_dir = args.work / name
        candidates, graph, deltas = write_variant(
            candidate_path, graph_path, variant_dir, name, kind, amplitude
        )
        raw = args.output / "raw"
        raw.mkdir(exist_ok=True)
        tracking_output = raw / f"{name}.tracking.tsv"
        tracking_seconds = run(
            [str(args.tracking), str(candidates), "--workers", "2"], tracking_output, deadline
        )
        loc1 = variant_dir / f"{name}.loc1"
        pipeline_output = raw / f"{name}.pipeline.txt"
        pipeline_seconds = run(
            [str(args.pipeline), str(candidates), str(graph), str(loc1_authority), str(loc1)],
            pipeline_output,
            deadline,
        )
        tracks_output = Path(str(loc1) + ".tracks.tsv")
        retained_tracks = raw / f"{name}.pipeline-tracks.tsv"
        shutil.copyfile(tracks_output, retained_tracks)
        fixed_output = raw / f"{name}.fixed.json"
        fixed_seconds = run([str(args.location), "score", str(loc1), "2"], fixed_output, deadline)
        search_seconds: dict[str, float] = {}
        if name in {"baseline", "common-50ms", "jitter-50ms"}:
            for site, (latitude, longitude, radius) in SEARCHES.items():
                search_output = raw / f"{name}.search-{site}.json"
                search_seconds[site] = run(
                    [
                        str(args.location),
                        "search",
                        str(loc1),
                        str(latitude),
                        str(longitude),
                        str(radius),
                        "2",
                    ],
                    search_output,
                    deadline,
                )
        records[name] = {
            "kind": kind,
            "amplitude_ms": amplitude,
            "source_groups": len(deltas),
            "negative_groups": sum(delta < 0 for delta in deltas.values()),
            "positive_groups": sum(delta > 0 for delta in deltas.values()),
            "generated_candidates_sha256": sha256(candidates),
            "generated_graph_sha256": sha256(graph),
            "seconds": {
                "tracking": tracking_seconds,
                "pipeline": pipeline_seconds,
                "fixed_sites": fixed_seconds,
                "searches": search_seconds,
            },
        }
        loc1.unlink()

    raw = args.output / "raw"
    baseline_tracking = parse_tracking(raw / "baseline.tracking.tsv")
    baseline_pipeline = parse_pipeline(raw / "baseline.pipeline-tracks.tsv")
    baseline_fixed = json.loads((raw / "baseline.fixed.json").read_text())
    for name, _, _ in variants:
        tracking = parse_tracking(raw / f"{name}.tracking.tsv")
        pipeline = parse_pipeline(raw / f"{name}.pipeline-tracks.tsv")
        fixed = json.loads((raw / f"{name}.fixed.json").read_text())
        records[name]["tracking"] = compare_tracking(baseline_tracking, tracking)
        records[name]["pipeline"] = compare_pipeline(
            baseline_tracking, tracking, baseline_pipeline, pipeline
        )
        records[name]["fixed_sites"] = compare_fixed(
            baseline_fixed, fixed, baseline_tracking, tracking
        )
        if name in {"baseline", "common-50ms", "jitter-50ms"}:
            records[name]["searches"] = {}
            for site in SEARCHES:
                value = json.loads((raw / f"{name}.search-{site}.json").read_text())
                incumbent = value["selected"]
                baseline = json.loads((raw / f"baseline.search-{site}.json").read_text())
                reference = baseline["selected"]
                records[name]["searches"][site] = {
                    "evaluated_points": value["evaluated_points"],
                    "deferred_cells": value["deferred_cells"],
                    "complete": value["complete"],
                    "east_km": incumbent["east_km"],
                    "north_km": incumbent["north_km"],
                    "score_hz": incumbent["score_hz"],
                    "east_delta_km": incumbent["east_km"] - reference["east_km"],
                    "north_delta_km": incumbent["north_km"] - reference["north_km"],
                    "absolute_score_delta_hz": abs(incumbent["score_hz"] - reference["score_hz"]),
                }

    result = {
        "schema": "leo-ds9-host-timestamp-sensitivity/v1",
        "scope": "controlled public-candidate timestamp perturbation; diagnostic only",
        "perturbation": {
            "translated_fields": [
                "candidate.support_start_utc_ns",
                "candidate.support_center_utc_ns",
                "candidate.support_end_utc_ns",
                "graph.support_start_utc_ns",
                "graph.support_center_utc_ns",
                "graph.support_end_utc_ns",
            ],
            "graph_session_start": "fixed",
            "common": "+A for every source group",
            "jitter": "sorted source_group_id rank alternates -A,+A",
            "unchanged": "moments, CFO/scores, candidate/source IDs, row order",
            "limitation": "public fixture has source_group_id but no visit_id; jitter is group-coherent, not proven visit-coherent",
        },
        "inputs": {
            "candidates": {"path": str(candidate_path), "sha256": sha256(candidate_path)},
            "graph": {"path": str(graph_path), "sha256": sha256(graph_path)},
            "loc1_authority": {"path": str(loc1_authority), "sha256": sha256(loc1_authority)},
        },
        "artifacts": {
            "tracking": {"path": str(args.tracking), "sha256": sha256(args.tracking)},
            "pipeline": {"path": str(args.pipeline), "sha256": sha256(args.pipeline)},
            "location": {"path": str(args.location), "sha256": sha256(args.location)},
        },
        "search_policy": {
            "budget_points": 400,
            "workers": 2,
            "sites": SEARCHES,
            "variants": ["baseline", "common-50ms", "jitter-50ms"],
        },
        "elapsed_seconds": time.monotonic() - started,
        "wall_limit_seconds": args.wall_limit,
        "variants": records,
    }
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"elapsed_seconds": result["elapsed_seconds"], "variants": list(records)}))


if __name__ == "__main__":
    main()
