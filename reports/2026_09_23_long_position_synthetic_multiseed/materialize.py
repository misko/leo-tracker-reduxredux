#!/usr/bin/env python3
"""Materialize the frozen 20-seed paired synthetic sensitivity cases."""

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

SEEDS = np.arange(2026092300, 2026092320, dtype=np.int64)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def receiver_ecef(latitude_deg: float, longitude_deg: float):
    latitude, longitude = np.deg2rad([latitude_deg, longitude_deg])
    a, flattening = 6378.137, 1 / 298.257223563
    eccentricity2 = flattening * (2 - flattening)
    radius = a / np.sqrt(1 - eccentricity2 * np.sin(latitude) ** 2)
    return np.asarray([
        radius * np.cos(latitude) * np.cos(longitude),
        radius * np.cos(latitude) * np.sin(longitude),
        radius * (1 - eccentricity2) * np.sin(latitude),
    ])


def doppler(position: np.ndarray, velocity: np.ndarray, receiver: np.ndarray):
    delta = position - receiver
    return -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocity, axis=1) / np.linalg.norm(
        delta, axis=1
    )


def direct_states(catalogue, candidate_index, start_ns, times, shift):
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
        raise FileExistsError("fresh outputs required")
    started = time.monotonic()
    base_receipt = json.loads(args.base_receipt.read_text())
    if base_receipt["bindings"]["materialized_npz"] != digest(args.base_materialized):
        raise ValueError("base materialization binding mismatch")
    base_archive = np.load(args.base_materialized, allow_pickle=False)
    base = {key: base_archive[key] for key in base_archive.files}
    base_archive.close()
    generator = base_receipt["generator"]
    receiver = receiver_ecef(generator["latitude_deg"], generator["longitude_deg"])
    satellite_ids = base["satellite_id"]
    satellite_lookup = {str(value): index for index, value in enumerate(satellite_ids)}
    noise = np.empty((len(SEEDS), len(base["times_s"])), dtype=np.float64)
    shifts = np.empty((len(SEEDS), len(satellite_ids)), dtype=np.float64)
    noise_only = np.empty_like(noise)
    shifted = np.empty_like(noise)
    for seed_index, seed in enumerate(SEEDS):
        rng = np.random.Generator(np.random.PCG64(int(seed)))
        noise[seed_index] = rng.normal(0.0, 300.0, len(base["times_s"]))
        shifts[seed_index] = np.clip(
            rng.normal(0.0, 0.3, len(satellite_ids)), -1.0, 1.0
        )
        noise_only[seed_index] = base["zero_noise_hz"] + noise[seed_index]

    archive = TleArchiveReader(args.tle_root)
    snapshots = {(row.digest, row.collected_utc_ns): row for row in archive.list_snapshots()}
    session_models = {}
    snapshot_rows = []
    for source in base_receipt["snapshots"]:
        session_id = source["session_id"]
        cache_receipt_path = args.cache_root / session_id / "cache_receipt.json"
        cache_receipt = json.loads(cache_receipt_path.read_text())
        prepared = cache_receipt["prepared_evidence"]
        key = (prepared["snapshot_digest"], prepared["snapshot_collected_utc_ns"])
        if key not in snapshots:
            raise ValueError(f"causal snapshot unavailable for {session_id}")
        snapshot = snapshots[key]
        payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = parse_element_sets(payload)
        session_models[session_id] = (
            catalogue,
            {str(value): index for index, value in enumerate(catalogue.satellite_numbers)},
            prepared["start_utc_ns"],
        )
        snapshot_rows.append({
            "session_id": session_id,
            "snapshot_digest": snapshot.digest,
            "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
            "cache_receipt": digest(cache_receipt_path),
        })

    for seed_index in range(len(SEEDS)):
        for track_index, (start, count) in enumerate(
            zip(base["track_start"], base["track_count"], strict=True)
        ):
            selection = slice(int(start), int(start + count))
            session_id = str(base["session_id"][track_index])
            candidate_id = str(base["candidate_id"][track_index])
            catalogue, candidate_lookup, start_ns = session_models[session_id]
            shift = float(shifts[seed_index, satellite_lookup[candidate_id]])
            position, velocity = direct_states(
                catalogue,
                candidate_lookup[candidate_id],
                start_ns,
                base["times_s"][selection],
                shift,
            )
            shifted[seed_index, selection] = (
                doppler(position, velocity, receiver)
                + base["track_frequency_offset_hz"][track_index]
                + noise[seed_index, selection]
            )

    retained = {
        key: base[key]
        for key in (
            "times_s", "training_mask", "track_index", "position_ecef_km",
            "velocity_ecef_km_s", "track_id", "session_id", "candidate_id",
            "track_start", "track_count", "track_weight_s", "track_frequency_offset_hz",
            "satellite_id",
        )
    }
    np.savez(
        args.output,
        **retained,
        seeds=SEEDS,
        random_frequency_noise_hz=noise,
        satellite_epoch_shift_s=shifts,
        gaussian_300hz_hz=noise_only,
        gaussian_300hz_satellite_epoch_0p3s_hz=shifted,
    )
    receipt = {
        "schema": "long-position-synthetic-multiseed-materialization/v1",
        "protocol_frozen_before_generation": True,
        "generator": generator,
        "seeds": SEEDS.tolist(),
        "rng": "NumPy Generator(PCG64(seed)), one independent stream per seed",
        "case_pairing": "same per-observation 300 Hz draw within each seed",
        "shift_generation": "direct SGP4 at every exact shifted observation epoch",
        "observation_count": len(base["times_s"]),
        "track_count": len(base["track_id"]),
        "satellite_count": len(satellite_ids),
        "snapshots": snapshot_rows,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "protocol": digest(Path(__file__).with_name("PROTOCOL.md")),
            "tool": digest(Path(__file__)),
            "base_materialized": digest(args.base_materialized),
            "base_receipt": digest(args.base_receipt),
            "materialized_npz": digest(args.output),
        },
    }
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-materialized", type=Path, required=True)
    parser.add_argument("--base-receipt", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
