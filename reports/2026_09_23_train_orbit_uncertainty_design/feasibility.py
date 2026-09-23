#!/usr/bin/env python3
"""Inventory distinct earlier causal elements for the first six TRAIN scans."""

import argparse
import hashlib
import json
from pathlib import Path

from leo.analysis.catalogue_prediction import element_pair_digest
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records, parse_element_sets

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json"
PARENT = ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json"
METADATA = Path("/tmp/leo-train-rx-metadata.json")
MAXIMUM_HISTORY_S = 72 * 3600


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def record_map(reader, reference, wanted):
    return {
        row.satellite_number: row
        for row in parse_element_set_records(reader.read(reference))
        if row.satellite_number in wanted
    }


def element_epoch(record):
    return parse_element_sets(record.text).element_epoch_utc_ns()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh output required")
    inventory = json.loads(INVENTORY.read_text())["partitions"]
    session_ids = inventory["train"]["session_ids"][:6]
    parent = json.loads(PARENT.read_text())
    arm = next(
        row for row in parent["arms"] if row["prior"] == "sacramento" and row["scale_s"] == 5.0
    )
    fixed = {
        sid: sorted(
            {int(row["candidate_id"]) for row in arm["fixed_tracks"] if row["session_id"] == sid}
        )
        for sid in session_ids
    }
    metadata = {row["session_id"]: row for row in json.loads(METADATA.read_text())["sessions"]}
    reader = TleArchiveReader(args.tle_root)
    snapshots = reader.list_snapshots()
    by_identity = {(row.digest, row.collected_utc_ns): row for row in snapshots}
    output_rows = []
    snapshot_digests = set()
    for sid in session_ids:
        meta = metadata[sid]
        baseline = by_identity[
            (meta["tle_snapshot_digest"], meta["tle_snapshot_collected_utc_ns"])
        ]
        cutoff = min(track["support_start_utc_ns"] for track in meta["tracks"]) - 505_000_000_000
        if not baseline.collected_utc_ns < cutoff:
            raise ValueError(f"non-causal baseline: {sid}")
        wanted = set(fixed[sid])
        current = record_map(reader, baseline, wanted)
        earlier = [
            row
            for row in snapshots
            if row.collected_utc_ns < baseline.collected_utc_ns
            and baseline.collected_utc_ns - row.collected_utc_ns <= MAXIMUM_HISTORY_S * 1e9
        ]
        history = {number: {} for number in wanted}
        for reference in earlier:
            records = record_map(reader, reference, wanted)
            snapshot_digests.add(reference.digest)
            for number, record in records.items():
                epoch = element_epoch(record)
                if epoch >= cutoff:
                    continue
                item_digest = element_pair_digest(record.first_line, record.second_line)
                current_digest = element_pair_digest(
                    current[number].first_line, current[number].second_line
                )
                if item_digest != current_digest:
                    history[number].setdefault(
                        item_digest,
                        {
                            "element_epoch_utc_ns": epoch,
                            "nearest_collection_utc_ns": reference.collected_utc_ns,
                        },
                    )
        for number in fixed[sid]:
            current_record = current[number]
            distinct = list(history[number].values())
            output_rows.append(
                {
                    "session_id": sid,
                    "candidate_id": str(number),
                    "current_element_epoch_utc_ns": element_epoch(current_record),
                    "current_element_age_s": (cutoff - element_epoch(current_record)) / 1e9,
                    "distinct_earlier_element_count": len(distinct),
                    "earlier_element_epoch_age_s": sorted(
                        (cutoff - row["element_epoch_utc_ns"]) / 1e9 for row in distinct
                    ),
                }
            )
        snapshot_digests.add(baseline.digest)
    counts = [row["distinct_earlier_element_count"] for row in output_rows]
    result = {
        "schema": "leo.train_orbit_uncertainty_feasibility.v1",
        "scope": {"partition": "TRAIN", "session_ids": session_ids, "history_hours": 72},
        "coverage": {
            "fixed_candidate_occurrences": len(output_rows),
            "with_at_least_one_distinct_earlier_element": sum(value >= 1 for value in counts),
            "with_at_least_two_distinct_earlier_elements": sum(value >= 2 for value in counts),
            "minimum_distinct_earlier_elements": min(counts),
            "median_distinct_earlier_elements": sorted(counts)[len(counts) // 2],
            "maximum_distinct_earlier_elements": max(counts),
        },
        "rows": output_rows,
        "bindings": {
            "tool": digest(Path(__file__)),
            "inventory": digest(INVENTORY),
            "fixed_parent": digest(PARENT),
            "strict_metadata": digest(METADATA),
            "archive_snapshot_digests": sorted(snapshot_digests),
        },
        "reference_position_used": False,
        "validation_or_test_used": False,
        "future_tle_used": False,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
