#!/usr/bin/env python3
"""Materialize the frozen direct-SGP4 synthetic position control."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    propagate_candidate_states,
)
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

SEED = 20260923
GENERATOR = (38.0, -122.0)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def receiver_ecef(latitude_deg: float, longitude_deg: float):
    latitude, longitude = np.deg2rad([latitude_deg, longitude_deg])
    a, flattening = 6378.137, 1 / 298.257223563
    eccentricity2 = flattening * (2 - flattening)
    radius = a / np.sqrt(1 - eccentricity2 * np.sin(latitude) ** 2)
    receiver = np.asarray([
        radius * np.cos(latitude) * np.cos(longitude),
        radius * np.cos(latitude) * np.sin(longitude),
        radius * (1 - eccentricity2) * np.sin(latitude),
    ])
    up = np.asarray([
        np.cos(latitude) * np.cos(longitude),
        np.cos(latitude) * np.sin(longitude),
        np.sin(latitude),
    ])
    return receiver, up


def doppler(position: np.ndarray, velocity: np.ndarray, receiver: np.ndarray):
    delta = position - receiver
    distance = np.linalg.norm(delta, axis=1)
    return -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocity, axis=1) / distance


def direct_states(catalogue, candidate_index: int, start_ns: int, times, shift=0.0):
    position, velocity, valid = propagate_candidate_states(
        catalogue,
        [candidate_index],
        start_ns,
        np.asarray(times, dtype=float),
        np.asarray([shift], dtype=float),
    )
    if valid.tolist() != [candidate_index]:
        raise ValueError("selected generator identity failed direct SGP4")
    return position[0, 0], velocity[0, 0]


def run(args):
    if args.output.exists() or args.receipt.exists():
        raise FileExistsError("fresh materialization outputs required")
    started = time.monotonic()
    manifest = json.loads(args.manifest.read_text())
    baseline = json.loads(args.baseline.read_text())
    view = next(row for row in baseline["views"] if row["scan_count"] == 6)
    sessions = manifest["partitions"]["train"]["session_ids"][:6]
    if view["session_ids"] != sessions:
        raise ValueError("sealed first-six TRAIN session order mismatch")
    sacramento = next(row for row in view["searches"] if row["prior"] == "sacramento")
    archive = TleArchiveReader(args.tle_root)
    snapshots = {(row.digest, row.collected_utc_ns): row for row in archive.list_snapshots()}
    rng = np.random.Generator(np.random.PCG64(SEED))
    receiver, up = receiver_ecef(*GENERATOR)

    prepared = []
    snapshot_rows = []
    for session_id, selected_scan in zip(sessions, sacramento["selected"]["scans"], strict=True):
        if selected_scan["session_id"] != session_id:
            raise ValueError("baseline scan order mismatch")
        directory = args.cache_root / session_id
        receipt_path = directory / "cache_receipt.json"
        cache_path = directory / "state_cache.npz"
        receipt = json.loads(receipt_path.read_text())
        if receipt["session_id"] != session_id:
            raise ValueError("cache session mismatch")
        if receipt["bindings"]["state_cache"] != digest(cache_path):
            raise ValueError("cache binding mismatch")
        evidence = {row["track_id"]: row for row in receipt["prepared_evidence"]["tracks"]}
        key = (
            receipt["prepared_evidence"]["snapshot_digest"],
            receipt["prepared_evidence"]["snapshot_collected_utc_ns"],
        )
        if key not in snapshots:
            raise ValueError(f"recorded causal snapshot unavailable for {session_id}")
        snapshot = snapshots[key]
        payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = parse_element_sets(payload)
        candidate_lookup = {
            str(number): index for index, number in enumerate(catalogue.satellite_numbers)
        }
        snapshot_rows.append({
            "session_id": session_id,
            "snapshot_digest": snapshot.digest,
            "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
            "snapshot_byte_size": snapshot.byte_size,
            "cache_receipt": digest(receipt_path),
            "state_cache": digest(cache_path),
        })
        for selected in selected_scan["tracks"]:
            candidate_id = selected["candidate_id"]
            if candidate_id is None or candidate_id not in candidate_lookup:
                raise ValueError("fixed generating identity absent from causal snapshot")
            source = evidence[selected["track_id"]]
            times = np.asarray(source["times_s"], dtype=float)
            mask = np.asarray(source["training_mask"], dtype=bool)
            position, velocity = direct_states(
                catalogue,
                candidate_lookup[candidate_id],
                receipt["prepared_evidence"]["start_utc_ns"],
                times,
            )
            delta = position - receiver
            distance = np.linalg.norm(delta, axis=1)
            elevation = np.rad2deg(
                np.arcsin(np.clip(np.sum(delta * up, axis=1) / distance, -1.0, 1.0))
            )
            prepared.append({
                "session_id": session_id,
                "track_id": selected["track_id"],
                "candidate_id": candidate_id,
                "times_s": times,
                "training_mask": mask,
                "weight_s": int(len(np.unique(np.floor(times)))),
                "position": position,
                "velocity": velocity,
                "catalogue": catalogue,
                "candidate_index": candidate_lookup[candidate_id],
                "start_utc_ns": receipt["prepared_evidence"]["start_utc_ns"],
                "minimum_elevation_deg": float(np.min(elevation)),
                "maximum_elevation_deg": float(np.max(elevation)),
                "included": bool(np.all(elevation >= 0.0)),
            })

    retained = [row for row in prepared if row["included"]]
    satellite_ids = sorted({row["candidate_id"] for row in retained}, key=int)
    cfo = rng.uniform(-1_000_000.0, 1_000_000.0, len(retained))
    total_observations = sum(len(row["times_s"]) for row in retained)
    noise = rng.normal(0.0, 300.0, total_observations)
    shifts = np.clip(rng.normal(0.0, 0.3, len(satellite_ids)), -1.0, 1.0)
    shift_by_satellite = dict(zip(satellite_ids, shifts, strict=True))

    flat = {key: [] for key in (
        "times_s", "training_mask", "track_index", "position_ecef_km",
        "velocity_ecef_km_s", "shifted_position_ecef_km",
        "shifted_velocity_ecef_km_s", "zero_noise_hz", "gaussian_300hz_hz",
        "gaussian_300hz_satellite_epoch_0p3s_hz",
    )}
    track_rows = []
    offset = 0
    for track_index, (row, track_cfo) in enumerate(zip(retained, cfo, strict=True)):
        count = len(row["times_s"])
        track_noise = noise[offset : offset + count]
        shift = float(shift_by_satellite[row["candidate_id"]])
        shifted_position, shifted_velocity = direct_states(
            row["catalogue"], row["candidate_index"], row["start_utc_ns"],
            row["times_s"], shift,
        )
        base_signal = doppler(row["position"], row["velocity"], receiver) + track_cfo
        shifted_signal = doppler(shifted_position, shifted_velocity, receiver) + track_cfo
        flat["times_s"].extend(row["times_s"])
        flat["training_mask"].extend(row["training_mask"])
        flat["track_index"].extend([track_index] * count)
        flat["position_ecef_km"].extend(row["position"])
        flat["velocity_ecef_km_s"].extend(row["velocity"])
        flat["shifted_position_ecef_km"].extend(shifted_position)
        flat["shifted_velocity_ecef_km_s"].extend(shifted_velocity)
        flat["zero_noise_hz"].extend(base_signal)
        flat["gaussian_300hz_hz"].extend(base_signal + track_noise)
        flat["gaussian_300hz_satellite_epoch_0p3s_hz"].extend(
            shifted_signal + track_noise
        )
        track_rows.append({
            "session_id": row["session_id"], "track_id": row["track_id"],
            "candidate_id": row["candidate_id"], "start": offset, "count": count,
            "weight_s": row["weight_s"], "frequency_offset_hz": float(track_cfo),
            "satellite_epoch_shift_s": shift,
        })
        offset += count

    string_width = max(len(row["track_id"]) for row in retained)
    session_width = max(len(row["session_id"]) for row in retained)
    np.savez(
        args.output,
        times_s=np.asarray(flat["times_s"], dtype=np.float64),
        training_mask=np.asarray(flat["training_mask"], dtype=np.bool_),
        track_index=np.asarray(flat["track_index"], dtype=np.int32),
        position_ecef_km=np.asarray(flat["position_ecef_km"], dtype=np.float64),
        velocity_ecef_km_s=np.asarray(flat["velocity_ecef_km_s"], dtype=np.float64),
        shifted_position_ecef_km=np.asarray(flat["shifted_position_ecef_km"], dtype=np.float64),
        shifted_velocity_ecef_km_s=np.asarray(flat["shifted_velocity_ecef_km_s"], dtype=np.float64),
        zero_noise_hz=np.asarray(flat["zero_noise_hz"], dtype=np.float64),
        gaussian_300hz_hz=np.asarray(flat["gaussian_300hz_hz"], dtype=np.float64),
        gaussian_300hz_satellite_epoch_0p3s_hz=np.asarray(
            flat["gaussian_300hz_satellite_epoch_0p3s_hz"], dtype=np.float64
        ),
        track_id=np.asarray([row["track_id"] for row in retained], dtype=f"U{string_width}"),
        session_id=np.asarray([row["session_id"] for row in retained], dtype=f"U{session_width}"),
        candidate_id=np.asarray([int(row["candidate_id"]) for row in retained], dtype=np.int64),
        track_start=np.asarray([row["start"] for row in track_rows], dtype=np.int32),
        track_count=np.asarray([row["count"] for row in track_rows], dtype=np.int32),
        track_weight_s=np.asarray([row["weight_s"] for row in track_rows], dtype=np.int32),
        track_frequency_offset_hz=np.asarray(cfo, dtype=np.float64),
        satellite_id=np.asarray([int(value) for value in satellite_ids], dtype=np.int64),
        satellite_epoch_shift_s=np.asarray(shifts, dtype=np.float64),
        random_frequency_noise_hz=np.asarray(noise, dtype=np.float64),
    )
    receipt = {
        "schema": "long-position-synthetic-materialization/v1",
        "protocol_frozen_before_generation": True,
        "generator": {
            "latitude_deg": GENERATOR[0], "longitude_deg": GENERATOR[1],
            "altitude_m": 0.0, "role": "sequestered until post-seal evaluation",
        },
        "rng": {"algorithm": "PCG64", "seed": SEED},
        "generator_method": "direct SGP4 at exact rounded observation epochs",
        "selection": {
            "source_arm": "sacramento", "input_track_count": len(prepared),
            "retained_track_count": len(retained),
            "excluded_track_count": len(prepared) - len(retained),
            "criterion": "minimum exact-epoch elevation >= 0 degrees",
            "tracks": [{
                "session_id": row["session_id"], "track_id": row["track_id"],
                "candidate_id": row["candidate_id"], "included": row["included"],
                "minimum_elevation_deg": row["minimum_elevation_deg"],
                "maximum_elevation_deg": row["maximum_elevation_deg"],
                "reason": None if row["included"] else "generating identity below horizon",
            } for row in prepared],
        },
        "track_nuisance": track_rows,
        "satellite_epoch_shifts_s": {
            satellite: float(shift_by_satellite[satellite]) for satellite in satellite_ids
        },
        "snapshots": snapshot_rows,
        "observation_count": total_observations,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "manifest": digest(args.manifest), "baseline": digest(args.baseline),
            "protocol": digest(Path(__file__).with_name("PROTOCOL.md")),
            "tool": digest(Path(__file__)), "materialized_npz": digest(args.output),
        },
    }
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
