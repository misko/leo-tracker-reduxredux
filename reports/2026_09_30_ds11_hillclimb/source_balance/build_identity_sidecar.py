"""Build the read-only DS11 bank-row to physical-NORAD identity sidecar.

This adapter is intentionally separate from ``model.py``.  It reads the TLE
archive only to recover the immutable catalogue row ordering used by each
exported bank, and emits no RF or production state changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records

    parser = argparse.ArgumentParser()
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()

    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    archive = TleArchiveReader(args.tle_root)
    references = archive.list_snapshots()
    by_digest = {}
    for reference in references:
        by_digest.setdefault("sha256:" + reference.sha256, []).append(reference)

    rosters = {}
    scans = {}
    for index, entry in enumerate(plan["inputs"]):
        manifest_path = Path(next(
            artifact["path"] for artifact in entry["artifacts"]
            if artifact["kind"] == "candidates" and artifact["path"].endswith(".json")
        ))
        bank_path = Path(next(
            artifact["path"] for artifact in entry["artifacts"]
            if artifact["kind"] == "candidates" and artifact["path"].endswith(".npz")
        ))
        observation_path = Path(next(
            artifact["path"] for artifact in entry["artifacts"]
            if artifact["kind"] == "observations"
        ))
        manifest = json.loads(manifest_path.read_text())
        snapshot = manifest["baseline_snapshot_sha256"]
        if snapshot not in rosters:
            matches = by_digest.get(snapshot, [])
            if not matches:
                raise ValueError(f"archived snapshot unavailable: {snapshot}")
            # Equal bytes imply equal row identities; use the earliest stable ref.
            reference = min(matches, key=lambda row: (row.collected_utc_ns, row.provider))
            payload = archive.read(reference)
            if "sha256:" + hashlib.sha256(payload.encode()).hexdigest() != snapshot:
                raise ValueError("archive payload digest mismatch")
            filtered, _ = exclude_labelled_starlink_debris(payload)
            numbers = [int(row.satellite_number) for row in parse_element_set_records(filtered)]
            if len(numbers) != manifest["catalogue_size"] or len(set(numbers)) != len(numbers):
                raise ValueError("catalogue roster size or NORAD uniqueness mismatch")
            rosters[snapshot] = numbers
        numbers = rosters[snapshot]
        tracks = {}
        with np.load(bank_path, allow_pickle=False) as bank:
            for row in manifest["tracks"]:
                candidate_ids = bank[f"candidate_ids_{row['index']}"].astype(int).tolist()
                if (len(candidate_ids) != row["candidate_count"] or
                        len(set(candidate_ids)) != len(candidate_ids) or
                        any(value < 0 or value >= len(numbers) for value in candidate_ids)):
                    raise ValueError("invalid candidate bank catalogue rows")
                tracks[row["track_id"]] = {
                    "candidate_ids": candidate_ids,
                    "candidate_norad": [numbers[value] for value in candidate_ids],
                }
        scans[str(index)] = {
            "session_id": entry["session_id"],
            "snapshot_sha256": snapshot,
            "catalogue_size": len(numbers),
            "observation_sha256": digest(observation_path),
            "manifest_sha256": digest(manifest_path),
            "bank_sha256": digest(bank_path),
            "tracks": tracks,
        }
    result = {
        "schema": "ds11-source-balance-identities/v1",
        "meaning": "bank candidate_ids are catalogue rows; candidate_norad is the physical NORAD mapping",
        "plan_sha256": digest(plan_path),
        "scans": scans,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
