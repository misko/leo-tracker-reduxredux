"""Assemble bound confirmation inputs, physical identities and update coverage."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
HILL = HERE.parent
EXPORT_PLAN = HERE / "export-plan.json"
PLAN = HERE / "plan.json"
SIDECAR = HERE / "catalogue_identities.json"
ELIGIBILITY = HERE / "eligibility.json"
INVENTORY = HILL / "remaining43_causal_inventory/inventory.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def meaningful(rows):
    return {
        int(row["norad"]): row
        for row in rows
        if row["changed_sgp4_inputs"] and row["selected_epoch_ns"] > row["original_epoch_ns"]
    }


def intersect_tracks(tracks: dict, changes: dict[int, dict], kind: str):
    rows = []
    for track_id, track in tracks.items():
        slots = [slot for slot, norad in enumerate(track["candidate_norad"]) if int(norad) in changes]
        if not slots:
            continue
        rows.append({
            "track_id": track_id,
            "index": int(track["index"]),
            "slots": slots,
            "candidate_ids": [track["candidate_ids"][slot] for slot in slots],
            "norads": [track["candidate_norad"][slot] for slot in slots],
            "kind": kind,
        })
    return rows


def main():
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records

    export_plan = json.loads(EXPORT_PLAN.read_text())
    inventory = json.loads(INVENTORY.read_text())
    inputs = []
    terminal_paths = []
    for slot, capture in enumerate(export_plan["captures"]):
        index = capture["full_manifest_index"]
        receipt_path = HERE / f"export_{index:02d}.receipt.json"
        validated_path = HERE / "exports" / f"{index:02d}" / "validated.json"
        receipt = json.loads(receipt_path.read_text())
        validated = json.loads(validated_path.read_text())
        if (receipt["exit_code"] != 0 or receipt["slot"] != slot
                or receipt["full_manifest_index"] != index):
            raise ValueError(f"export receipt not successful for {index}")
        if receipt["source_sha256"] != digest(HERE / "export.py"):
            raise ValueError("export receipt source binding mismatch")
        if receipt["log_sha256"] != digest(HERE / f"export_{index:02d}.log"):
            raise ValueError("export log binding mismatch")
        if validated["full_manifest_index"] != index or validated["slot"] != slot:
            raise ValueError("validated export index mismatch")
        entry = validated["input"]
        for artifact in entry["artifacts"]:
            if "sha256:" + digest(artifact["path"]) != artifact["sha256"]:
                raise ValueError("exported artifact digest mismatch")
        inputs.append(entry)
        terminal_paths += [receipt_path, HERE / f"export_{index:02d}.log", validated_path]
    if len(inputs) != 5:
        raise ValueError("confirmation export is incomplete")
    plan = {
        "schema": "ds11-causal-fresh-confirmation-inputs/v1",
        "config": export_plan["config"],
        "inputs": inputs,
        "source_sha256": {
            str(path.resolve()): digest(path)
            for path in [Path(__file__), EXPORT_PLAN, HERE / "PROTOCOL.md", HERE / "export.py",
                         INVENTORY, *terminal_paths]
        },
    }
    with PLAN.open("x") as stream:
        json.dump(plan, stream, indent=2)

    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    references = archive.list_snapshots()
    by_digest = {}
    for reference in references:
        by_digest.setdefault(reference.digest, []).append(reference)
    rosters, scans = {}, {}
    for slot, entry in enumerate(inputs):
        observation_path = Path(next(row["path"] for row in entry["artifacts"] if row["kind"] == "observations"))
        manifest_path = Path(next(row["path"] for row in entry["artifacts"]
                                  if row["kind"] == "candidates" and row["path"].endswith(".json")))
        bank_path = Path(next(row["path"] for row in entry["artifacts"]
                              if row["kind"] == "candidates" and row["path"].endswith(".npz")))
        manifest = json.loads(manifest_path.read_text())
        snapshot = manifest["baseline_snapshot_sha256"]
        if snapshot not in rosters:
            matches = by_digest.get(snapshot, [])
            if not matches:
                raise ValueError(f"archived baseline snapshot unavailable: {snapshot}")
            reference = min(matches, key=lambda row: (row.collected_utc_ns, row.provider))
            payload = archive.read(reference)
            filtered, _ = exclude_labelled_starlink_debris(payload)
            numbers = [int(row.satellite_number) for row in parse_element_set_records(filtered)]
            if len(numbers) != manifest["catalogue_size"] or len(set(numbers)) != len(numbers):
                raise ValueError("catalogue roster mismatch")
            rosters[snapshot] = numbers
        numbers = rosters[snapshot]
        tracks = {}
        with np.load(bank_path, allow_pickle=False) as bank:
            for row in manifest["tracks"]:
                candidate_ids = bank[f"candidate_ids_{row['index']}"].astype(int).tolist()
                if (len(candidate_ids) != row["candidate_count"]
                        or len(set(candidate_ids)) != len(candidate_ids)
                        or any(value < 0 or value >= len(numbers) for value in candidate_ids)):
                    raise ValueError("invalid bank candidate rows")
                tracks[row["track_id"]] = {
                    "index": int(row["index"]),
                    "candidate_ids": candidate_ids,
                    "candidate_norad": [numbers[value] for value in candidate_ids],
                }
        scans[str(slot)] = {
            "full_manifest_index": int(entry["full_manifest_index"]),
            "session_id": entry["session_id"],
            "snapshot_sha256": snapshot,
            "catalogue_size": len(numbers),
            "observation_sha256": digest(observation_path),
            "manifest_sha256": digest(manifest_path),
            "bank_sha256": digest(bank_path),
            "tracks": tracks,
        }
    sidecar = {
        "schema": "ds11-causal-fresh-confirmation-identities/v1",
        "meaning": "bank catalogue rows mapped to physical NORAD identities",
        "plan_path": str(PLAN.resolve()),
        "plan_sha256": digest(PLAN),
        "scans": scans,
    }
    with SIDECAR.open("x") as stream:
        json.dump(sidecar, stream, sort_keys=True, separators=(",", ":"))

    comparison_by_index = {row["full_manifest_index"]: row for row in inventory["comparisons"]}
    coverage = []
    for slot, scan in scans.items():
        index = scan["full_manifest_index"]
        comparison = comparison_by_index[index]
        direct = meaningful(comparison["three_day_best_capture_vs_three_day_best_guard"]["changes"])
        retention = meaningful(comparison["three_day_best_at_guard_vs_latest_provider_guard"]["changes"])
        combined = meaningful(comparison["three_day_best_capture_vs_latest_provider_guard"]["changes"])
        if set(combined) != set(direct) | set(retention):
            raise ValueError("combined metadata changes differ from direct plus retention")
        direct_tracks = intersect_tracks(scan["tracks"], direct, "capture_window")
        retention_tracks = intersect_tracks(scan["tracks"], retention, "guard_retention")
        bank_norads = {
            int(value) for track in scan["tracks"].values() for value in track["candidate_norad"]
        }
        coverage.append({
            "slot": int(slot),
            "full_manifest_index": index,
            "session_id": scan["session_id"],
            "metadata": {
                "capture_window_newer_records": len(direct),
                "guard_retention_newer_records": len(retention),
                "combined_newer_records": len(combined),
            },
            "bank_intersection": {
                "capture_window_unique_norads": len(set(direct) & bank_norads),
                "capture_window_tracks": len(direct_tracks),
                "capture_window_slots": sum(len(row["slots"]) for row in direct_tracks),
                "guard_retention_unique_norads": len(set(retention) & bank_norads),
                "guard_retention_tracks": len(retention_tracks),
                "guard_retention_slots": sum(len(row["slots"]) for row in retention_tracks),
            },
            "capture_window_tracks": direct_tracks,
            "guard_retention_tracks": retention_tracks,
            "change_records": {
                "capture_window": list(direct.values()),
                "guard_retention": list(retention.values()),
            },
            "completion_proof": [row for row in inventory["completion_proof"]["qualified_snapshots"]
                                 if row["full_manifest_index"] == index],
        })
    result = {
        "schema": "ds11-causal-fresh-confirmation-eligibility/v1",
        "status": "bank intersection only; no position fits",
        "plan_sha256": digest(PLAN),
        "identity_sidecar_sha256": digest(SIDECAR),
        "inventory_sha256": digest(INVENTORY),
        "summary": {
            "scans": len(coverage),
            "capture_window_metadata_records": sum(row["metadata"]["capture_window_newer_records"] for row in coverage),
            "capture_window_unique_norad_scan_occasions": sum(row["bank_intersection"]["capture_window_unique_norads"] for row in coverage),
            "capture_window_affected_tracks": sum(row["bank_intersection"]["capture_window_tracks"] for row in coverage),
            "capture_window_updated_slots": sum(row["bank_intersection"]["capture_window_slots"] for row in coverage),
            "guard_retention_metadata_records": sum(row["metadata"]["guard_retention_newer_records"] for row in coverage),
            "guard_retention_unique_norad_scan_occasions": sum(row["bank_intersection"]["guard_retention_unique_norads"] for row in coverage),
            "guard_retention_affected_tracks": sum(row["bank_intersection"]["guard_retention_tracks"] for row in coverage),
            "guard_retention_updated_slots": sum(row["bank_intersection"]["guard_retention_slots"] for row in coverage),
        },
        "scans": coverage,
        "source_sha256": {
            str(path.resolve()): digest(path)
            for path in [Path(__file__), PLAN, SIDECAR, INVENTORY]
        },
        "runtime_sha256": {
            str(Path(inspect.getfile(value))): digest(inspect.getfile(value))
            for value in (TleArchiveReader, parse_element_set_records)
        },
    }
    with ELIGIBILITY.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
