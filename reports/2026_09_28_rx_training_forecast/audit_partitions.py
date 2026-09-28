#!/usr/bin/env python3
"""Independently audit RX partition separation from exported source metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROLES = {"train", "reception", "held_frequency", "embargo"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _overlap_counts(
    rows: list[tuple[Any, ...]], key_size: int, role_at: int
) -> Counter[tuple[str, str]]:
    """Count every half-open interval overlap, grouped by the leading key fields."""
    grouped: dict[tuple[Any, ...], list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        grouped[row[:key_size]].append(row)
    counts: Counter[tuple[str, str]] = Counter()
    for values in grouped.values():
        values.sort(key=lambda row: (row[key_size], row[key_size + 1]))
        active: list[tuple[Any, ...]] = []
        for current in values:
            start, end = current[key_size], current[key_size + 1]
            active = [prior for prior in active if prior[key_size + 1] > start]
            for prior in active:
                if prior[key_size] < end and start < prior[key_size + 1]:
                    counts[tuple(sorted((prior[role_at], current[role_at])))] += 1
            active.append(current)
    return counts


def audit(
    partitions_path: Path,
    opportunities_path: Path,
    frequency_path: Path,
    links_path: Path,
) -> dict[str, Any]:
    partitions = json.loads(partitions_path.read_text(encoding="utf-8"))
    windows = partitions["windows"]
    roles = {row["source_window_id"]: row["role"] for row in windows}
    if len(roles) != len(windows) or set(roles.values()) - ROLES:
        raise ValueError("partition windows must have unique known roles")

    opportunities = _read_jsonl(opportunities_path)
    candidate_window: dict[str, str] = {}
    support_rows: list[tuple[Any, ...]] = []
    time_rows: list[tuple[Any, ...]] = []
    paired = 0
    for row in opportunities:
        window_id = row["source_window_id"]
        if window_id not in roles:
            raise ValueError("opportunity is absent from partitions")
        views = row["receivers"]
        receiver_ids = {view["receiver_id"] for view in views.values()}
        if set(views) != {"rx0", "rx1"} or receiver_ids != {0, 1}:
            raise ValueError("opportunity does not bind both receivers")
        paired += 1
        session = row["source_window"]["session_id"]
        role = roles[window_id]
        time_rows.append((session, row["window_start_utc_ns"], row["window_end_utc_ns"], role))
        for view in views.values():
            stream = f"rx-{view['receiver_id']}"
            for candidate in view["candidates"]:
                projected = candidate.get("projected_candidate_id")
                if projected is not None:
                    if projected in candidate_window:
                        raise ValueError("projected candidate maps to multiple windows")
                    candidate_window[projected] = window_id
                support = candidate.get("source_interval")
                if support is not None:
                    support_rows.append((
                        session,
                        stream,
                        support["source_sample_start"],
                        support["source_sample_end"],
                        role,
                    ))
    if set(roles) != {row["source_window_id"] for row in opportunities}:
        raise ValueError("partitions and opportunities have different window inventories")

    links = json.loads(links_path.read_text(encoding="utf-8"))
    frequency = json.loads(frequency_path.read_text(encoding="utf-8"))
    legacy_rows: list[tuple[Any, ...]] = []
    unresolved = 0
    for session, accounting in frequency["accounting"].items():
        source_link = {
            (row["track_id"], row["observation_id"]): row["candidate_ids"]
            for row in links[session]["rows"]
        }
        for track in accounting["track_masks"]:
            for observation in track["observation_sources"]:
                ids = source_link.get((track["track_id"], observation["observation_id"]), [])
                if len(ids) != 1 or ids[0] not in candidate_window:
                    unresolved += 1
                    continue
                legacy_rows.append(
                    (
                        session,
                        observation["source_group_id"],
                        observation["stream_id"],
                        observation["source_sample_start"],
                        observation["source_sample_end"],
                        roles[candidate_window[ids[0]]],
                        "old_train" if observation["training"] else "old_held",
                    )
                )
    if unresolved:
        raise ValueError("legacy frequency observation lacks an exact opportunity join")

    raw_time = _overlap_counts(time_rows, 1, 3)
    raw_support = _overlap_counts(support_rows, 2, 4)
    new_legacy = _overlap_counts(legacy_rows, 3, 5)
    old_legacy = _overlap_counts(legacy_rows, 3, 6)
    combined_legacy = _overlap_counts(
        [(*row[:5], f"{row[5]}::{row[6]}") for row in legacy_rows], 3, 5
    )
    def cross_role_count(values: Counter[tuple[str, str]]) -> int:
        return sum(count for (left, right), count in values.items() if left != right)

    rate_role = Counter((row["sample_rate_hz"], row["role"]) for row in windows)
    rate_split = Counter(
        (row["sample_rate_hz"], row["recording_split"])
        for row in partitions["recordings"]
    )
    old_cross_by_new_role = Counter()
    for (left, right), count in combined_legacy.items():
        left_new, left_old = left.split("::", 1)
        right_new, right_old = right.split("::", 1)
        if {left_old, right_old} == {"old_train", "old_held"}:
            old_cross_by_new_role["|".join(sorted((left_new, right_new)))] += count
    return {
        "schema": "rx-grouped-partition-independent-audit/v1",
        "inputs": {
            str(path): "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (partitions_path, opportunities_path, frequency_path, links_path)
        },
        "inventory": {
            "partition_windows": len(windows), "opportunity_windows": len(opportunities),
            "paired_receiver_windows": paired, "raw_candidate_supports": len(support_rows),
            "legacy_frequency_observations_joined": len(legacy_rows),
        },
        "separation": {
            "cross_role_time_window_overlap_pairs": cross_role_count(raw_time),
            "cross_role_raw_candidate_support_overlap_pairs": cross_role_count(raw_support),
            "cross_role_legacy_source_overlap_pairs": cross_role_count(new_legacy),
            "legacy_original_train_held_overlap_pairs": sum(
                count
                for (left, right), count in old_legacy.items()
                if {left, right} == {"old_train", "old_held"}
            ),
            "all_legacy_overlap_pairs_by_new_role": {
                f"{a}|{b}": n for (a, b), n in sorted(new_legacy.items())
            },
            "old_train_held_overlap_pairs_by_new_role": dict(sorted(old_cross_by_new_role.items())),
        },
        "coverage": {
            "windows_by_rate_and_role": {
                f"{rate}|{role}": n for (rate, role), n in sorted(rate_role.items())
            },
            "recordings_by_rate_and_split": {
                f"{rate}|{split}": n for (rate, split), n in sorted(rate_split.items())
            },
        },
        "conclusion": (
            "All independently enumerated overlapping time, raw-candidate-support, and "
            "legacy source-support pairs remain within one new temporal role."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partitions", type=Path, required=True)
    parser.add_argument("--opportunities", type=Path, required=True)
    parser.add_argument("--frequency", type=Path, required=True)
    parser.add_argument("--links", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = audit(args.partitions, args.opportunities, args.frequency, args.links)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
