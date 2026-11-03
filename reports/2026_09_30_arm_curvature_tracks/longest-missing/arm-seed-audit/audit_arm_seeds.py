#!/usr/bin/env python3
"""Audit ARM-input seed coverage against canonical server reference sources."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def circular_residual(value: float, prediction: float, spacing: float) -> float:
    result = math.fmod(value - prediction + spacing / 2.0, spacing)
    if result < 0.0:
        result += spacing
    return result - spacing / 2.0


def lane_key(row: dict) -> tuple[int, str, int, float]:
    return row["channel"], row["edge"], row["receiver_id"], row["actual_rf_hz"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--observation-source-map", type=Path, required=True)
    parser.add_argument("--reference-observations", type=Path, required=True)
    parser.add_argument("--reference-tracks", type=Path, required=True)
    parser.add_argument("--reference-source-map", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--tracker-stderr", type=Path, required=True)
    parser.add_argument("--physical-output", type=Path, required=True)
    parser.add_argument("--comparator-module", type=Path, required=True)
    parser.add_argument("--tracker-source", type=Path, required=True)
    parser.add_argument("--research-receipt", type=Path, required=True)
    parser.add_argument("--server-seed-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.comparator_module.parent.resolve()))
    import compare_membership as membership  # pylint: disable=import-error,import-outside-toplevel

    rows: list[dict] = []
    with args.observations.open(encoding="ascii", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        for row in reader:
            rows.append({
                **row,
                "receiver_id": int(row["receiver_id"]),
                "channel": int(row["channel"]),
                "actual_rf_hz": float(row["actual_rf_hz"]),
                "support_center_utc_ns": int(row["support_center_utc_ns"]),
                "measured_cfo_hz": float(row["measured_cfo_hz"]),
                "control_score": float(row["control_score"]),
                "margin": float(row["margin"]),
            })

    observations = membership.read_observations(args.observations)
    observation_sources = membership.read_sources(args.observation_source_map, observations)
    reference_observations = membership.read_observations(args.reference_observations)
    reference_sources = membership.read_sources(
        args.reference_source_map, reference_observations
    )
    reference = membership.read_tracks(args.reference_tracks, reference_observations)
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    if sha256(args.physical_output) != comparison["inputs"]["output_tracks"]["sha256"]:
        raise ValueError("physical output differs from the evaluated frozen host output")
    matched = {value["reference_track_index"] for value in comparison["primary"]["matches"]}
    merged = set(comparison["primary"]["one_to_one_unmatched_but_complete_merge_indexes"])
    missing_supported = set(comparison["primary"]["supported_without_complete_output_indexes"])
    missing_input_limited = set(comparison["primary"]["input_unsupported_reference_indexes"])
    missing = missing_supported | missing_input_limited
    if matched | merged | missing != set(range(len(reference.values))) or (
        matched & merged or matched & missing or merged & missing or
        missing_supported & missing_input_limited
    ):
        raise ValueError("reference outcome categories do not form a partition")

    reference_points = {
        track.index: {reference_sources[point.candidate]: point for point in track.points}
        for track in reference.values
    }
    if any(len(reference_points[track.index]) != len(track.points) for track in reference.values):
        raise ValueError("reference track repeats a canonical visit/RX/probe source")
    lanes: dict[tuple[int, str, int, float], list[dict]] = defaultdict(list)
    for row in rows:
        lanes[lane_key(row)].append(row)

    reference_audit = {
        index: {
            "reference_track_index": index,
            "outcome": (
                "complete_one_to_one" if index in matched else
                "complete_only_through_merge" if index in merged else
                "without_complete_output_input_supported" if index in missing_supported else
                "without_complete_output_input_limited"
            ),
        }
        for index in range(len(reference.values))
    }
    lane_audit = []
    total_considered = 0
    total_valid = 0
    total_retained = 0

    for lane, lane_rows in sorted(lanes.items()):
        reference_ns = min(row["support_center_utc_ns"] for row in lane_rows)
        scale = 11_200_000_000.0 / lane[3]
        spacing = (1.0 / 4.4e-6) * scale
        source_rows: dict[str, list[dict]] = defaultdict(list)
        for row in lane_rows:
            source_rows[row["source_group_id"]].append(row)

        points: list[dict] = []
        groups: list[dict] = []
        for source_group, items in sorted(source_rows.items()):
            items.sort(key=lambda row: (row["measured_cfo_hz"], row["candidate_id"]))
            times = [row["support_center_utc_ns"] for row in items]
            group_points: list[int] = []
            for item in items:
                raw_hz = item["measured_cfo_hz"] * scale
                weight = min(max(item["margin"], 0.0) / max(item["control_score"], 0.02), 16.0)
                if group_points and points[group_points[-1]]["raw_hz"] == raw_hz:
                    prior = points[group_points[-1]]
                    if weight > prior["weight"] or (
                        weight == prior["weight"] and
                        item["candidate_id"] < prior["row"]["candidate_id"]
                    ):
                        points[group_points[-1]] = {
                            "row": item,
                            "time_s": (item["support_center_utc_ns"] - reference_ns) / 1e9,
                            "raw_hz": raw_hz,
                            "weight": weight,
                        }
                    continue
                group_points.append(len(points))
                points.append({
                    "row": item,
                    "time_s": (item["support_center_utc_ns"] - reference_ns) / 1e9,
                    "raw_hz": raw_hz,
                    "weight": weight,
                })
            groups.append({
                "source_group": source_group,
                "time_s": ((min(times) + max(times)) / 2.0 - reference_ns) / 1e9,
                "points": group_points,
            })
        groups.sort(key=lambda group: (group["time_s"], group["source_group"]))

        seeds: list[dict] = []
        considered = 0
        for first_group in range(len(groups) - 1):
            second_group = first_group + 1
            while second_group < len(groups) and (
                groups[second_group]["time_s"] == groups[first_group]["time_s"]
            ):
                second_group += 1
            if second_group == len(groups):
                break
            for left in groups[first_group]["points"]:
                for right in groups[second_group]["points"]:
                    considered += 1
                    delta_s = points[right]["time_s"] - points[left]["time_s"]
                    if delta_s <= 0.0 or delta_s > 4.0:
                        continue
                    lifted_hz = points[right]["raw_hz"] + round(
                        (points[left]["raw_hz"] - points[right]["raw_hz"]) / spacing
                    ) * spacing
                    rate = (lifted_hz - points[left]["raw_hz"]) / delta_s
                    if rate < -15_000.0 or rate > 15_000.0:
                        continue
                    seeds.append({
                        "first_group": first_group,
                        "left": left,
                        "right": right,
                        "score": points[left]["weight"] + points[right]["weight"],
                        "time_s": groups[first_group]["time_s"],
                    })
        seeds.sort(
            key=lambda seed: (
                seed["score"], seed["first_group"], seed["left"], seed["right"]
            ),
            reverse=True,
        )
        retained = seeds[:512]
        total_considered += considered
        total_valid += len(seeds)
        total_retained += len(retained)

        minimum_time = min(group["time_s"] for group in groups)
        maximum_time = max(group["time_s"] for group in groups)
        bins = [0] * 10
        for seed in retained:
            fraction = (seed["time_s"] - minimum_time) / (maximum_time - minimum_time)
            bins[min(9, max(0, int(fraction * 10)))] += 1
        lane_audit.append({
            "lane": {"channel": lane[0], "edge": lane[1], "receiver_id": lane[2],
                     "actual_rf_hz": lane[3]},
            "source_groups": len(groups),
            "points_after_exact_deduplication": len(points),
            "seeds_considered": considered,
            "valid_seeds_before_cap": len(seeds),
            "retained_seeds": len(retained),
            "retained_cutoff_score": retained[-1]["score"],
            "lane_time_range_s": [minimum_time, maximum_time],
            "retained_first_endpoint_equal_time_deciles": bins,
            "retained_first_endpoint_time_range_s": [
                min(seed["time_s"] for seed in retained),
                max(seed["time_s"] for seed in retained),
            ],
        })

        lane_references = [
            track for track in reference.values
            if (track.lane.channel, track.lane.edge, track.lane.receiver, track.lane.rf_hz) == lane
        ]
        for track in lane_references:
            expected = reference_points[track.index]

            def compatible(seed: dict) -> bool:
                for point_index in (seed["left"], seed["right"]):
                    point = points[point_index]
                    expected_point = expected.get(
                        observation_sources[point["row"]["candidate_id"]]
                    )
                    if expected_point is None or abs(circular_residual(
                        point["raw_hz"], expected_point.dealiased_cfo_hz, spacing
                    )) > 2_500.0:
                        return False
                return True

            compatible_seeds = [
                (rank, seed) for rank, seed in enumerate(seeds, 1) if compatible(seed)
            ]
            retained_compatible = [
                (rank, seed) for rank, seed in compatible_seeds if rank <= 512
            ]
            centers = [reference_observations[point.candidate].center_ns for point in track.points]
            audit = reference_audit[track.index]
            audit.update({
                "lane": {"channel": lane[0], "edge": lane[1], "receiver_id": lane[2],
                         "actual_rf_hz": lane[3]},
                "reference_point_count": len(track.points),
                "reference_center_range_s": [
                    (min(centers) - reference_ns) / 1e9,
                    (max(centers) - reference_ns) / 1e9,
                ],
                "valid_compatible_seeds": len(compatible_seeds),
                "retained_compatible_seeds": len(retained_compatible),
                "best_compatible_global_rank": (
                    compatible_seeds[0][0] if compatible_seeds else None
                ),
                "best_compatible_score": (
                    compatible_seeds[0][1]["score"] if compatible_seeds else None
                ),
                "lane_retained_cutoff_score": retained[-1]["score"],
            })

    stderr_stats = None
    for line in args.tracker_stderr.read_text(encoding="ascii").splitlines():
        fields = line.split("\t")
        if fields[0] == "STATS":
            stderr_stats = [int(value) for value in fields[1:]]
    if stderr_stats is None or stderr_stats[:4] != [
        len(lanes), sum(item["source_groups"] for item in lane_audit),
        total_considered, total_retained,
    ]:
        raise ValueError("audit enumeration does not reproduce frozen tracker seed counters")

    server_audit = json.loads(args.server_seed_audit.read_text(encoding="utf-8"))
    server_references = {
        value["reference_track_index"]: value for value in server_audit["references"]
    }
    if set(server_references) != set(reference_audit):
        raise ValueError("server seed audit reference inventory differs")
    for index, audit in reference_audit.items():
        server = server_references[index]
        audit["server_input_comparison"] = {
            "outcome": server["outcome"],
            "valid_compatible_seeds": server["valid_compatible_seeds"],
            "retained_compatible_seeds": server["retained_compatible_seeds"],
            "best_compatible_global_rank": server["best_compatible_global_rank"],
        }

    references = [reference_audit[index] for index in sorted(reference_audit)]
    categories = {}
    for outcome in (
        "complete_one_to_one", "complete_only_through_merge",
        "without_complete_output_input_supported",
        "without_complete_output_input_limited",
    ):
        selected = [item for item in references if item["outcome"] == outcome]
        categories[outcome] = {
            "reference_tracks": len(selected),
            "with_any_valid_compatible_seed": sum(
                item["valid_compatible_seeds"] > 0 for item in selected
            ),
            "with_any_retained_compatible_seed": sum(
                item["retained_compatible_seeds"] > 0 for item in selected
            ),
        }

    output = {
        "schema": "leo-curvature-arm-seed-selection-audit/v1",
        "scope": (
            "Read-only reconstruction of seed enumeration and the 512-per-lane global "
            "weight cap on frozen ARM observations. Maintained server reference membership is "
            "joined only after the run through canonical (visit,receiver,probe) source maps."
        ),
        "inputs": {
            name: {"path": str(path.resolve()), "sha256": sha256(path)}
            for name, path in {
                "observations": args.observations,
                "observation_source_map": args.observation_source_map,
                "reference_observations": args.reference_observations,
                "reference_tracks": args.reference_tracks,
                "reference_source_map": args.reference_source_map,
                "comparison": args.comparison,
                "tracker_stderr": args.tracker_stderr,
                "physical_output": args.physical_output,
                "comparator_module": args.comparator_module,
                "tracker_source": args.tracker_source,
                "research_receipt": args.research_receipt,
                "server_seed_audit": args.server_seed_audit,
            }.items()
        },
        "compatibility_definition": (
            "Both ARM seed endpoints map to canonical (visit,receiver,probe) sources in the "
            "server reference track and their scaled CFOs are within the frozen 2500 Hz circular "
            "comparator gate of the reference dealiased CFO. Candidate and source-group digests "
            "are never compared across detector sides. This is diagnostic and was not supplied "
            "to the tracker."
        ),
        "exact_counter_cross_check": {
            "tracker_stderr": {
                "lanes": stderr_stats[0], "source_groups": stderr_stats[1],
                "seeds_considered": stderr_stats[2], "seeds_retained": stderr_stats[3],
            },
            "audit": {
                "lanes": len(lanes),
                "source_groups": sum(item["source_groups"] for item in lane_audit),
                "seeds_considered": total_considered,
                "valid_seeds_before_cap": total_valid,
                "seeds_retained": total_retained,
            },
        },
        "outcome_summary": categories,
        "requested_longest_missing_reference_indexes": [2, 10, 30, 8, 34, 47, 19, 59, 33],
        "requested_longest_missing": [
            reference_audit[index] for index in [2, 10, 30, 8, 34, 47, 19, 59, 33]
        ],
        "lanes": lane_audit,
        "references": references,
        "interpretation": {
            "finding": (
                "ARM seed coverage is separated from detector-input ceilings and merge displacement. "
                "The requested long missing references report valid and retained compatible seed "
                "counts and exact global ranks through canonical source identities."
            ),
            "recommendation": (
                "Use this audit to distinguish missing ARM evidence from seed-cap loss. Any future "
                "same-budget time-stratified experiment must keep seed construction, within-stratum "
                "order, tracing, beam, and consolidation unchanged; no primary configuration change "
                "is made here."
            ),
            "limits": (
                "Compatibility to a server segment is target-conditioned diagnosis. It does not "
                "establish satellite identity or prove that retaining a compatible seed would yield "
                "a complete output. Input-limited references must not be classified as tracker-only "
                "failures. In particular, reference 10 has many retained compatible seeds, while "
                "an independent local-quadratic continuation check finds the ARM continuation into "
                "the server's reference 16 substantially smoother than switching to reference 10. "
                "Its maintained-segmentation mismatch is therefore not evidence of an ARM tracking "
                "error or of physical identity truth."
            ),
        },
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
