#!/usr/bin/env python3
"""Audit held-frequency joins and cross-mask source-interval overlap.

This reads compact derived evidence only. It performs no scientific fit and
keeps the paired-receiver opportunity audit out of scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--held-frequency", type=Path, required=True)
    parser.add_argument("--model-rows", type=Path, required=True)
    parser.add_argument("--source-links", type=Path, required=True)
    parser.add_argument("--associations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("output already exists")

    held = json.loads(args.held_frequency.read_text())
    model_rows = json.loads(args.model_rows.read_text())
    source_links = json.loads(args.source_links.read_text())
    associations = json.loads(args.associations.read_text())

    def held_key(row: dict[str, Any]) -> tuple[str, str, str]:
        return row["session_id"], row["track_id"], row["observation_id"]

    def model_key(row: dict[str, Any]) -> tuple[str, str, str]:
        return row["session_id"], row["track_id"], row["observation_id"]

    held_index = {held_key(row): row for row in held["rows"]}
    model_index = {model_key(row): row for row in model_rows}
    if len(held_index) != len(held["rows"]) or len(model_index) != len(model_rows):
        raise ValueError("duplicate held-frequency or model-row identity")
    if set(held_index) != set(model_index):
        raise ValueError("held-frequency and model-row identities differ")

    link_index: dict[tuple[str, str, str], str] = {}
    for session_id, branch in source_links.items():
        for row in branch["rows"]:
            if len(row["candidate_ids"]) != 1:
                continue
            key = session_id, row["track_id"], row["observation_id"]
            if key in link_index:
                raise ValueError("duplicate unambiguous source link")
            link_index[key] = row["candidate_ids"][0]
    for key, row in held_index.items():
        if link_index.get(key) != row["source_candidate_id"]:
            raise ValueError("held-frequency source candidate differs from source link")
        model = model_index[key]
        expected_split = "calibration" if model["split"] == "cal" else "holdout"
        if (
            row["observation_utc_ns"] != model["observation_utc_ns"]
            or row["candidate_ids"] != model["candidate_ids"]
            or row["split"] != expected_split
        ):
            raise ValueError("held-frequency identity fields differ from model row")

    association_index = {
        (branch["session_id"], row["track_id"], row["projected_observation_id"]): row
        for branch in associations["branches"]
        for row in branch["rows"]
    }
    mask_rows: list[tuple[str, str, dict[str, Any]]] = []
    for session_id, accounting in held["accounting"].items():
        for track in accounting["track_masks"]:
            mask_rows.extend(
                (session_id, track["track_id"], row) for row in track["observation_sources"]
            )
    mask_keys = {
        (session_id, track_id, row["observation_id"]) for session_id, track_id, row in mask_rows
    }
    if len(mask_keys) != len(mask_rows) or mask_keys != set(association_index):
        raise ValueError("frequency mask inventory differs from associations")

    source_fields = (
        "observation_utc_ns",
        "source_group_id",
        "source_sample_start",
        "source_sample_end",
        "support_center_utc_ns",
        "stream_id",
    )
    for session_id, track_id, row in mask_rows:
        association = association_index[(session_id, track_id, row["observation_id"])]
        if row["training"] != association["training"] or any(
            row[field] != association[field] for field in source_fields
        ):
            raise ValueError("frequency mask source provenance differs from association")

    # Compare half-open [start, end) intervals only where sample coordinates
    # share the exact session, source group, and stream coordinate system.
    grouped: dict[tuple[str, str, str], list[list[tuple[int, int, str, str]]]] = defaultdict(
        lambda: [[], []]
    )
    for session_id, track_id, row in mask_rows:
        interval = (
            int(row["source_sample_start"]),
            int(row["source_sample_end"]),
            track_id,
            row["observation_id"],
        )
        group = session_id, row["source_group_id"], row["stream_id"]
        grouped[group][0 if row["training"] else 1].append(interval)

    pair_count = 0
    same_track_count = 0
    exact_interval_count = 0
    pair_summed_overlap_samples = 0
    participating_training: set[tuple[str, str, str, str, str]] = set()
    participating_held: set[tuple[str, str, str, str, str]] = set()
    pairs_by_group: Counter[tuple[str, str, str]] = Counter()
    pairs_by_session: Counter[str] = Counter()
    overlap_lengths: Counter[int] = Counter()
    for group, (training, held_rows) in grouped.items():
        training.sort()
        held_rows.sort()
        held_start = 0
        for train in training:
            while held_start < len(held_rows) and held_rows[held_start][1] <= train[0]:
                held_start += 1
            index = held_start
            while index < len(held_rows) and held_rows[index][0] < train[1]:
                held_row = held_rows[index]
                overlap = min(train[1], held_row[1]) - max(train[0], held_row[0])
                if overlap > 0:
                    pair_count += 1
                    same_track_count += train[2] == held_row[2]
                    exact_interval_count += train[:2] == held_row[:2]
                    pair_summed_overlap_samples += overlap
                    pairs_by_group[group] += 1
                    pairs_by_session[group[0]] += 1
                    overlap_lengths[overlap] += 1
                    participating_training.add((*group, train[2], train[3]))
                    participating_held.add((*group, held_row[2], held_row[3]))
                index += 1

    mask_counts = Counter(row["training"] for _, _, row in mask_rows)
    result = {
        "schema": "rx-held-frequency-overlap-audit/v1",
        "scope": (
            "Read-only compact-evidence join and training/held source-interval overlap; "
            "no fit and no paired-receiver opportunity audit"
        ),
        "inputs": {
            "held_frequency": {
                "path": str(args.held_frequency),
                "sha256": digest(args.held_frequency),
            },
            "model_rows": {"path": str(args.model_rows), "sha256": digest(args.model_rows)},
            "source_links": {"path": str(args.source_links), "sha256": digest(args.source_links)},
            "associations": {"path": str(args.associations), "sha256": digest(args.associations)},
            "audit_script": {"path": str(Path(__file__)), "sha256": digest(Path(__file__))},
        },
        "join_assertions": {
            "held_rows": len(held["rows"]),
            "unique_held_keys": len(held_index),
            "model_rows": len(model_rows),
            "unique_model_keys": len(model_index),
            "held_model_key_sets_equal": True,
            "unambiguous_source_links": len(link_index),
            "held_source_link_mismatches": 0,
            "held_model_identity_mismatches": 0,
            "mask_observations": len(mask_rows),
            "unique_mask_keys": len(mask_keys),
            "association_rows": len(association_index),
            "mask_association_key_sets_equal": True,
            "mask_association_provenance_mismatches": 0,
            "training_observations": mask_counts[True],
            "held_observations": mask_counts[False],
        },
        "overlap_definition": {
            "group_key": ["session_id", "source_group_id", "stream_id"],
            "interval": "half-open [source_sample_start, source_sample_end)",
            "pairing": "every training interval against every overlapping held interval in group",
        },
        "overlap": {
            "source_groups_total": len(grouped),
            "source_groups_with_overlap": len(pairs_by_group),
            "training_held_pairs": pair_count,
            "same_track_pairs": same_track_count,
            "cross_track_pairs": pair_count - same_track_count,
            "exact_interval_pairs": exact_interval_count,
            "participating_training_observations": len(participating_training),
            "participating_held_observations": len(participating_held),
            "pair_summed_overlap_samples": pair_summed_overlap_samples,
            "maximum_pairs_per_source_group": max(pairs_by_group.values(), default=0),
            "source_groups_with_multiple_pairs": sum(
                value > 1 for value in pairs_by_group.values()
            ),
            "pairs_by_session": dict(sorted(pairs_by_session.items())),
            "overlap_sample_counts": {
                str(length): count for length, count in sorted(overlap_lengths.items())
            },
        },
        "interpretation_limit": (
            "Pair-summed samples can double-count across pairs. This source-coordinate overlap "
            "does not by itself establish paired-receiver opportunity overlap."
        ),
    }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
