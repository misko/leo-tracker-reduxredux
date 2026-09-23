#!/usr/bin/env python3
"""Create an outcome-free random split of fixed two-hour scan groups."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

PARTITIONS = ("train", "validation", "test")
TARGET_FRACTIONS = {"train": 0.60, "validation": 0.20, "test": 0.20}
GROUP_SECONDS = 2 * 60 * 60
NOMINAL_CAPTURE_SECONDS = 300


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def group_scans(scans: list[dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for scan in scans:
        captured = datetime.fromisoformat(scan["captured_at"].replace("Z", "+00:00"))
        bucket = int(captured.timestamp()) // GROUP_SECONDS
        # A capture crossing a fixed boundary could leak overlapping evidence.
        # The frozen 113-scan corpus has none; fail rather than silently split it.
        final_sample = captured + timedelta(seconds=scan["nominal_capture_seconds"])
        if int((final_sample.timestamp() - 1e-6) // GROUP_SECONDS) != bucket:
            raise ValueError(f"capture crosses a group boundary: {scan['session_id']}")
        grouped.setdefault(bucket, []).append(scan)
    result = []
    for bucket, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: (row["captured_at"], row["session_id"]))
        start = datetime.fromtimestamp(bucket * GROUP_SECONDS, UTC)
        result.append(
            {
                "group_id": start.strftime("utc2h-%Y%m%dT%H00Z"),
                "interval_start": start.isoformat().replace("+00:00", "Z"),
                "interval_end_exclusive": datetime.fromtimestamp((bucket + 1) * GROUP_SECONDS, UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "session_count": len(rows),
                "session_ids": [row["session_id"] for row in rows],
            }
        )
    return result


def assign_groups(groups: list[dict], seed: int) -> dict[str, list[dict]]:
    """Find the closest whole-group 60/20/20 allocation; seed breaks ties."""
    ordered = list(groups)
    rng = random.Random(seed)
    rng.shuffle(ordered)
    branch_order = list(PARTITIONS)
    rng.shuffle(branch_order)
    # State is (train scans, validation scans) -> assignment in shuffled group order.
    states: dict[tuple[int, int], tuple[str, ...]] = {(0, 0): ()}
    for group in ordered:
        size = group["session_count"]
        following = {}
        for (train_count, validation_count), assignment in states.items():
            for partition in branch_order:
                key = (
                    train_count + (size if partition == "train" else 0),
                    validation_count + (size if partition == "validation" else 0),
                )
                following.setdefault(key, assignment + (partition,))
        states = following
    total = sum(group["session_count"] for group in groups)

    def objective(item):
        (train_count, validation_count), assignment = item
        counts = {
            "train": train_count,
            "validation": validation_count,
            "test": total - train_count - validation_count,
        }
        empty = any(counts[name] == 0 for name in PARTITIONS)
        deviation = sum(abs(counts[name] - TARGET_FRACTIONS[name] * total) for name in PARTITIONS)
        return empty, deviation, assignment

    _, assignment = min(states.items(), key=objective)
    result = {name: [] for name in PARTITIONS}
    for group, partition in zip(ordered, assignment, strict=True):
        result[partition].append(group)
    for rows in result.values():
        rows.sort(key=lambda row: row["interval_start"])
    return result


def build_manifest(source: dict, inventory: dict, source_digest: str, seed: int) -> dict:
    source_ids = (
        source["partitions"]["training"]["session_ids"]
        + source["partitions"]["development_validation"]["session_ids"]
    )
    if len(source_ids) != 113 or len(set(source_ids)) != 113:
        raise ValueError("expected exactly 113 unique historically exposed scans")
    excluded = set(source["partitions"]["embargo_quarantine"]["session_ids"])
    excluded.update(source["partitions"]["test_embargo_quarantine"]["session_ids"])
    excluded.update(source["partitions"]["prospective_test_reserve"]["session_ids"])
    if set(source_ids) & excluded:
        raise ValueError("source scans overlap an excluded or unopened partition")
    authority = {row["session_id"]: row for row in inventory["scans"]}
    if set(source_ids) - authority.keys():
        raise ValueError("inventory does not cover every source scan")
    scans = [
        {
            "session_id": session,
            "captured_at": authority[session]["captured_at"],
            "nominal_capture_seconds": NOMINAL_CAPTURE_SECONDS,
        }
        for session in source_ids
    ]
    groups = group_scans(scans)
    assigned = assign_groups(groups, seed)
    partitions = {}
    for name in PARTITIONS:
        ids = [session for group in assigned[name] for session in group["session_ids"]]
        partitions[name] = {
            "group_ids": [group["group_id"] for group in assigned[name]],
            "session_count": len(ids),
            "session_ids": ids,
        }
    return {
        "schema": "position-random-group-split/v1",
        "created_without_position_outcomes": True,
        "retrospective_audit_only": True,
        "historical_exposure": (
            "all 113 scans were exposed by earlier work; test is not untouched"
        ),
        "source_manifest_sha256": source_digest,
        "seed": seed,
        "target_fractions": TARGET_FRACTIONS,
        "group_policy": {
            "duration_seconds": GROUP_SECONDS,
            "anchor": "Unix epoch UTC",
            "membership": "floor(captured_at_unix_seconds / 7200)",
            "nominal_capture_seconds": NOMINAL_CAPTURE_SECONDS,
            "boundary_rule": (
                "fail manifest generation if a nominal capture interval crosses a "
                "two-hour boundary; no source capture crosses one"
            ),
            "assignment": (
                "seeded shuffle of whole groups, then exact dynamic programming for "
                "minimum total absolute scan-count deviation from 60/20/20; seeded "
                "order resolves ties"
            ),
        },
        "source_scan_count": len(source_ids),
        "groups": groups,
        "partitions": partitions,
        "excluded_source_partitions": [
            "embargo_quarantine",
            "test_embargo_quarantine",
            "prospective_test_reserve",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260923)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    document = build_manifest(
        json.loads(args.source.read_text()),
        json.loads(args.inventory.read_text()),
        sha256(args.source),
        args.seed,
    )
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload)


if __name__ == "__main__":
    main()
