#!/usr/bin/env python3
"""Build bound, slot-preserving state-array patches from proven causal TLEs."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records, parse_element_sets


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HILL = HERE.parent
BASE = HILL.parent / "2026_09_30_ds11_single10"
PLAN = BASE / "plan.json"
INVENTORY = HILL / "causal_orbit_inventory" / "inventory.json"
SEED = HILL / "delayed_orbit_inventory" / "inventory.json"
IDENTITIES = HILL / "source_balance" / "catalogue_identities.json"
PROOF = HILL / "orbit_age_audit" / "capture-start-completion-proof.json"
PATCHES = HERE / "patches"
ALLOWED = (10, 13, 16, 27, 31)
POSITION_TOLERANCE_KM = 1e-8
VELOCITY_TOLERANCE_KM_S = 1e-10


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def element_digest(record) -> str:
    payload = f"{record.first_line}\n{record.second_line}\n".encode()
    return hashlib.sha256(payload).hexdigest()


def validate_bound_hashes(document: dict, base: Path) -> list[Path]:
    paths = []
    for name, expected in document.get("source_sha256", {}).items():
        path = Path(name)
        if not path.is_absolute():
            path = (base / path).resolve()
        if digest(path) != expected.removeprefix("sha256:"):
            raise ValueError(f"source digest mismatch: {path}")
        paths.append(path)
    return paths


def validate_proof(row: dict, scan: dict, inventory_rows: list[dict]) -> dict:
    if not row.get("qualified"):
        raise ValueError("capture-start completion proof is not qualified")
    if row.get("index") != scan.get("index") or row.get("session") != scan.get("session"):
        raise ValueError("completion proof scan binding mismatch")
    if row.get("capture_start_utc_ns") != scan.get("start_utc_ns"):
        raise ValueError("completion proof capture-start mismatch")
    publication_ns = round(float(row["journal_published_unix_s"]) * 1e9)
    if publication_ns >= int(scan["start_utc_ns"]):
        raise ValueError("selected snapshot was not published before capture")
    changed = [item for item in inventory_rows if item["changed"]]
    if int(row["changed_candidate_count"]) != len(changed):
        raise ValueError("completion proof changed-candidate count mismatch")
    selected = {item["selected_snapshot"] for item in changed}
    expected = "sha256:" + row["snapshot_sha256"]
    if selected != {expected}:
        raise ValueError("completion proof selected-snapshot mismatch")
    return {
        "provider": row["provider"],
        "collected_utc_ns": int(row["snapshot_collected_utc_ns"]),
        "sha256": row["snapshot_sha256"],
        "archive_path": row["archive_path"],
        "journal_published_unix_s": float(row["journal_published_unix_s"]),
        "journal_published_utc_ns": publication_ns,
        "qualified": True,
    }


def changed_slots(candidate_ids, norads, changed: dict[int, dict]) -> np.ndarray:
    candidate_ids = np.asarray(candidate_ids, dtype=np.int64)
    norads = np.asarray(norads, dtype=np.int64)
    if candidate_ids.ndim != 1 or norads.shape != candidate_ids.shape:
        raise ValueError("candidate identity mapping shape mismatch")
    if len(set(candidate_ids.tolist())) != len(candidate_ids):
        raise ValueError("duplicate candidate IDs in one track")
    if len(set(norads.tolist())) != len(norads):
        raise ValueError("duplicate physical identities in one track")
    return np.flatnonzero(np.isin(norads, np.asarray(sorted(changed), dtype=np.int64)))


def replay_error(actual_position, actual_velocity, saved_position, saved_velocity):
    if actual_position.shape != saved_position.shape or actual_velocity.shape != saved_velocity.shape:
        raise ValueError("old-state replay shape mismatch")
    if not all(
        np.isfinite(value).all()
        for value in (actual_position, actual_velocity, saved_position, saved_velocity)
    ):
        raise ValueError("old-state replay contains nonfinite values")
    position = float(np.max(np.abs(actual_position - saved_position), initial=0.0))
    velocity = float(np.max(np.abs(actual_velocity - saved_velocity), initial=0.0))
    if position > POSITION_TOLERANCE_KM or velocity > VELOCITY_TOLERANCE_KM_S:
        raise ValueError(
            f"old-state replay failed: position={position}, velocity={velocity}"
        )
    return position, velocity


def catalogue(records) -> object:
    text = "".join(
        f"0 {record.name}\n{record.first_line}\n{record.second_line}\n"
        for record in records
    )
    return parse_element_sets(text)


def prepare(index: int, *, output_dir: Path = PATCHES, archive_root: Path = Path("/var/lib/leo/tle")):
    if index not in ALLOWED:
        raise ValueError(f"index must be one of {ALLOWED}")
    plan = json.loads(PLAN.read_text())
    inventory = json.loads(INVENTORY.read_text())
    seed = json.loads(SEED.read_text())
    identities = json.loads(IDENTITIES.read_text())
    proof = json.loads(PROOF.read_text())
    if inventory.get("schema") != "ds11-causal-orbit-availability/v1":
        raise ValueError("causal inventory schema mismatch")
    if proof.get("schema") != "ds11-capture-start-snapshot-completion-proof/v1":
        raise ValueError("completion proof schema mismatch")
    bound_paths = validate_bound_hashes(inventory, INVENTORY.parent)
    bound_paths += validate_bound_hashes(proof, PROOF.parent)
    if identities.get("plan_sha256") != digest(PLAN):
        raise ValueError("identity sidecar plan binding mismatch")

    entry = plan["inputs"][index]
    observation_path = Path(next(a["path"] for a in entry["artifacts"] if a["kind"] == "observations"))
    candidate_paths = [Path(a["path"]) for a in entry["artifacts"] if a["kind"] == "candidates"]
    manifest_path = next(path for path in candidate_paths if path.suffix == ".json")
    bank_path = next(path for path in candidate_paths if path.suffix == ".npz")
    for artifact in entry["artifacts"]:
        if "sha256:" + digest(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("plan artifact digest mismatch")
    observations = json.loads(observation_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    if observations["session_id"] != entry["session_id"] or manifest["session_id"] != entry["session_id"]:
        raise ValueError("input session mismatch")

    scan = next(s for s in inventory["scans"] if s["index"] == index and s["stage"] == "capture_start")
    seed_scan = next(s for s in seed["scans"] if s["index"] == index)
    proof_row = next(s for s in proof["scans"] if s["index"] == index)
    proof_audit = validate_proof(proof_row, scan, scan["candidates"])
    if scan["session"] != entry["session_id"] or observations["start_utc_ns"] != scan["start_utc_ns"]:
        raise ValueError("inventory input binding mismatch")

    reader = TleArchiveReader(archive_root)
    refs = reader.list_snapshots()
    proof_path = Path(proof_audit["archive_path"])
    selected_ref = next(
        (
            ref for ref in refs
            if ref.path == proof_path
            and ref.provider == proof_audit["provider"]
            and ref.collected_utc_ns == proof_audit["collected_utc_ns"]
            and ref.sha256 == proof_audit["sha256"]
        ),
        None,
    )
    if selected_ref is None or digest(proof_path) != proof_audit["sha256"]:
        raise ValueError("proven selected archive occurrence is unavailable or changed")
    by_digest = {}
    for ref in refs:
        by_digest.setdefault(ref.digest, ref)
    record_cache = {}

    def records(ref):
        key = str(ref.path)
        if key not in record_cache:
            parsed = parse_element_set_records(reader.read(ref))
            mapping = {row.satellite_number: row for row in parsed}
            if len(mapping) != len(parsed):
                raise ValueError("duplicate physical identity in snapshot")
            record_cache[key] = mapping
        return record_cache[key]

    fresh_records = records(selected_ref)
    changed = {int(row["norad"]): row for row in scan["candidates"] if row["changed"]}
    old_rows = {int(row["norad"]): row for row in seed_scan["candidates"]}
    if set(changed) - set(old_rows):
        raise ValueError("changed identity absent from original inventory")
    for norad, row in changed.items():
        fresh = fresh_records.get(norad)
        if fresh is None or element_digest(fresh) != row["selected_element_sha256"]:
            raise ValueError("fresh element record mismatch")

    side_scan = identities["scans"][str(index)]
    if side_scan["session_id"] != entry["session_id"] or side_scan["bank_sha256"] != digest(bank_path):
        raise ValueError("identity sidecar bank binding mismatch")
    observation_tracks = {row["track_id"]: row for row in observations["tracks"]}
    banks = np.load(bank_path, allow_pickle=False)
    timing = np.asarray(banks["timing_grid_s"], dtype=float)
    if not np.array_equal(timing, np.asarray(plan["config"]["timing_grid_s"], dtype=float)):
        raise ValueError("timing grid mismatch")

    arrays, track_rows = {}, []
    position_error = velocity_error = 0.0
    for item in manifest["tracks"]:
        ti = int(item["index"])
        track_id = item["track_id"]
        track = observation_tracks[track_id]
        side = side_scan["tracks"][track_id]
        candidate_ids = np.asarray(banks[f"candidate_ids_{ti}"], dtype=np.int64)
        if not np.array_equal(candidate_ids, np.asarray(side["candidate_ids"], dtype=np.int64)):
            raise ValueError("candidate order differs from physical identity sidecar")
        norads = np.asarray(side["candidate_norad"], dtype=np.int64)
        slots = changed_slots(candidate_ids, norads, changed)
        if not len(slots):
            continue
        selected_norads = norads[slots]
        original_records = []
        replacement_records = []
        selected_shas = []
        for norad in selected_norads.tolist():
            old = old_rows[int(norad)]
            original_ref = by_digest.get(old["original_snapshot"])
            if original_ref is None:
                raise ValueError("original snapshot unavailable")
            original = records(original_ref).get(int(norad))
            if original is None or element_digest(original) != old["original_element_sha256"]:
                raise ValueError("original element record mismatch")
            original_records.append(original)
            replacement_records.append(fresh_records[int(norad)])
            selected_shas.append(changed[int(norad)]["selected_element_sha256"])
            bound_paths.append(original_ref.path)
        times = np.asarray(track["times_s"], dtype=float)
        original_catalogue = catalogue(original_records)
        replacement_catalogue = catalogue(replacement_records)
        expected_norads = tuple(map(int, selected_norads))
        if (tuple(original_catalogue.satellite_numbers) != expected_norads
                or tuple(replacement_catalogue.satellite_numbers) != expected_norads):
            raise ValueError("propagation catalogue physical identity order mismatch")
        old_position, old_velocity, old_valid = propagate_candidate_states(
            original_catalogue, range(len(slots)), observations["start_utc_ns"], times, timing
        )
        if not np.array_equal(old_valid, np.arange(len(slots))):
            raise ValueError("original exact record failed propagation")
        pe, ve = replay_error(
            old_position,
            old_velocity,
            banks[f"position_km_{ti}"][slots],
            banks[f"velocity_km_s_{ti}"][slots],
        )
        position_error, velocity_error = max(position_error, pe), max(velocity_error, ve)
        position, velocity, valid = propagate_candidate_states(
            replacement_catalogue, range(len(slots)), observations["start_utc_ns"], times, timing
        )
        if not np.array_equal(valid, np.arange(len(slots))):
            raise ValueError("fresh exact record failed propagation")
        skey, pkey, vkey = f"slots_{ti}", f"position_km_{ti}", f"velocity_km_s_{ti}"
        arrays[skey], arrays[pkey], arrays[vkey] = slots, position, velocity
        track_rows.append({
            "track_id": track_id,
            "index": ti,
            "slots_key": skey,
            "position_key": pkey,
            "velocity_key": vkey,
            "candidate_ids": candidate_ids[slots].tolist(),
            "norads": selected_norads.tolist(),
            "selected_element_sha256": selected_shas,
        })
    if not arrays:
        raise ValueError("affected scan produced no replacement slots")

    output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = output_dir / f"{index:02d}.npz"
    json_path = output_dir / f"{index:02d}.json"
    if npz_path.exists() or json_path.exists():
        raise FileExistsError(f"patch output already exists for index {index}")
    np.savez(npz_path, **arrays)
    runtime_paths = [
        Path(inspect.getfile(propagate_candidate_states)),
        Path(inspect.getfile(parse_element_sets)),
    ]
    source_paths = list(dict.fromkeys([
        Path(__file__), PLAN, INVENTORY, SEED, IDENTITIES, PROOF,
        observation_path, manifest_path, bank_path, selected_ref.path,
        *bound_paths, *runtime_paths,
    ]))
    result = {
        "schema": "ds11-causal-fresh-bank-patch/v1",
        "index": index,
        "session_id": entry["session_id"],
        "capture_start_utc_ns": int(observations["start_utc_ns"]),
        "selection_stage": "capture_start",
        "timing_grid_s": timing.tolist(),
        "selected_snapshot": {
            key: proof_audit[key]
            for key in ("provider", "collected_utc_ns", "sha256", "archive_path")
        },
        "proofs": [proof_audit],
        "source_sha256": {str(path): digest(path) for path in source_paths},
        "array": {"path": str(npz_path.resolve()), "sha256": digest(npz_path)},
        "replay": {
            "position_max_abs_km": position_error,
            "velocity_max_abs_km_s": velocity_error,
            "position_tolerance_km": POSITION_TOLERANCE_KM,
            "velocity_tolerance_km_s": VELOCITY_TOLERANCE_KM_S,
        },
        "counts": {
            "original_tracks": len(manifest["tracks"]),
            "patched_tracks": len(track_rows),
            "changed_candidate_records": len(changed),
            "replacement_candidate_occurrences": sum(len(row["norads"]) for row in track_rows),
        },
        "tracks": track_rows,
    }
    json_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=int, choices=ALLOWED)
    args = parser.parse_args()
    result = prepare(args.index)
    print(json.dumps({
        "index": result["index"],
        "patched_tracks": result["counts"]["patched_tracks"],
        "replacement_candidate_occurrences": result["counts"]["replacement_candidate_occurrences"],
        "replay": result["replay"],
    }, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
