#!/usr/bin/env python3
"""Two-session uncapped full-catalogue regional method-development smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import time
from pathlib import Path

import numpy as np
from sgp4.api import SatrecArray

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region, ScoreConfig
from leo.sky.frames import (
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

REGION = Region(39.7392, -104.9903, 14_484.096, 14_484.096)
SPACINGS = (1000.0,)
CATALOGUE_BATCH = 64
GRID_BATCH = 8
TOTAL_BUDGET_S = 8 * 60
RSS_LIMIT_KIB = 2 * 1024 * 1024
CONFIG = ScoreConfig()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def atomic_create(path: Path, document):
    payload = json.dumps(document, indent=2, sort_keys=True).encode() + b"\n"
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"sealed result differs: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.link(temporary, path)
    temporary.unlink()


def load_tracks(root):
    tracks, snapshots, shard_digests = [], {}, []
    for path in sorted(root.glob("*.json")):
        raw = path.read_bytes()
        doc = json.loads(raw)
        shard_digests.append("sha256:" + hashlib.sha256(raw).hexdigest())
        snapshots[doc["catalogue_snapshot"]["digest"]] = doc["catalogue_snapshot"]
        for track in doc["tracks"]:
            rows = track["observations"]
            count = len(rows)
            if count < 4:
                raise ValueError("track lacks two chronological train and held-out observations")
            training_count = min(count - 2, max(2, math.ceil(0.6 * count)))
            training = np.arange(count) < training_count
            if min(int(training.sum()), int((~training).sum())) < 2:
                raise ValueError("track lacks an independent train or held-out observation")
            tracks.append(
                {
                    "track_id": doc["session"]["session_id"] + ":" + track["tracklet_id"],
                    "snapshot_digest": doc["catalogue_snapshot"]["digest"],
                    "utc_ns": np.asarray(
                        [row["support_center_utc_ns"] for row in rows], dtype=np.int64
                    ),
                    "measured_hz": np.asarray([row["measured_cfo_hz"] for row in rows]),
                    "training": training,
                }
            )
    if len(tracks) != 205 or sum(len(track["utc_ns"]) for track in tracks) != 4895:
        raise ValueError("this runner is sealed to the four-session 205-track/4895-row acquisition")
    return tracks, snapshots, tuple(shard_digests)


def load_catalogues(archive, snapshots, tracks):
    result = {}
    by_digest = {snapshot.digest: snapshot for snapshot in archive.list_snapshots()}
    for snapshot_digest, reference in snapshots.items():
        snapshot = by_digest.get(snapshot_digest)
        if snapshot is None or snapshot.collected_utc_ns != reference["collected_utc_ns"]:
            raise ValueError("exported causal snapshot is unavailable or changed")
        payload, _debris = exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = parse_element_sets(payload)
        earliest = min(
            int(track["utc_ns"].min())
            for track in tracks
            if track["snapshot_digest"] == snapshot_digest
        )
        indices = [
            index
            for index, (name, epoch) in enumerate(
                zip(catalogue.names, catalogue.element_epoch_utc_ns(), strict=True)
            )
            if name.upper().startswith("STARLINK") and epoch < earliest
        ]
        result[snapshot_digest] = {
            "catalogue": catalogue,
            "indices": indices,
            "catalogue_size": len(indices),
            "snapshot": reference,
        }
    return result


def propagated_batch(catalogue, indices, utc_ns):
    satellites = SatrecArray([catalogue.satellites[index] for index in indices])
    jd, fraction = julian_day_from_utc_ns(utc_ns)
    errors, position, velocity = satellites.sgp4(jd, fraction)
    usable = np.all(errors == 0, axis=1)
    angle = greenwich_mean_sidereal_time_rad(jd, fraction)
    position, velocity = teme_to_ecef(position[usable], velocity[usable], angle)
    return usable, position, velocity


def batch_scores(track, positions, velocities, grid):
    training = track["training"]
    y = track["measured_hz"]
    outputs = []
    horizon = math.sin(math.radians(CONFIG.minimum_elevation_deg))
    for start in range(0, len(grid), GRID_BATCH):
        receiver = grid.ecef_km[start : start + GRID_BATCH]
        up = grid.up[start : start + GRID_BATCH]
        shape = (len(receiver), len(positions), len(y))
        dot = (receiver @ positions.reshape(-1, 3).T).reshape(shape)
        distance = np.sqrt(
            np.maximum(
                np.sum(positions * positions, axis=-1)[None]
                + np.sum(receiver * receiver, axis=-1)[:, None, None]
                - 2 * dot,
                1e-12,
            )
        )
        numerator = np.sum(positions * velocities, axis=-1)[None] - (
            receiver @ velocities.reshape(-1, 3).T
        ).reshape(shape)
        prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * numerator / distance
        elevation = (
            (up @ positions.reshape(-1, 3).T).reshape(shape)
            - np.sum(receiver * up, axis=-1)[:, None, None]
        ) / distance
        visible = np.min(elevation[..., training], axis=-1) >= horizon
        residual = y[None, None, :] - prediction
        offset = np.mean(residual[..., training], axis=-1, keepdims=True)
        train_mse = np.mean((residual[..., training] - offset) ** 2, axis=-1)
        heldout_mse = np.mean((residual[..., ~training] - offset) ** 2, axis=-1)
        n = CONFIG.effective_count
        train_ll = -0.5 * n * train_mse / CONFIG.signal_sigma_hz**2 - n * math.log(
            CONFIG.signal_sigma_hz
        )
        heldout_ll = -0.5 * n * heldout_mse / CONFIG.signal_sigma_hz**2 - n * math.log(
            CONFIG.signal_sigma_hz
        )
        outputs.append(
            (np.where(visible, train_ll, -np.inf), np.where(visible, heldout_ll, -np.inf))
        )
    return np.concatenate([item[0] for item in outputs]), np.concatenate(
        [item[1] for item in outputs]
    )


def score_track(track, catalogue_info, grid, deadline):
    size = catalogue_info["catalogue_size"]
    log_prior = math.log(CONFIG.signal_prior / size)
    signal_train = np.full(len(grid), -np.inf)
    signal_joint = np.full(len(grid), -np.inf)
    best_ll = np.full(len(grid), -np.inf)
    best_catalog = np.full(len(grid), -1, dtype=np.int64)
    propagation_failures = 0
    catalogue = catalogue_info["catalogue"]
    indices = catalogue_info["indices"]
    for begin in range(0, len(indices), CATALOGUE_BATCH):
        if time.monotonic() >= deadline:
            raise TimeoutError("shared wall-time budget exhausted")
        chosen = indices[begin : begin + CATALOGUE_BATCH]
        usable, position, velocity = propagated_batch(catalogue, chosen, track["utc_ns"])
        propagation_failures += len(chosen) - int(usable.sum())
        if not np.any(usable):
            continue
        catalog_numbers = np.asarray(catalogue.satellite_numbers)[np.asarray(chosen)[usable]]
        train_ll, heldout_ll = batch_scores(track, position, velocity, grid)
        signal_train = np.logaddexp(signal_train, np.logaddexp.reduce(train_ll + log_prior, axis=1))
        signal_joint = np.logaddexp(
            signal_joint, np.logaddexp.reduce(train_ll + heldout_ll + log_prior, axis=1)
        )
        local = np.argmax(train_ll, axis=1)
        local_ll = train_ll[np.arange(len(grid)), local]
        replace = local_ll > best_ll
        best_ll[replace] = local_ll[replace]
        best_catalog[replace] = catalog_numbers[local[replace]]
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > RSS_LIMIT_KIB:
            raise MemoryError("2 GiB RSS budget exceeded")
    y = track["measured_hz"]
    training = track["training"]
    null_offset = np.mean(y[training])
    null_train_mse = np.mean((y[training] - null_offset) ** 2)
    null_test_mse = np.mean((y[~training] - null_offset) ** 2)
    n = CONFIG.effective_count
    null_train = -0.5 * n * null_train_mse / CONFIG.null_sigma_hz**2 - n * math.log(
        CONFIG.null_sigma_hz
    )
    null_test = -0.5 * n * null_test_mse / CONFIG.null_sigma_hz**2 - n * math.log(
        CONFIG.null_sigma_hz
    )
    null_prior = math.log1p(-CONFIG.signal_prior)
    evidence = np.logaddexp(signal_train, null_train + null_prior)
    predictive = np.logaddexp(signal_joint, null_train + null_test + null_prior) - evidence
    return (
        evidence - (null_train + null_prior),
        predictive - null_test,
        best_catalog,
        propagation_failures,
    )


def run_arm(spacing, tracks, catalogues, output, global_started):
    grid = REGION.grid(spacing)
    result_path = output / f"full-region-{int(spacing)}km.json"
    arm_started = time.monotonic()
    remaining = TOTAL_BUDGET_S - (arm_started - global_started)
    # A deterministic preflight from the previous completed arm prevents a
    # hopeless finer arm from consuming the shared budget.
    prior_receipts = sorted(output.glob("full-region-*km.json"))
    completed = [json.loads(path.read_text()) for path in prior_receipts]
    completed = [item for item in completed if item["state"] == "complete"]
    if completed:
        latest = completed[-1]
        predicted = latest["runtime_seconds"] * len(grid) / latest["grid_point_count"]
        if predicted > remaining * 0.9:
            receipt = {
                "state": "not_run_resource_budget",
                "reason": "preflight runtime extrapolation exceeds remaining shared budget",
                "spacing_km": spacing,
                "grid_point_count": len(grid),
                "predicted_runtime_seconds": predicted,
                "remaining_budget_seconds": remaining,
            }
            atomic_create(result_path, receipt)
            return receipt
    total_train = np.zeros(len(grid))
    total_heldout = np.zeros(len(grid))
    best_by_track, failures = [], 0
    deadline = global_started + TOTAL_BUDGET_S
    try:
        for track_index, track in enumerate(tracks):
            train, heldout, identity, failed = score_track(
                track, catalogues[track["snapshot_digest"]], grid, deadline
            )
            total_train += train
            total_heldout += heldout
            best_by_track.append(identity)
            failures += failed
            if track_index % 5 == 0:
                print(spacing, track_index + 1, "/", len(tracks), flush=True)
    except (TimeoutError, MemoryError) as error:
        receipt = {
            "state": "not_run_resource_budget",
            "reason": str(error),
            "spacing_km": spacing,
            "grid_point_count": len(grid),
            "completed_track_count": len(best_by_track),
            "runtime_seconds": time.monotonic() - arm_started,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
        atomic_create(result_path, receipt)
        return receipt
    order = np.argsort(total_train)[::-1]
    alternatives = [
        {
            "rank": rank + 1,
            "grid_index": int(index),
            "latitude_deg": float(grid.latitude_deg[index]),
            "longitude_deg": float(grid.longitude_deg[index]),
            "training_log_evidence": float(total_train[index]),
            "heldout_log_predictive": float(total_heldout[index]),
        }
        for rank, index in enumerate(order[:16])
    ]
    selected = int(order[0])
    receipt = {
        "state": "complete",
        "method": "two-session-uncapped-full-catalogue-regional-smoke-v1",
        "spacing_km": spacing,
        "grid_point_count": len(grid),
        "track_count": len(tracks),
        "observation_count": sum(len(track["utc_ns"]) for track in tracks),
        "catalogue_size": next(iter(catalogues.values()))["catalogue_size"],
        "selected_grid_index": selected,
        "selected_latitude_deg": float(grid.latitude_deg[selected]),
        "selected_longitude_deg": float(grid.longitude_deg[selected]),
        "training_log_evidence": float(total_train[selected]),
        "heldout_log_predictive": float(total_heldout[selected]),
        "alternatives": alternatives,
        "selected_track_catalog_numbers": [int(values[selected]) for values in best_by_track],
        "propagation_failure_count": failures,
        "runtime_seconds": time.monotonic() - arm_started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "truth_accessed": False,
    }
    receipt["result_digest"] = digest(receipt)
    atomic_create(result_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True)
    from leo.operations.tle_archive import TleArchiveReader

    tracks, snapshots, shard_digests = load_tracks(args.shards)
    catalogues = load_catalogues(TleArchiveReader(args.tle_root), snapshots, tracks)
    configuration = {
        "region": REGION.__dict__,
        "spacings_km": SPACINGS,
        "catalogue_batch": CATALOGUE_BATCH,
        "grid_batch": GRID_BATCH,
        "score": CONFIG.__dict__,
        "total_budget_seconds": TOTAL_BUDGET_S,
        "rss_limit_kib": RSS_LIMIT_KIB,
        "source_shard_digests": shard_digests,
        "truth_accessed": False,
    }
    atomic_create(
        args.output / "configuration.json", {**configuration, "digest": digest(configuration)}
    )
    started = time.monotonic()
    receipts = [run_arm(spacing, tracks, catalogues, args.output, started) for spacing in SPACINGS]
    atomic_create(
        args.output / "sealed-arms.json",
        {
            "method_development_smoke": True,
            "not_12h_study": True,
            "receipts": receipts,
            "truth_accessed": False,
        },
    )


if __name__ == "__main__":
    main()
