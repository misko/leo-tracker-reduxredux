#!/usr/bin/env python3
"""Exact block jackknife of the sealed pooled TRAIN fixed-ID solution."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POOLED = ROOT / "reports/2026_09_23_pooled_train_position/results/inference.json"
FIRST = ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json"
SECOND = ROOT / "reports/2026_09_23_second_train_epoch_replication/results/inference.json"
HELPER = ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/fit.py"
SINGLE = ROOT / "reports/2026_09_23_long_training_search/search.py"
TOOL = HERE / "run.py"
CACHES = [
    Path("/tmp/leo-long-training-cache-full8h"),
    Path("/tmp/leo-long-training-cache-second8h"),
]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def inverse_offset(centre, point):
    """Return spherical east/north offset in km, inverse of offset_coordinate."""
    lat1, lon1 = np.deg2rad(centre)
    lat2, lon2 = np.deg2rad(point)
    dlon = lon2 - lon1
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    bearing = np.arctan2(y, x)
    angular = np.arctan2(
        np.hypot(y, x),
        np.sin(lat1) * np.sin(lat2) + np.cos(lat1) * np.cos(lat2) * np.cos(dlon),
    )
    distance = 6371.0088 * angular
    return np.asarray([distance * np.sin(bearing), distance * np.cos(bearing)])


def alignment(vectors):
    """Directional concentration in [0, 1], ignoring zero-length vectors."""
    rows = [np.asarray(v, dtype=float) for v in vectors if np.linalg.norm(v) > 0]
    if not rows:
        return 0.0
    return float(np.linalg.norm(np.sum(rows, axis=0)) / sum(np.linalg.norm(v) for v in rows))


def block_partition(groups, count=4):
    blocks = []
    for group_index, sessions in enumerate(groups):
        for block_index, chunk in enumerate(np.array_split(np.asarray(sessions), count)):
            blocks.append(
                {
                    "block_id": f"group{group_index + 1}_block{block_index + 1}",
                    "group": group_index + 1,
                    "session_ids": [str(value) for value in chunk],
                }
            )
    return blocks


def verify_cache_bindings(cache, bindings):
    for row in bindings:
        session = cache / row["session_id"]
        for filename, key in (("cache_receipt.json", "receipt"), ("state_cache.npz", "cache")):
            if digest(session / filename) != row[key]:
                raise ValueError(f"cache binding mismatch: {row['session_id']} {filename}")


def prepare(helper, single, sources, groups):
    tracks = []
    for source, sessions, cache in zip(sources, groups, CACHES, strict=True):
        arm = next(
            row
            for row in source["arms"]
            if row["prior"] == "sacramento"
            and row["scale_s"] == 5.0
            and ("model" not in row or row["model"] == "scan")
            and ("view_scan_count" not in row or row["view_scan_count"] == len(sessions))
        )
        scans = [
            {
                "session_id": sid,
                "tracks": [r for r in arm["fixed_tracks"] if r["session_id"] == sid],
            }
            for sid in sessions
        ]
        current, _ = helper.prepare(single, cache, sessions, scans)
        tracks.extend(current)
    return tracks


def main():
    output = HERE / "results"
    if output.exists():
        raise FileExistsError("fresh output required")
    pooled = json.loads(POOLED.read_text())
    sources = [json.loads(FIRST.read_text()), json.loads(SECOND.read_text())]
    groups = pooled["groups"]
    arm = next(a for a in pooled["arms"] if a["prior"] == "sacramento" and a["scale_s"] == 5.0)
    if pooled["held_rows_used_for_fit"] or pooled["reference_used_for_fit"]:
        raise ValueError("pooled inference is not TRAIN-only")
    if (
        digest(HELPER) != pooled["bindings"]["helper"]
        or digest(SINGLE) != pooled["bindings"]["single"]
    ):
        raise ValueError("numerical source differs from pooled seal")
    if (
        pooled["bindings"]["first"] != digest(FIRST)
        or pooled["bindings"]["second"] != digest(SECOND)
    ):
        raise ValueError("pooled parent inference binding differs")
    verify_cache_bindings(CACHES[0], sources[0]["bindings"]["caches"])
    verify_cache_bindings(CACHES[1], sources[1]["cache_bindings"])

    helper, single = load(HELPER, "bias_helper"), load(SINGLE, "bias_single")
    tracks = prepare(helper, single, sources, groups)
    if len(tracks) != arm["track_count"] or len({t["track_id"] for t in tracks}) != len(tracks):
        raise ValueError("pooled fixed-track support differs")
    expected = {
        (row["track_id"], row["candidate_id"], row["session_id"])
        for source, sessions in zip(sources, groups, strict=True)
        for arm_row in source["arms"]
        if arm_row["prior"] == "sacramento"
        and arm_row["scale_s"] == 5.0
        and ("model" not in arm_row or arm_row["model"] == "scan")
        and ("view_scan_count" not in arm_row or arm_row["view_scan_count"] == len(sessions))
        for row in arm_row["fixed_tracks"]
    }
    actual = {(row["track_id"], row["candidate_id"], row["session_id"]) for row in tracks}
    if actual != expected:
        raise ValueError("prepared fixed-ID support differs from sealed parent arms")
    prior = single.PRIORS["sacramento"]
    pooled_position = inverse_offset(prior[:2], (arm["latitude_deg"], arm["longitude_deg"]))
    blocks = block_partition(groups)
    started = time.monotonic()
    control_position, control_taus, control_trace, control_stopped, control_reason = (
        helper.coupled_polish(
            single,
            tracks,
            prior,
            pooled_position.copy(),
            dict(arm["taus_s"]),
            5.0,
        )
    )
    control_drift = control_position - pooled_position
    rows = []
    for block in blocks:
        excluded = set(block["session_ids"])
        retained = [track for track in tracks if track["session_id"] not in excluded]
        taus = {key: value for key, value in arm["taus_s"].items() if key not in excluded}
        position, taus, trace, stopped, reason = helper.coupled_polish(
            single, retained, prior, pooled_position.copy(), taus, 5.0
        )
        scored = helper.score(
            single,
            retained,
            single.offset_coordinate(prior[:2], *position),
            taus,
            5.0,
        )
        displacement = position - pooled_position
        rows.append(
            {
                **block,
                "excluded_track_count": len(tracks) - len(retained),
                "east_displacement_km": float(displacement[0]),
                "north_displacement_km": float(displacement[1]),
                "displacement_km": float(np.linalg.norm(displacement)),
                "objective_hz": scored["penalized_objective_rmse_hz"],
                "visibility_failure_count": scored["visibility_failure_count"],
                "tau_boundary_count": sum(abs(v) >= 4.998 for v in taus.values()),
                "stopping_rule_satisfied": stopped,
                "stop_reason": reason,
                "iterations": len(trace),
            }
        )
    vectors = {
        group: [
            np.asarray([row["east_displacement_km"], row["north_displacement_km"]])
            for row in rows
            if row["group"] == group
        ]
        for group in (1, 2)
    }
    means = {g: np.mean(vectors[g], axis=0) for g in (1, 2)}
    denom = float(np.linalg.norm(means[1]) * np.linalg.norm(means[2]))
    result = {
        "method": (
            "exact leave-one-contiguous-quarter refits from sealed pooled "
            "scale-5s fixed-ID solution"
        ),
        "interpretation_scope": (
            "local deletion sensitivity within the Sacramento-prior basin; contiguous blocks "
            "are not chronological held-out evaluation or calibrated uncertainty"
        ),
        "blocks": rows,
        "full_support_continuation_control": {
            "east_drift_km": float(control_drift[0]),
            "north_drift_km": float(control_drift[1]),
            "drift_km": float(np.linalg.norm(control_drift)),
            "iterations": len(control_trace),
            "stopping_rule_satisfied": control_stopped,
            "stop_reason": control_reason,
            "tau_boundary_count": sum(abs(v) >= 4.998 for v in control_taus.values()),
        },
        "summary": {
            "median_displacement_km": float(np.median([r["displacement_km"] for r in rows])),
            "maximum_displacement_km": float(max(r["displacement_km"] for r in rows)),
            "group1_alignment": alignment(vectors[1]),
            "group2_alignment": alignment(vectors[2]),
            "group_mean_cosine": float(means[1] @ means[2] / denom) if denom else None,
            "group_mean_separation_km": float(np.linalg.norm(means[1] - means[2])),
            "group1_mean_displacement_en_km": means[1].tolist(),
            "group2_mean_displacement_en_km": means[2].tolist(),
        },
        "bindings": {
            "pooled": digest(POOLED),
            "first": digest(FIRST),
            "second": digest(SECOND),
            "helper": digest(HELPER),
            "single": digest(SINGLE),
            "tool": digest(TOOL),
        },
        "pooled_position_lat_lon": [arm["latitude_deg"], arm["longitude_deg"]],
        "pooled_position_en_km": pooled_position.tolist(),
        "track_count": len(tracks),
        "runtime_s": time.monotonic() - started,
        "held_rows_used": False,
        "reference_position_read": False,
    }
    output.mkdir()
    path = output / "inference.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":", 1)[1] + "\n")


if __name__ == "__main__":
    main()
