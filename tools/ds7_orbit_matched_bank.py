#!/usr/bin/env python3
"""Rebuild only changed slots in a frozen DS7 candidate bank."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

try:
    from tools.ds7_orbit_inventory import ElementRecord, _raw_records
except ModuleNotFoundError:  # Direct ``python tools/...`` execution.
    from ds7_orbit_inventory import ElementRecord, _raw_records


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def select_records(reader, snapshots, cutoff: int, roster: set[int]):
    """Newest element epoch per roster object from bytes collected before cutoff."""
    selected: dict[int, ElementRecord] = {}
    for snapshot in snapshots:
        if snapshot.provider != "space-track" or snapshot.collected_utc_ns >= cutoff:
            continue
        for record in _raw_records(reader.read(snapshot), snapshot):
            if record.catalog_number not in roster:
                continue
            old = selected.get(record.catalog_number)
            key = (record.epoch_utc_ns, snapshot.collected_utc_ns, snapshot.sha256)
            if old is None or key > (
                old.epoch_utc_ns,
                old.source.collected_utc_ns,
                old.source.sha256,
            ):
                selected[record.catalog_number] = record
    return selected


def replace_rows(original: np.ndarray, replacements: np.ndarray, slots: list[int]) -> np.ndarray:
    result = original.copy()
    result[np.asarray(slots)] = replacements
    return result


def build(args) -> dict:
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    started = time.monotonic()
    tracks = json.loads(args.tracks.read_text())
    manifest = json.loads((args.baseline / "manifest.json").read_text())
    shortlists = json.loads((args.baseline / "shortlists.json").read_text())
    if manifest["tracks_sha256"] != sha256(args.tracks):
        raise ValueError("baseline manifest does not bind track export")
    archive = TleArchiveReader(args.tle_root)
    snapshots = archive.list_snapshots()
    baseline_ref = next(
        item
        for item in snapshots
        if item.digest == manifest["baseline_snapshot_sha256"]
        and item.collected_utc_ns
        == next(
            row["collected_utc_ns"]
            for row in manifest["provider_sources"]
            if row["provider"] == "space-track"
        )
        and item.provider == "space-track"
    )
    baseline_records = _raw_records(archive.read(baseline_ref), baseline_ref)
    if len(baseline_records) != manifest["catalogue_size"]:
        raise ValueError("baseline catalogue size differs from manifest")
    roster = {item.catalog_number for item in baseline_records}
    cutoff = int(tracks["start_utc_ns"]) - 505_000_000_000
    selected = select_records(archive, snapshots, cutoff, roster)
    if set(selected) != roster:
        raise ValueError("all-archive product lacks a baseline roster object")
    baseline_by_number = {item.catalog_number: item for item in baseline_records}
    changed_numbers = {
        number
        for number in roster
        if selected[number].element_sha256 != baseline_by_number[number].element_sha256
    }
    chosen = [selected[item.catalog_number] for item in baseline_records]
    catalogue = parse_element_sets(
        "".join(f"0 {item.name}\n{item.line1}\n{item.line2}\n" for item in chosen)
    )
    if tuple(catalogue.satellite_numbers) != tuple(
        item.catalog_number for item in baseline_records
    ):
        raise ValueError("matched product changed baseline roster order")

    old = np.load(args.baseline / "banks.npz", allow_pickle=False)
    arrays = {key: old[key].copy() for key in old.files}
    by_track = {item["track_id"]: item for item in tracks["tracks"]}
    changed_slots = []
    for item in manifest["tracks"]:
        index = item["index"]
        ids = arrays[f"candidate_ids_{index}"]
        expected = np.asarray(shortlists["shortlists"][item["track_id"]])
        if not np.array_equal(ids, expected):
            raise ValueError("baseline candidate ordering differs from shortlist")
        slots = [
            slot
            for slot, idx in enumerate(ids)
            if baseline_records[int(idx)].catalog_number in changed_numbers
        ]
        if not slots:
            continue
        changed_ids = ids[np.asarray(slots)]
        row = by_track[item["track_id"]]
        pos, vel, propagated = propagate_candidate_states(
            catalogue,
            changed_ids,
            tracks["start_utc_ns"],
            np.asarray(row["times_s"]),
            arrays["timing_grid_s"],
        )
        if not np.array_equal(propagated, changed_ids):
            raise ValueError("propagated candidate ordering changed")
        arrays[f"position_km_{index}"] = replace_rows(arrays[f"position_km_{index}"], pos, slots)
        arrays[f"velocity_km_s_{index}"] = replace_rows(
            arrays[f"velocity_km_s_{index}"], vel, slots
        )
        changed_slots.extend(
            {
                "track_index": index,
                "track_id": item["track_id"],
                "candidate_slot": slot,
                "catalogue_index": int(ids[slot]),
                "catalog_number": baseline_records[int(ids[slot])].catalog_number,
            }
            for slot in slots
        )

    args.output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.output / "banks.npz", **arrays)
    unchanged_arrays = []
    for key in old.files:
        if key.startswith(("position_km_", "velocity_km_s_")):
            track_index = int(key.rsplit("_", 1)[1])
            slots = [
                row["candidate_slot"] for row in changed_slots if row["track_index"] == track_index
            ]
            mask = np.ones(old[key].shape[0], dtype=bool)
            mask[slots] = False
            if not np.array_equal(old[key][mask], arrays[key][mask]):
                raise ValueError("unchanged bank rows differ")
        elif not np.array_equal(old[key], arrays[key]):
            raise ValueError("non-state bank array changed")
        unchanged_arrays.append(key)
    source_counts: dict[str, int] = {}
    for number in changed_numbers:
        digest = selected[number].source.digest
        source_counts[digest] = source_counts.get(digest, 0) + 1
    result = {
        **manifest,
        "schema": "ds7-orbit-matched-bank/v1",
        "baseline_manifest_sha256": sha256(args.baseline / "manifest.json"),
        "baseline_bank_sha256": sha256(args.baseline / "banks.npz"),
        "shortlists_sha256": sha256(args.baseline / "shortlists.json"),
        "cutoff_utc_ns": cutoff,
        "selection": (
            "newest element epoch over Space Track snapshots collected before "
            "start minus 505 seconds"
        ),
        "changed_roster_object_count": len(changed_numbers),
        "changed_roster_catalog_numbers": sorted(changed_numbers),
        "changed_candidate_slot_count": len(changed_slots),
        "changed_slots": changed_slots,
        "changed_source_snapshots": [
            {"sha256": digest, "changed_roster_object_count": source_counts[digest]}
            for digest in sorted(source_counts)
        ],
        "gap_snapshots": [
            {"collected_utc_ns": item.collected_utc_ns, "sha256": item.digest}
            for item in snapshots
            if item.provider == "space-track"
            and cutoff <= item.collected_utc_ns < int(tracks["start_utc_ns"])
        ],
        "bank_sha256": sha256(args.output / "banks.npz"),
        "unchanged_array_count": len(unchanged_arrays),
        "raw_iq_read_bytes": 0,
        "elapsed_seconds": time.monotonic() - started,
    }
    (args.output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.output / "shortlists.json").write_bytes((args.baseline / "shortlists.json").read_bytes())
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--tracks", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
