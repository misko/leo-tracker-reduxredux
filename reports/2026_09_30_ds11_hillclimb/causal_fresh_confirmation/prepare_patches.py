#!/usr/bin/env python3
"""Build slot-preserving confirmation patches from proven pre-capture TLE bytes.

This prepares candidate state arrays only.  It never evaluates a position
likelihood or reads reference positions.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
IDENTITIES = HERE / "catalogue_identities.json"
ELIGIBILITY = HERE / "eligibility.json"
INVENTORY = HERE.parent / "remaining43_causal_inventory/inventory.json"
PATCHES = HERE / "patches"
ALLOWED = (10, 18, 35, 60, 75)
POSITION_TOLERANCE_KM = 1e-8
VELOCITY_TOLERANCE_KM_S = 1e-10


def digest(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def element_digest(record) -> str:
    return hashlib.sha256(
        (record.first_line + "\n" + record.second_line + "\n").encode()
    ).hexdigest()


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


def normalize_proof(row: dict, *, index: int, session: str, capture_ns: int) -> dict:
    if (
        row.get("full_manifest_index") != index
        or row.get("session") != session
        or row.get("capture_start_utc_ns") != capture_ns
        or row.get("qualified") is not True
    ):
        raise ValueError("completion proof scan binding differs")
    collected = int(row["snapshot_collected_utc_ns"])
    published = int(row["journal_published_utc_ns"])
    if not collected < published < capture_ns:
        raise ValueError("completion proof is not strictly pre-capture")
    return {
        "provider": row["provider"],
        "collected_utc_ns": collected,
        "sha256": row["snapshot_sha256"].removeprefix("sha256:"),
        "archive_path": row["archive_path"],
        "journal_published_utc_ns": published,
        "qualified": True,
        "capture_start_utc_ns": capture_ns,
    }


def changed_slots(candidate_ids, norads, changed: dict[int, dict]) -> np.ndarray:
    candidate_ids = np.asarray(candidate_ids, dtype=np.int64)
    norads = np.asarray(norads, dtype=np.int64)
    if candidate_ids.ndim != 1 or candidate_ids.shape != norads.shape:
        raise ValueError("candidate identity mapping shape mismatch")
    if len(set(candidate_ids.tolist())) != len(candidate_ids):
        raise ValueError("duplicate candidate IDs in one track")
    if len(set(norads.tolist())) != len(norads):
        raise ValueError("duplicate physical NORADs in one track")
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
        raise ValueError(f"old-state replay failed: position={position}, velocity={velocity}")
    return position, velocity


def catalogue(records):
    from leo.sky.propagation import parse_element_sets

    text = "".join(
        f"0 {record.name}\n{record.first_line}\n{record.second_line}\n" for record in records
    )
    return parse_element_sets(text)


def artifact_paths(entry: dict) -> tuple[Path, Path, Path]:
    observations = [Path(row["path"]) for row in entry["artifacts"] if row["kind"] == "observations"]
    candidates = [Path(row["path"]) for row in entry["artifacts"] if row["kind"] == "candidates"]
    manifests = [path for path in candidates if path.suffix == ".json"]
    banks = [path for path in candidates if path.suffix == ".npz"]
    if len(observations) != 1 or len(manifests) != 1 or len(banks) != 1:
        raise ValueError("input artifact cardinality differs")
    return observations[0], manifests[0], banks[0]


def prepare(index: int, *, output_dir: Path = PATCHES, archive_root: Path = Path("/var/lib/leo/tle")):
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    if index not in ALLOWED:
        raise ValueError(f"index must be one of {ALLOWED}")
    plan = json.loads(PLAN.read_text())
    identities = json.loads(IDENTITIES.read_text())
    eligibility = json.loads(ELIGIBILITY.read_text())
    inventory = json.loads(INVENTORY.read_text())
    if plan.get("schema") != "ds11-causal-fresh-confirmation-inputs/v1":
        raise ValueError("confirmation plan schema differs")
    if identities.get("schema") != "ds11-causal-fresh-confirmation-identities/v1":
        raise ValueError("identity schema differs")
    if eligibility.get("schema") != "ds11-causal-fresh-confirmation-eligibility/v1":
        raise ValueError("eligibility schema differs")
    if inventory.get("schema") != "ds11-remaining43-causal-orbit-inventory/v1":
        raise ValueError("causal inventory schema differs")
    if identities.get("plan_path") != str(PLAN) or identities.get("plan_sha256") != digest(PLAN):
        raise ValueError("identity sidecar plan binding differs")
    if (
        eligibility.get("plan_sha256") != digest(PLAN)
        or eligibility.get("identity_sidecar_sha256") != digest(IDENTITIES)
        or eligibility.get("inventory_sha256") != digest(INVENTORY)
    ):
        raise ValueError("eligibility source binding differs")
    bound_paths = validate_bound_hashes(plan, PLAN.parent)
    bound_paths += validate_bound_hashes(eligibility, ELIGIBILITY.parent)
    bound_paths += validate_bound_hashes(inventory, INVENTORY.parent)

    matches = [(slot, row) for slot, row in enumerate(plan["inputs"]) if row["full_manifest_index"] == index]
    if len(matches) != 1:
        raise ValueError("confirmation index absent or duplicated")
    slot, entry = matches[0]
    side = identities["scans"].get(str(slot))
    eligible = next(
        (row for row in eligibility["scans"] if row["slot"] == slot and row["full_manifest_index"] == index),
        None,
    )
    comparison = next(
        (row for row in inventory["comparisons"] if row["full_manifest_index"] == index),
        None,
    )
    if side is None or eligible is None or comparison is None:
        raise ValueError("confirmation metadata row absent")
    if not (entry["session_id"] == side["session_id"] == eligible["session_id"] == comparison["session"]):
        raise ValueError("confirmation session binding differs")

    observation_path, manifest_path, bank_path = artifact_paths(entry)
    for artifact in entry["artifacts"]:
        if "sha256:" + digest(artifact["path"]) != artifact["sha256"]:
            raise ValueError(f"input artifact digest differs: {artifact['path']}")
    if (
        side["observation_sha256"] != digest(observation_path)
        or side["manifest_sha256"] != digest(manifest_path)
        or side["bank_sha256"] != digest(bank_path)
    ):
        raise ValueError("identity artifact binding differs")
    observations = json.loads(observation_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    capture_ns = int(observations["start_utc_ns"])
    if (
        observations["session_id"] != entry["session_id"]
        or manifest["session_id"] != entry["session_id"]
        or manifest["tracks_sha256"] != "sha256:" + digest(observation_path)
        or capture_ns != comparison["capture_start_utc_ns"]
    ):
        raise ValueError("export session, observation, or capture binding differs")

    change_section = comparison["three_day_best_capture_vs_latest_provider_guard"]
    changed = {int(row["norad"]): row for row in change_section["changes"]}
    if len(changed) != len(change_section["changes"]):
        raise ValueError("duplicate changed physical identity")
    proof_rows = [
        normalize_proof(row, index=index, session=entry["session_id"], capture_ns=capture_ns)
        for row in eligible["completion_proof"]
    ]
    proof_by_digest = {"sha256:" + row["sha256"]: row for row in proof_rows}
    if len(proof_by_digest) != len(proof_rows):
        raise ValueError("duplicate proof snapshot digest")

    reader = TleArchiveReader(archive_root)
    refs = reader.list_snapshots()
    refs_by_exact = {(ref.provider, ref.collected_utc_ns, ref.digest): ref for ref in refs}
    baseline_refs = {}
    for source in comparison["baseline_latest_provider_sources"]:
        key = (source["provider"], int(source["collected_utc_ns"]), source["digest"])
        ref = refs_by_exact.get(key)
        if ref is None:
            raise ValueError(f"exact baseline archive source absent: {key}")
        baseline_refs[ref.digest] = ref
    proven_refs = {}
    for proof in proof_rows:
        key = (proof["provider"], proof["collected_utc_ns"], "sha256:" + proof["sha256"])
        ref = refs_by_exact.get(key)
        if ref is None or str(ref.path) != proof["archive_path"]:
            raise ValueError(f"exact proven archive source absent: {key}")
        reader.read(ref)
        if digest(ref.path) != proof["sha256"]:
            raise ValueError("proven archive bytes differ")
        proven_refs[ref.digest] = ref

    record_cache = {}

    def records(ref):
        key = (ref.provider, ref.collected_utc_ns, ref.digest)
        if key not in record_cache:
            filtered, _ = exclude_labelled_starlink_debris(reader.read(ref))
            parsed = parse_element_set_records(filtered)
            mapping = {int(record.satellite_number): record for record in parsed}
            if len(mapping) != len(parsed):
                raise ValueError(f"duplicate NORAD in {ref.path}")
            record_cache[key] = mapping
        return record_cache[key]

    observation_tracks = {row["track_id"]: row for row in observations["tracks"]}
    manifest_tracks = {row["track_id"]: row for row in manifest["tracks"]}
    if len(observation_tracks) != len(observations["tracks"]) or len(manifest_tracks) != len(manifest["tracks"]):
        raise ValueError("duplicate observation or bank track identity")
    if set(observation_tracks) != set(manifest_tracks) or set(side["tracks"]) != set(manifest_tracks):
        raise ValueError("track set differs among export and identity sidecar")

    timing = np.asarray(plan["config"]["timing_grid_s"], dtype=float)
    arrays = {}
    track_rows = []
    record_audit = {}
    used_proofs = {}
    position_error = velocity_error = 0.0
    full_candidate_slots = training_count = held_count = 0
    with np.load(bank_path, allow_pickle=False) as banks:
        if not np.array_equal(np.asarray(banks["timing_grid_s"], dtype=float), timing):
            raise ValueError("bank timing grid differs from frozen plan")
        if sorted(row["index"] for row in manifest["tracks"]) != list(range(len(manifest["tracks"]))):
            raise ValueError("bank track indices are not complete and contiguous")
        for item in sorted(manifest["tracks"], key=lambda row: row["index"]):
            ti = int(item["index"])
            track_id = item["track_id"]
            track = observation_tracks[track_id]
            side_track = side["tracks"][track_id]
            if int(side_track["index"]) != ti:
                raise ValueError("identity sidecar track index differs")
            times = np.asarray(track["times_s"], dtype=float)
            mask_values = track["training_mask"]
            if len(mask_values) != len(times) or not all(isinstance(value, bool) for value in mask_values):
                raise ValueError("training mask shape or type differs")
            mask = np.asarray(mask_values, dtype=bool)
            training_count += int(mask.sum())
            held_count += int((~mask).sum())
            if int(item["observation_count"]) != len(times):
                raise ValueError("bank observation count differs")
            candidate_ids = np.asarray(banks[f"candidate_ids_{ti}"], dtype=np.int64)
            expected_ids = np.asarray(side_track["candidate_ids"], dtype=np.int64)
            norads = np.asarray(side_track["candidate_norad"], dtype=np.int64)
            if (
                not np.array_equal(candidate_ids, expected_ids)
                or len(candidate_ids) != int(item["candidate_count"])
                or candidate_ids.shape != norads.shape
            ):
                raise ValueError("full candidate order or physical identity binding differs")
            full_candidate_slots += len(candidate_ids)
            slots = changed_slots(candidate_ids, norads, changed)
            if not len(slots):
                continue
            original_records = []
            selected_records = []
            slot_audits = []
            for candidate_id, norad in zip(candidate_ids[slots].tolist(), norads[slots].tolist(), strict=True):
                change = changed[int(norad)]
                old_ref = baseline_refs.get(change["original_snapshot"])
                new_ref = proven_refs.get(change["selected_snapshot"])
                proof = proof_by_digest.get(change["selected_snapshot"])
                if old_ref is None:
                    raise ValueError("changed record is absent from exact baseline sources")
                if new_ref is None or proof is None:
                    raise ValueError("changed bank record lacks an exact completion proof")
                original = records(old_ref).get(int(norad))
                selected = records(new_ref).get(int(norad))
                if original is None or element_digest(original) != change["original_element_sha256"]:
                    raise ValueError("original exact element digest differs")
                if selected is None or element_digest(selected) != change["selected_element_sha256"]:
                    raise ValueError("selected exact element digest differs")
                original_records.append(original)
                selected_records.append(selected)
                audit = {
                    "candidate_id": int(candidate_id),
                    "norad": int(norad),
                    "original_snapshot": change["original_snapshot"],
                    "selected_snapshot": change["selected_snapshot"],
                    "original_element_sha256": change["original_element_sha256"],
                    "selected_element_sha256": change["selected_element_sha256"],
                }
                slot_audits.append(audit)
                record_audit[int(norad)] = {key: value for key, value in audit.items() if key != "candidate_id"}
                used_proofs[change["selected_snapshot"]] = proof

            original_catalogue = catalogue(original_records)
            selected_catalogue = catalogue(selected_records)
            expected_norads = tuple(map(int, norads[slots]))
            if (
                tuple(original_catalogue.satellite_numbers) != expected_norads
                or tuple(selected_catalogue.satellite_numbers) != expected_norads
            ):
                raise ValueError("propagation catalogue physical order differs")
            original_position, original_velocity, original_valid = propagate_candidate_states(
                original_catalogue, range(len(slots)), capture_ns, times, timing
            )
            if not np.array_equal(original_valid, np.arange(len(slots))):
                raise ValueError("original exact records failed propagation")
            pe, ve = replay_error(
                original_position,
                original_velocity,
                np.asarray(banks[f"position_km_{ti}"])[slots],
                np.asarray(banks[f"velocity_km_s_{ti}"])[slots],
            )
            position_error, velocity_error = max(position_error, pe), max(velocity_error, ve)
            position, velocity, valid = propagate_candidate_states(
                selected_catalogue, range(len(slots)), capture_ns, times, timing
            )
            if not np.array_equal(valid, np.arange(len(slots))):
                raise ValueError("selected exact records failed propagation")
            skey, pkey, vkey = f"slots_{ti}", f"position_km_{ti}", f"velocity_km_s_{ti}"
            arrays[skey], arrays[pkey], arrays[vkey] = slots, position, velocity
            track_rows.append(
                {
                    "track_id": track_id,
                    "index": ti,
                    "slots_key": skey,
                    "position_key": pkey,
                    "velocity_key": vkey,
                    "candidate_ids": candidate_ids[slots].tolist(),
                    "norads": norads[slots].tolist(),
                    "training_mask_sha256": hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest(),
                    "records": slot_audits,
                }
            )

    expected_capture = {
        int(row["norad"])
        for row in eligible["change_records"]["capture_window"]
        if any(int(row["norad"]) in item["candidate_norad"] for item in side["tracks"].values())
    }
    actual_newer = {
        norad for norad, row in record_audit.items() if changed[norad]["epoch_advance_s"] > 0
    }
    if actual_newer != expected_capture:
        raise ValueError("newer-epoch bank intersection differs from audited eligibility")

    output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = output_dir / f"{index:02d}.npz"
    json_path = output_dir / f"{index:02d}.json"
    if npz_path.exists() or json_path.exists():
        raise FileExistsError(f"patch output already exists for index {index}")
    np.savez(npz_path, **arrays)

    used_proof_rows = [used_proofs[key] for key in sorted(used_proofs)]
    selected_snapshots = [
        {key: row[key] for key in ("provider", "collected_utc_ns", "sha256", "archive_path")}
        for row in used_proof_rows
    ]
    runtime_paths = [
        Path(inspect.getfile(propagate_candidate_states)),
        Path(inspect.getfile(parse_element_sets)),
        Path(inspect.getfile(exclude_labelled_starlink_debris)),
        Path(inspect.getfile(TleArchiveReader)),
    ]
    archive_paths = [ref.path for ref in {*baseline_refs.values(), *proven_refs.values()}]
    source_paths = list(
        dict.fromkeys(
            [
                Path(__file__), PLAN, IDENTITIES, ELIGIBILITY, INVENTORY,
                observation_path, manifest_path, bank_path,
                *bound_paths, *archive_paths, *runtime_paths,
            ]
        )
    )
    result = {
        "schema": "ds11-causal-fresh-confirmation-bank-patch/v1",
        "index": index,
        "slot": slot,
        "session_id": entry["session_id"],
        "capture_start_utc_ns": capture_ns,
        "timing_grid_s": timing.tolist(),
        "selected_snapshots": selected_snapshots,
        "proofs": used_proof_rows,
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
            "full_candidate_slots_validated": full_candidate_slots,
            "training_observations_validated": training_count,
            "held_observations_validated": held_count,
            "inventory_changed_records": len(changed),
            "patched_unique_norads": len(record_audit),
            "patched_tracks": len(track_rows),
            "replacement_candidate_occurrences": sum(len(row["candidate_ids"]) for row in track_rows),
        },
        "records": [record_audit[norad] for norad in sorted(record_audit)],
        "tracks": track_rows,
    }
    json_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def build_manifest(*, output_dir: Path = PATCHES):
    rows = []
    for slot, index in enumerate(ALLOWED):
        json_path = output_dir / f"{index:02d}.json"
        npz_path = output_dir / f"{index:02d}.npz"
        patch = json.loads(json_path.read_text())
        if patch["index"] != index or patch["slot"] != slot:
            raise ValueError("patch set order differs")
        if patch["array"]["path"] != str(npz_path.resolve()) or patch["array"]["sha256"] != digest(npz_path):
            raise ValueError("patch array binding differs")
        rows.append(
            {
                "slot": slot,
                "index": index,
                "session_id": patch["session_id"],
                "patch_path": str(json_path.resolve()),
                "patch_sha256": digest(json_path),
                "array_path": str(npz_path.resolve()),
                "array_sha256": digest(npz_path),
                "patched_tracks": patch["counts"]["patched_tracks"],
                "replacement_candidate_occurrences": patch["counts"]["replacement_candidate_occurrences"],
            }
        )
    path = output_dir / "patch-manifest.json"
    if path.exists():
        raise FileExistsError(path)
    result = {
        "schema": "ds11-causal-fresh-confirmation-patch-set/v1",
        "indices": list(ALLOWED),
        "source_sha256": {
            str(Path(__file__)): digest(Path(__file__)),
            str(PLAN): digest(PLAN),
            str(IDENTITIES): digest(IDENTITIES),
            str(ELIGIBILITY): digest(ELIGIBILITY),
            str(INVENTORY): digest(INVENTORY),
        },
        "patches": rows,
    }
    path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("one")
    one.add_argument("index", type=int, choices=ALLOWED)
    sub.add_parser("manifest")
    args = parser.parse_args()
    if args.action == "one":
        result = prepare(args.index)
        print(
            json.dumps(
                {
                    "index": result["index"],
                    "patched_tracks": result["counts"]["patched_tracks"],
                    "replacement_candidate_occurrences": result["counts"]["replacement_candidate_occurrences"],
                    "replay": result["replay"],
                },
                allow_nan=False,
            ),
            flush=True,
        )
    else:
        result = build_manifest()
        print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
