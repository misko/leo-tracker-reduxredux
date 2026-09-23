#!/usr/bin/env python3
"""Audit quarter-second cached state interpolation against exact propagation."""

# ruff: noqa: E402
from __future__ import annotations

import os

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import LIGHT_KM_S, REFERENCE_RF_HZ
from leo.sky.frames import greenwich_mean_sidereal_time_rad, julian_day_from_utc_ns, teme_to_ecef
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid

TAUS = np.array([-5.0, 0.0, 5.0])
POINTS = (
    ("training_joint_basin", 37.84936795005425, -122.48209887260599),
    ("sacramento_city", 38.5816, -121.4944),
    ("reno_city", 39.5296, -119.8138),
)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def interpolation_indices(grid, query, step=0.25):
    """Return safe linear-interpolation indices, rejecting cache extrapolation."""
    grid = np.asarray(grid, dtype=float)
    query = np.asarray(query, dtype=float)
    tolerance = 1e-9
    if np.any(query < grid[0] - tolerance) or np.any(query > grid[-1] + tolerance):
        raise ValueError("query lies outside cached state support")
    fractional = (query - grid[0]) / step
    low = np.floor(fractional + tolerance).astype(int)
    low = np.clip(low, 0, len(grid) - 1)
    high = np.minimum(low + 1, len(grid) - 1)
    return low, high, fractional - low


def training_winner(measured, training_mask, model) -> int:
    training = np.asarray(training_mask, dtype=bool)
    residual = np.asarray(measured)[None, None, training] - model[..., training]
    residual -= residual.mean(axis=-1, keepdims=True)
    return int(np.argmin(np.mean(residual**2, axis=-1)))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _catalogue_payload(snapshot_digest: str) -> bytes:
    program = """\
import base64,sys
from pathlib import Path
from leo.operations.tle_archive import TleArchiveReader
digest=sys.argv[1]
archive=TleArchiveReader(Path('/var/lib/leo/tle'))
refs=[x for x in archive.list_snapshots() if x.digest==digest]
if not refs: raise ValueError('snapshot digest absent')
print(base64.b64encode(archive.read(refs[0]).encode()).decode())
"""
    result = subprocess.run(
        ["sudo", "-n", "-u", "leo", sys.executable, "-c", program, snapshot_digest],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = base64.b64decode(result.stdout)
    if "sha256:" + hashlib.sha256(payload).hexdigest() != snapshot_digest:
        raise ValueError("catalogue payload digest mismatch")
    return payload


def _exact_prediction(joint, evidence, arrays, tracks, candidate_ids, point, payload):
    catalogue = parse_element_sets(payload.decode("ascii"))
    lookup = {str(number): index for index, number in enumerate(catalogue.satellite_numbers)}
    indices = [lookup[value] for value in candidate_ids]
    times = np.concatenate([np.asarray(track["times_s"], dtype=float) for track in tracks])
    query = (times[None, :] + TAUS[:, None]).reshape(-1)
    epochs = evidence["start_utc_ns"] + np.rint(query * 1e9).astype(np.int64)
    state = propagate_grid(
        catalogue,
        SamplingGrid(tuple(map(int, epochs)), 0, 1.0),
        indices,
    )
    jd, fraction = julian_day_from_utc_ns(epochs)
    position, velocity = teme_to_ecef(
        state.position_teme_km,
        state.velocity_teme_km_s,
        greenwich_mean_sidereal_time_rad(jd, fraction),
    )
    receiver, _ = joint.receiver_ecef(point[0], point[1])
    delta = position - receiver
    distance = np.linalg.norm(delta, axis=-1)
    doppler = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocity, axis=-1) / distance
    return doppler.reshape(len(candidate_ids), len(TAUS), len(times))


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    manifest = json.loads(args.manifest.read_text())
    training = manifest["partitions"]["train"]["session_ids"]
    joint = _load(args.joint_tool, "prediction_precision_joint")
    cache_index = {}
    cache_digests = {}
    for path in sorted(args.replication_root.glob("block_*/cache/cache_manifest.json")):
        cache_digests[path.parent.parent.name] = _digest(path)
        for scan in json.loads(path.read_text())["scans"]:
            cache_index[scan["session_id"]] = path.parent
    sessions = [sid for sid in training if sid in cache_index][:3]
    if len(sessions) != 3:
        raise ValueError("three cached training sessions unavailable")
    rows = []
    sources = {}
    for sid in sessions:
        evidence, arrays = joint.load_scan_cache(cache_index[sid], sid)
        tracks = evidence["tracks"][:4]
        candidates = list(map(str, arrays["candidate_id"][:3]))
        payload = _catalogue_payload(evidence["snapshot_digest"])
        sources[sid] = {
            "snapshot_digest": evidence["snapshot_digest"],
            "start_utc_ns": evidence["start_utc_ns"],
            "cache": str(cache_index[sid]),
        }
        for track in tracks:
            query = np.asarray(track["times_s"])[None, :] + TAUS[:, None]
            interpolation_indices(arrays["time_grid_s"], query)
        for point_id, latitude, longitude in POINTS:
            exact = _exact_prediction(
                joint, evidence, arrays, tracks, candidates, (latitude, longitude), payload
            )
            offset = 0
            for track in tracks:
                count = len(track["times_s"])
                cached = joint.prediction_for_track(
                    evidence,
                    arrays,
                    track,
                    latitude,
                    longitude,
                    taus_s=TAUS,
                ).predictions_hz[: len(candidates)]
                error = cached - exact[:, :, offset : offset + count]
                exact_track = exact[:, :, offset : offset + count]
                offset += count
                centered = error - error.mean(axis=-1, keepdims=True)
                cached_winner = training_winner(
                    track["measured_hz"], track["training_mask"], cached
                )
                exact_winner = training_winner(
                    track["measured_hz"], track["training_mask"], exact_track
                )
                rows.append(
                    {
                        "session_id": sid,
                        "point_id": point_id,
                        "track_id": track["track_id"],
                        "observations": count,
                        "candidate_count": len(candidates),
                        "cached_training_winner_flat_index": cached_winner,
                        "exact_training_winner_flat_index": exact_winner,
                        "training_winner_changed": cached_winner != exact_winner,
                        "raw_rms_hz": float(np.sqrt(np.mean(error**2))),
                        "raw_max_abs_hz": float(np.max(np.abs(error))),
                        "cfo_removed_rms_hz": float(np.sqrt(np.mean(centered**2))),
                        "cfo_removed_max_abs_hz": float(np.max(np.abs(centered))),
                    }
                )
    result = {
        "schema": "position-prediction-precision-audit/v1",
        "scope": "three frozen random-group training scans; first four tracks and candidates",
        "points": [dict(point_id=x[0], latitude_deg=x[1], longitude_deg=x[2]) for x in POINTS],
        "taus_s": TAUS.tolist(),
        "counts": {"sessions": len(sessions), "track_point_rows": len(rows)},
        "training_ranking": {
            "winner_changes": sum(row["training_winner_changed"] for row in rows),
            "comparisons": len(rows),
        },
        "error_hz": {
            "raw_rms": float(np.sqrt(np.mean([row["raw_rms_hz"] ** 2 for row in rows]))),
            "raw_max_abs": max(row["raw_max_abs_hz"] for row in rows),
            "cfo_removed_rms": float(
                np.sqrt(np.mean([row["cfo_removed_rms_hz"] ** 2 for row in rows]))
            ),
            "cfo_removed_max_abs": max(row["cfo_removed_max_abs_hz"] for row in rows),
        },
        "cache_support_checked": True,
        "negative_indexing_possible": False,
        "sources": sources,
        "bindings": {
            "manifest": _digest(args.manifest),
            "joint_tool": _digest(args.joint_tool),
            "audit_tool": _digest(Path(__file__)),
            "cache_manifests": cache_digests,
        },
        "rows": rows,
    }
    args.output.mkdir(parents=True)
    (args.output / "precision_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(json.dumps(result["error_hz"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--joint-tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
