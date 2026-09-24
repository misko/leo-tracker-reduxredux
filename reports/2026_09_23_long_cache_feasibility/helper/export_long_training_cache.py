#!/usr/bin/env python3
"""Export one compact, response-free adaptive-TLE long-session cache.

Run as the service identity that has read-only access to scanner inputs.  This
uses the public preparation operation and does not call a position search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.cli.adaptive_tle_position import PRIORS
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def query_offsets_ns(tracks, taus_s):
    """Return unique receive-plus-tau epochs and track/tau lookup indices."""
    offsets = []
    for track in tracks:
        for tau in taus_s:
            offsets.extend(np.rint((track.times_s + tau) * 1e9).astype(np.int64).tolist())
    unique = np.asarray(sorted(set(offsets)), dtype=np.int64)
    lookup = {int(value): index for index, value in enumerate(unique)}
    indices = []
    for track in tracks:
        rows = []
        for tau in taus_s:
            values = np.rint((track.times_s + tau) * 1e9).astype(np.int64)
            rows.append([lookup[int(value)] for value in values])
        indices.append(rows)
    return unique, indices


def regional_normal_caps():
    """Prior-centre normal and conservative angular radius for each disk."""
    minimum_curvature_km = 6335.0
    values = []
    for name, (latitude, longitude, radius_km) in PRIORS.items():
        lat, lon = np.deg2rad([latitude, longitude])
        normal = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
        values.append((name, normal, radius_km / minimum_curvature_km))
    return values


def possibly_visible_in_regional_caps(position_km, caps):
    """Conservative necessary test for horizon visibility in either prior disk.

    A real receiver normal lies within the stated cap around its regional
    centre. The largest possible p.dot(n) over that cap is compared with the
    WGS84 semi-minor axis, which is a conservative lower horizon threshold at
    altitude zero. An uncertain candidate is retained.
    """
    earth_semi_minor_km = 6356.752314245
    keep = np.zeros(len(position_km), dtype=bool)
    norm = np.linalg.norm(position_km, axis=-1)
    for _name, normal, delta in caps:
        cosine = np.clip(np.sum(position_km * normal, axis=-1) / norm, -1.0, 1.0)
        angle = np.arccos(cosine)
        maximum_dot = norm * np.cos(np.maximum(angle - delta, 0.0))
        keep |= np.any(maximum_dot >= earth_semi_minor_km, axis=1)
    return keep


def export(args):
    if args.output.exists():
        raise FileExistsError("fresh output directory required")
    args.output.mkdir(parents=True)
    started = time.monotonic()
    source_store = ScannerTrackingInputStore(
        args.bulk_root,
        adaptive_analysis_root=args.adaptive_analysis_root,
    )
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            args.session_id,
            inputs=source_store,
            archive=TleArchiveReader(args.tle_root),
        )
    finally:
        source_store.close()
    taus = np.arange(-5.0, 6.0)
    query_offsets, _ = query_offsets_ns(prepared.tracks, taus)
    step_ns = round(args.grid_step_s * 1e9)
    grid_start = (int(query_offsets.min()) // step_ns) * step_ns
    grid_stop = ((int(query_offsets.max()) + step_ns - 1) // step_ns) * step_ns
    offsets = np.arange(grid_start, grid_stop + step_ns, step_ns, dtype=np.int64)
    caps = regional_normal_caps()
    kept_ids, kept_position, kept_velocity = [], [], []
    candidate = np.asarray(prepared.candidate_indices, dtype=int)
    for begin in range(0, len(candidate), args.candidate_block):
        block = candidate[begin : begin + args.candidate_block]
        position, velocity, valid = propagate_candidate_states(
            prepared.catalogue,
            block,
            prepared.start_utc_ns,
            offsets / 1e9,
            np.asarray([0.0]),
        )
        if not len(valid):
            continue
        position, velocity = position[:, 0], velocity[:, 0]
        keep = possibly_visible_in_regional_caps(position, caps)
        if np.any(keep):
            kept_ids.append(np.asarray(prepared.catalogue.satellite_numbers)[valid][keep])
            kept_position.append(position[keep])
            kept_velocity.append(velocity[keep])
    candidate_ids = np.concatenate(kept_ids) if kept_ids else np.empty(0, dtype=np.int64)
    position = (
        np.concatenate(kept_position)
        if kept_position
        else np.empty((0, len(offsets), 3), dtype=float)
    )
    velocity = (
        np.concatenate(kept_velocity)
        if kept_velocity
        else np.empty((0, len(offsets), 3), dtype=float)
    )
    np.savez_compressed(
        args.output / "state_cache.npz",
        candidate_id=candidate_ids,
        receive_plus_tau_offset_ns=offsets,
        position_ecef_km=position,
        velocity_ecef_km_s=velocity,
    )
    cache_path = args.output / "state_cache.npz"
    receipt = {
        "schema": "long-adaptive-tle-response-free-cache/v1",
        "session_id": prepared.session_id,
        "selection_scope": "one session explicitly named by caller",
        "position_search_or_fit_run": False,
        "candidate_policy": (
            "all causal non-debris STARLINK candidates from "
            "prepare_adaptive_tle_position_inputs, retained only if a conservative "
            "regional normal-cap bound permits above-horizon visibility at queried epochs"
        ),
        "regional_filter": {
            "priors": {
                name: {"latitude_deg": lat, "longitude_deg": lon, "radius_km": radius}
                for name, (lat, lon, radius) in PRIORS.items()
            },
            "altitude_m": 0.0,
            "minimum_wgs84_curvature_radius_km": 6335.0,
            "earth_semi_minor_axis_km": 6356.752314245,
            "criterion": (
                "retain if max p.dot(n) over either regional normal cap reaches "
                "the semi-minor axis at one queried epoch; uncertain candidates remain"
            ),
            "normal_cap_radius_rad": {name: float(delta) for name, _normal, delta in caps},
        },
        "state_layout": {
            "epoch_policy": "regular grid covering all rounded receive-plus-integer-tau epochs",
            "taus_s": taus.tolist(),
            "time_offset_count": len(offsets),
            "grid_step_s": args.grid_step_s,
            "query_epoch_count": len(query_offsets),
            "array_layout": "candidate, unique_epoch, xyz; ECEF position and velocity",
            "query_policy": "round((track.times_s + tau) * 1e9), then interpolate on grid",
        },
        "prepared_evidence": {
            "input_manifest_sha256": prepared.input_manifest_sha256,
            "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
            "evidence_sha256": prepared.evidence_sha256,
            "trajectory_digest": prepared.trajectory_digest,
            "snapshot_digest": prepared.snapshot_digest,
            "snapshot_collected_utc_ns": prepared.snapshot_collected_utc_ns,
            "start_utc_ns": prepared.start_utc_ns,
            "reconstructed_track_count": prepared.reconstructed_track_count,
            "eligible_track_count": prepared.eligible_track_count,
            "eligible_observation_count": prepared.eligible_observation_count,
            "tracks": prepared.track_evidence,
        },
        "candidate_counts": {
            "causal_full_catalogue": len(candidate),
            "regional_grid_retained": len(candidate_ids),
        },
        "storage_bytes": cache_path.stat().st_size,
        "elapsed_s": time.monotonic() - started,
        "bindings": {
            "export_tool": sha256(Path(__file__)),
            "state_cache": sha256(cache_path),
        },
    }
    (args.output / "cache_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {key: receipt[key] for key in ("candidate_counts", "storage_bytes", "elapsed_s")},
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--adaptive-analysis-root",
        type=Path,
        help="Separate read-only adaptive metrics root for isolated backfills.",
    )
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-block", type=int, default=128)
    parser.add_argument("--grid-step-s", type=float, default=1.0)
    export(parser.parse_args())


if __name__ == "__main__":
    main()
