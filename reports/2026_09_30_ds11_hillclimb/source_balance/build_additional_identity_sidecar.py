"""Emit physical candidate identities for an explicit additional-input plan."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records

    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text())
    archive = TleArchiveReader(args.tle_root)
    references = archive.list_snapshots()
    by_digest = {}
    for reference in references:
        by_digest.setdefault("sha256:" + reference.sha256, []).append(reference)
    rosters, scans = {}, {}
    for index, entry in enumerate(plan["inputs"]):
        artifacts = entry["artifacts"]
        observation = Path(next(row["path"] for row in artifacts if row["kind"] == "observations"))
        manifest_path = Path(next(
            row["path"] for row in artifacts
            if row["kind"] == "candidates" and row["path"].endswith(".json")
        ))
        bank_path = Path(next(
            row["path"] for row in artifacts
            if row["kind"] == "candidates" and row["path"].endswith(".npz")
        ))
        manifest = json.loads(manifest_path.read_text())
        snapshot = manifest["baseline_snapshot_sha256"]
        if snapshot not in rosters:
            matches = by_digest.get(snapshot, [])
            if not matches:
                raise ValueError(f"archived snapshot unavailable: {snapshot}")
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
                ids = bank[f"candidate_ids_{row['index']}"].astype(int).tolist()
                if (len(ids) != row["candidate_count"] or len(set(ids)) != len(ids) or
                        any(value < 0 or value >= len(numbers) for value in ids)):
                    raise ValueError("invalid candidate catalogue rows")
                tracks[row["track_id"]] = {
                    "candidate_ids": ids,
                    "candidate_norad": [numbers[value] for value in ids],
                }
        scans[str(index)] = {
            "session_id": entry["session_id"],
            "snapshot_sha256": snapshot,
            "catalogue_size": len(numbers),
            "observation_sha256": digest(observation),
            "manifest_sha256": digest(manifest_path),
            "bank_sha256": digest(bank_path),
            "tracks": tracks,
        }
    print(json.dumps({
        "schema": "ds11-source-balance-additional-identities/v1",
        "meaning": "bank candidate_ids rows mapped to physical NORAD identities",
        "plan_path": str(plan_path),
        "plan_sha256": digest(plan_path),
        "scans": scans,
    }, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
