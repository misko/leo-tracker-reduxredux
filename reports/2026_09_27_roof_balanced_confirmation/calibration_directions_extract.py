"""Calibration-only robust-shortlist direction extraction.

This script creates a new diagnostic artifact and does not alter any frozen
calibration or search module.  It deliberately accepts no evaluation location.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import pickle
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DIRECTION = ROOT / "reports/2026_09_27_roof_direction_subset"
LOCATION = ROOT / "reports/2026_09_27_roof_location_geometry"
CONFIRMATION = ROOT / "reports/2026_09_27_roof_geometry_confirmation"
sys.path[:0] = [str(LOCATION), str(DIRECTION), str(CONFIRMATION)]

import calibrate_frequency_fixedpoint as fixedpoint
from leo.analysis.adaptive_tle_prediction import build_prediction_banks
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def normalized_weights(weights: object) -> np.ndarray:
    value = np.asarray(weights, dtype=float)
    if value.ndim != 1 or not len(value) or not np.all(np.isfinite(value)):
        raise ValueError("weights must be a nonempty finite vector")
    if np.any(value < 0) or not value.sum() > 0:
        raise ValueError("weights must be nonnegative with positive total")
    return value / value.sum()


def align_indices(track_observation_ids: object, requested_ids: object) -> np.ndarray:
    source = list(track_observation_ids)
    if len(source) != len(set(source)):
        raise ValueError("duplicate track observation ID")
    lookup = {value: index for index, value in enumerate(source)}
    requested = list(requested_ids)
    if len(requested) != len(set(requested)):
        raise ValueError("duplicate requested observation ID")
    missing = [value for value in requested if value not in lookup]
    if missing:
        raise ValueError(f"missing observation IDs: {missing[:3]}")
    return np.asarray([lookup[value] for value in requested], dtype=int)


def candidate_directions(position_km: object, receiver_km: object,
                         east_axis: object, up_axis: object) -> tuple[np.ndarray, np.ndarray]:
    positions = np.asarray(position_km, dtype=float)
    receiver = np.asarray(receiver_km, dtype=float)
    east = np.asarray(east_axis, dtype=float)
    up = np.asarray(up_axis, dtype=float)
    if positions.ndim != 3 or positions.shape[-1] != 3:
        raise ValueError("candidate positions must have shape candidate,time,3")
    if receiver.shape != (3,) or east.shape != (3,) or up.shape != (3,):
        raise ValueError("receiver and axes must be three-vectors")
    if not all(np.all(np.isfinite(x)) for x in (positions, receiver, east, up)):
        raise ValueError("direction inputs must be finite")
    delta = positions - receiver
    norm = np.linalg.norm(delta, axis=-1)
    if np.any(norm <= 0):
        raise ValueError("candidate coincides with receiver")
    unit = delta / norm[..., None]
    return np.sum(unit * east, axis=-1), np.sum(unit * up, axis=-1)


def weighted_means(east: object, up: object, weights: object) -> tuple[np.ndarray, np.ndarray]:
    e = np.asarray(east, dtype=float)
    u = np.asarray(up, dtype=float)
    w = normalized_weights(weights)
    if e.shape != u.shape or e.ndim != 2 or e.shape[0] != len(w):
        raise ValueError("direction arrays must have shape candidate,observation")
    if not np.all(np.isfinite(e)) or not np.all(np.isfinite(u)):
        raise ValueError("directions must be finite")
    return w @ e, w @ u


def _atomic(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def main() -> None:
    target = HERE / "calibration_directions_data.json"
    fixed_path = LOCATION / "topology_frequency_fixedpoint.json"
    fixed_bytes = fixed_path.read_bytes()
    frozen = json.loads(fixed_bytes)
    if not frozen.get("converged"):
        raise ValueError("topology frequency fixed point is not converged")
    audit_path = CONFIRMATION / "audit_source_topology.json"
    audit_bytes = audit_path.read_bytes()
    if frozen["topology_audit_sha256"] != digest(audit_bytes):
        raise ValueError("frequency extraction/topology audit binding mismatch")

    inventory_path = DIRECTION / "evaluation_inventory.json"
    inventory = {row["session_id"]: row for row in json.loads(inventory_path.read_text())}
    manifest_path = DIRECTION / "evaluation_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    poses = {row["pose"]["session_id"]: row["pose"]["pose_authority"]
             for row in manifest["sessions"]}
    associations_path = DIRECTION / "associations.json"
    associations = json.loads(associations_path.read_text())
    branches = {row["session_id"]: row for row in associations["branches"]}
    links_path = DIRECTION / "source_links.json"
    links = json.loads(links_path.read_text())
    model_rows_path = DIRECTION / "model_rows.json"
    model_rows = json.loads(model_rows_path.read_text())
    reception = defaultdict(list)
    for row in model_rows:
        if row["split"] == "cal":
            reception[(row["session_id"], row["track_id"])].append(row)

    output_rows = []
    session_receipts = []
    for sid in sorted(frozen["final_tracks"]):
        entry = inventory[sid]
        source = frozen["source_digests"][sid]
        payload = Path(entry["cache_file"]).read_bytes()
        if (entry["split"] != "calibration" or not entry["ready"] or
                digest(payload) != entry["cache_sha256"]):
            raise ValueError(f"{sid}: invalid frozen cache")
        raw = pickle.loads(payload)
        prepared = prepare_adaptive_tle_position_inputs(
            sid, inputs=fixedpoint.CachedInput(raw),
            archive=TleArchiveReader(Path("/var/lib/leo/tle")))
        for key in ("input_manifest_sha256", "analysis_manifest_sha256",
                    "evidence_sha256", "snapshot_digest"):
            if getattr(prepared, key) != source[key]:
                raise ValueError(f"{sid}: {key} binding mismatch")
        link_digest = digest(json.dumps(
            links[sid]["rows"], sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode())
        if link_digest != source["source_links_sha256"]:
            raise ValueError(f"{sid}: source-link binding mismatch")
        branch = branches[sid]
        if (branch["branch"] != "truth_diagnostic" or
                branch["evidence_sha256"] != source["evidence_sha256"] or
                branch["snapshot_digest"] != source["snapshot_digest"]):
            raise ValueError(f"{sid}: original association binding mismatch")
        pose = poses[sid]
        if any(branch["site"][key] != pose[key]
               for key in ("latitude_deg", "longitude_deg")):
            raise ValueError(f"{sid}: known-site pose mismatch")

        banks, bank_receipt = build_prediction_banks(
            prepared.catalogue, prepared.candidate_indices,
            prepared.start_utc_ns, prepared.tracks, taus_s=np.array([0.]))
        bank_by_track = {bank.source.track_id: bank for bank in banks}
        robust = {row["track_id"]: row for row in frozen["final_tracks"][sid]}
        association_rows = defaultdict(dict)
        for row in branch["rows"]:
            association_rows[row["track_id"]][row["projected_observation_id"]] = row
        retained = set(robust)
        if set(bank_by_track) < retained:
            raise ValueError(f"{sid}: retained track absent from prediction bank")

        receiver_point = fixedpoint.point(pose["latitude_deg"], pose["longitude_deg"])
        receiver = receiver_point.ecef_km
        longitude = np.deg2rad(pose["longitude_deg"])
        east_axis = np.array([-np.sin(longitude), np.cos(longitude), 0.])
        for track_id, shortlist in robust.items():
            bank = bank_by_track[track_id]
            track = bank.source
            candidate_index = {int(cid): i for i, cid in enumerate(bank.candidate_ids)}
            ids = [int(value) for value in shortlist["candidate_ids"]]
            missing = [value for value in ids if value not in candidate_index]
            if missing:
                raise ValueError(f"{sid}/{track_id}: robust candidates absent: {missing}")
            weights = normalized_weights(shortlist["weights"])
            if not np.allclose(np.asarray(shortlist["log_weights"]),
                               np.log(weights), rtol=0, atol=1e-12):
                # Zero-underflow weights are allowed, but none occur in this artifact.
                positive = weights > 0
                if not np.allclose(np.asarray(shortlist["log_weights"])[positive],
                                   np.log(weights[positive]), rtol=0, atol=1e-12):
                    raise ValueError(f"{sid}/{track_id}: inconsistent robust weights")
            rx_rows = sorted(reception[(sid, track_id)], key=lambda row: row["observation_id"])
            observation_ids = [row["observation_id"] for row in rx_rows]
            indices = align_indices(track.observation_ids, observation_ids)
            old_rows = association_rows[track_id]
            if any(oid not in old_rows for oid in observation_ids):
                raise ValueError(f"{sid}/{track_id}: reception/association ID mismatch")
            positions = bank.position_km[
                [candidate_index[value] for value in ids], 0, :, :][:, indices, :]
            east, up = candidate_directions(
                positions, receiver, east_axis, receiver_point.up)
            mean_east, mean_up = weighted_means(east, up, weights)
            old_map = int(rx_rows[0]["candidate_ids"][0])
            for column, (row, index) in enumerate(zip(rx_rows, indices, strict=True)):
                old = old_rows[row["observation_id"]]
                old_ids = [int(value) for value in old["candidate_ids"]]
                old_weights = normalized_weights(old["candidate_probabilities"])
                azimuth = np.deg2rad(np.asarray(old["candidate_azimuth_deg"], float))
                elevation = np.deg2rad(np.asarray(old["candidate_elevation_deg"], float))
                old_component_east = np.cos(elevation) * np.sin(azimuth)
                old_component_up = np.sin(elevation)
                old_mean_east = float(old_weights @ old_component_east)
                old_mean_up = float(old_weights @ old_component_up)
                if (abs(old_mean_east - float(row["east"])) > 2e-12 or
                        abs(old_mean_up - float(row["up"])) > 2e-12):
                    raise ValueError(f"{sid}/{track_id}: old component mean mismatch")
                output_rows.append({
                    "session_id": sid, "track_id": track_id,
                    "observation_id": row["observation_id"],
                    "observation_utc_ns": int(old["observation_utc_ns"]),
                    "track_observation_index": int(index),
                    "weight_seconds": float(shortlist["weight_seconds"]),
                    "map_changed": old_map != ids[0],
                    "old_candidates": [
                        {"candidate_id": cid, "weight": float(weight),
                         "east": float(e), "up": float(u)}
                        for cid, weight, e, u in zip(
                            old_ids, old_weights, old_component_east,
                            old_component_up, strict=True)],
                    "robust_candidates": [
                        {"candidate_id": cid, "weight": float(weight),
                         "east": float(east[n, column]), "up": float(up[n, column])}
                        for n, (cid, weight) in enumerate(zip(ids, weights, strict=True))],
                    "old_mean_east": old_mean_east,
                    "old_mean_up": old_mean_up,
                    "robust_mean_east": float(mean_east[column]),
                    "robust_mean_up": float(mean_up[column]),
                    "delta_east": float(mean_east[column] - old_mean_east),
                    "delta_up": float(mean_up[column] - old_mean_up),
                })
        session_receipts.append({
            "session_id": sid, "retained_tracks": len(robust),
            "rows": sum(1 for row in output_rows if row["session_id"] == sid),
            "cache_sha256": entry["cache_sha256"],
            "input_manifest_sha256": prepared.input_manifest_sha256,
            "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
            "evidence_sha256": prepared.evidence_sha256,
            "snapshot_digest": prepared.snapshot_digest,
            "source_links_sha256": link_digest,
            "prediction_receipt": asdict(bank_receipt),
        })
        print("DIRECTIONS", sid, len(robust), session_receipts[-1]["rows"], flush=True)

    _atomic(target, {
        "protocol": "Known calibration site only; exact frozen robust candidate IDs and weights; no evaluation location, error, search, or refit.",
        "frozen_parameters": frozen["frozen_final_parameters"],
        "source_hashes": {
            "topology_frequency_fixedpoint": digest(fixed_bytes),
            "calibration_topology_audit": digest(audit_bytes),
            "evaluation_inventory": digest(inventory_path.read_bytes()),
            "evaluation_manifest": digest(manifest_path.read_bytes()),
            "associations": digest(associations_path.read_bytes()),
            "source_links": digest(links_path.read_bytes()),
            "model_rows": digest(model_rows_path.read_bytes()),
            "extractor": digest(Path(__file__).read_bytes()),
        },
        "sessions": session_receipts,
        "rows": output_rows,
    })


if __name__ == "__main__":
    main()
