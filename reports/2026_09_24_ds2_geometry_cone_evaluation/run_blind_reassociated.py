#!/usr/bin/env python3
"""Run the DS2 full-catalogue, blind/re-associated geometry-cone diagnostic.

Unlike ``run.py``, this program only reads receipt-bound portable candidate
caches.  The cache is a causal, non-debris Starlink catalogue restricted by a
predeclared Sacramento/Reno visibility envelope; it contains no saved
site-assisted identity.  The known coordinate is neither accepted nor read.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.regional_doppler import Region

HERE = Path(__file__).resolve().parent
CACHE_SCHEMA = "long-adaptive-tle-response-free-cache/v1"
SESSIONS = (
    "scan-fw-f3ce5fe73aa40506",
    "scan-fw-9f3d5067d149118e",
    "scan-fw-cfcf667726e80735",
)
PRIOR = {
    "name": "Sacramento-250km-predeclared",
    "latitude_deg": 38.5816,
    "longitude_deg": -121.4944,
    "width_km": 500.0,
    "height_km": 500.0,
}


def load_base() -> Any:
    spec = importlib.util.spec_from_file_location("ds2_geometry_conditional", HERE / "run.py")
    if spec is None or spec.loader is None:
        raise ImportError("cannot load conditional geometry helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = load_base()


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def parse_labels(path: Path) -> dict[str, dict[str, int]]:
    raw = json.loads(path.read_text())
    if raw.get("schema") != "ds2-portable-track-receiver-labels/v1":
        raise ValueError("unexpected receiver-label schema")
    return {
        scan["session_id"]: {
            track["track_id"]: int(track["receiver_id"]) for track in scan["tracks"]
        }
        for scan in raw["sessions"]
    }


def interpolate(states: np.lib.npyio.NpzFile, times_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    grid = np.asarray(states["receive_plus_tau_offset_ns"], float) / 1e9
    if times_s.min() < grid[0] or times_s.max() > grid[-1]:
        raise ValueError("receipt evidence is outside the portable state cache")
    fraction = (times_s - grid[0]) / (grid[1] - grid[0])
    low = np.floor(fraction).astype(int)
    high = np.minimum(low + 1, len(grid) - 1)
    weight = fraction - low
    position = states["position_ecef_km"][:, low, :] * (1.0 - weight)[None, :, None]
    position += states["position_ecef_km"][:, high, :] * weight[None, :, None]
    velocity = states["velocity_ecef_km_s"][:, low, :] * (1.0 - weight)[None, :, None]
    velocity += states["velocity_ecef_km_s"][:, high, :] * weight[None, :, None]
    return position, velocity


def load_episodes(
    cache_root: Path, labels: dict[str, dict[str, int]]
) -> tuple[list[Any], dict[str, Any]]:
    episodes = []
    receipts: dict[str, Any] = {}
    for session_id in SESSIONS:
        receipt_path = cache_root / session_id / "cache_receipt.json"
        states_path = cache_root / session_id / "state_cache.npz"
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("schema") != CACHE_SCHEMA:
            raise ValueError(f"unexpected cache schema for {session_id}")
        if "site-assisted" in str(receipt.get("candidate_policy", "")).lower():
            raise ValueError("portable cache may not use site-assisted identities")
        receipts[session_id] = receipt
        with np.load(states_path) as states:
            candidate_id = np.asarray(states["candidate_id"], str)
            for track in receipt["prepared_evidence"]["tracks"]:
                track_id = track["track_id"]
                receiver = labels.get(session_id, {}).get(track_id)
                if receiver not in (0, 1):
                    raise ValueError(f"missing receiver binding for {session_id}/{track_id}")
                observed = np.asarray(track["measured_hz"], float)
                training = np.asarray(track["training_mask"], bool)
                times = np.asarray(track["times_s"], float)
                if len(observed) < 4 or not training.any() or not (~training).any():
                    raise ValueError(f"invalid randomized partition for {session_id}/{track_id}")
                position, velocity = interpolate(states, times)
                episodes.append(
                    BASE.Episode(
                        session_id,
                        track_id,
                        receiver,
                        observed,
                        training,
                        times,
                        candidate_id,
                        position,
                        velocity,
                    )
                )
    return episodes, receipts


def fit_baseline(episodes: list[Any], region: Region, radius_km: float) -> dict[str, Any]:
    def loss(xy: np.ndarray) -> float:
        return BASE.baseline_loss(BASE.prepared(episodes, region, xy))

    grid = np.linspace(-radius_km, radius_km, 5)
    seeds = sorted(
        (loss(np.asarray([east, north])), east, north) for east in grid for north in grid
    )[:5]
    attempts = []
    for _, east, north in seeds:
        attempts.append(
            minimize(
                loss,
                np.asarray([east, north]),
                method="Powell",
                bounds=[(-radius_km, radius_km), (-radius_km, radius_km)],
                options={"maxiter": 140, "xtol": 0.02, "ftol": 1e-7},
            )
        )
    winner = min(attempts, key=lambda item: float(item.fun))
    latitude, longitude, _ = BASE.point(region, winner.x)
    return {
        "xy_km": winner.x.tolist(),
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "training_capped_loss": float(winner.fun),
        "attempt_count": len(attempts),
        "converged": bool(winner.success),
        "message": str(winner.message),
    }


def local_cone_grid(
    episodes: list[Any], region: Region, center: np.ndarray, axes: np.ndarray
) -> dict[str, Any]:
    cells = []
    for east in (-25.0, 0.0, 25.0):
        for north in (-25.0, 0.0, 25.0):
            xy = center + [east, north]
            if np.max(np.abs(xy)) <= 250.0:
                cells.append(BASE.evaluate_location(episodes, region, xy, axes, BASE.LOCAL_FOVS))
    winners = {}
    for width in BASE.LOCAL_FOVS:
        scenario_index = BASE.LOCAL_FOVS.index(width)
        scenario, cell = min(
            ((cell["scenarios"][scenario_index], cell) for cell in cells),
            key=lambda item: (item[0]["training_capped_loss"], item[1]["xy_km"]),
        )
        winners[str(width)] = {
            "full_fov_deg": width,
            "xy_km": cell["xy_km"],
            "latitude_deg": cell["latitude_deg"],
            "longitude_deg": cell["longitude_deg"],
            **scenario,
        }
    return {"grid_spacing_km": 25.0, "cells": cells, "winners": winners}


def run_bundle(episodes: list[Any], region: Region, axes: np.ndarray) -> dict[str, Any]:
    baseline = fit_baseline(episodes, region, radius_km=250.0)
    xy = np.asarray(baseline["xy_km"])
    staged = BASE.evaluate_location(episodes, region, xy, axes, BASE.FULL_FOVS)
    fixed = {
        str(angle): next(row for row in staged["scenarios"] if row["full_fov_deg"] == 2 * angle)
        for angle in BASE.FIXED_HALF_ANGLES
    }
    return {
        "baseline": baseline,
        "staged_full_fov": staged,
        "fixed_hard_half_angle": fixed,
        "local_fitted_cone": local_cone_grid(episodes, region, xy, axes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--receiver-labels", type=Path, default=HERE / "blind-receiver-labels.json")
    parser.add_argument("--output", type=Path, default=HERE / "blind-inference.json")
    args = parser.parse_args()
    started = time.monotonic()
    labels = parse_labels(args.receiver_labels)
    episodes, receipts = load_episodes(args.cache_root, labels)
    region = Region(
        PRIOR["latitude_deg"],
        PRIOR["longitude_deg"],
        PRIOR["width_km"],
        PRIOR["height_km"],
    )
    grid = BASE.orientations()
    axes = BASE.axes(grid)
    by_session = {
        session_id: [item for item in episodes if item.session_id == session_id]
        for session_id in SESSIONS
    }
    results = []
    for label, bundle in [*by_session.items(), ("joint-three-geometry-captures", episodes)]:
        result = run_bundle(bundle, region, axes)
        results.append(
            {"label": label, "session_ids": sorted({item.session_id for item in bundle}), **result}
        )
    document = {
        "schema": "ds2-lt3d-geometry-cone-blind-reassociated-inference/v1",
        "complete": True,
        "reference_used_for_inference": False,
        "held_used_for_selection": False,
        "partition": "development",
        "identity_scope": (
            "full receipt-bound causal non-debris Starlink cache; point-local reassociation"
        ),
        "position_scope": (
            "blind within predeclared Sacramento-250km prior; no saved-site candidate identity"
        ),
        "candidate_policy": receipts[SESSIONS[0]]["candidate_policy"],
        "regional_filter": receipts[SESSIONS[0]]["regional_filter"],
        "session_policy": (
            "all three explicit geometry-authorized .21 captures; whole session input"
        ),
        "geometry": {
            "fixture": "LT3D-001A",
            "axis_separation_deg": 20.0,
            "mapping": "provisional; both RX-to-slot symmetries evaluated and training-selected",
            "orientation": (
                "learned ENU fixture yaw, shared tilt <=45 degrees; "
                "15-degree yaw/azimuth and 5-degree tilt grid"
            ),
        },
        "prior": PRIOR,
        "randomized_partition": (
            "receipt-bound per-track mask profiles CFO and association on training samples; "
            "held samples report diagnostics only"
        ),
        "orientation_count": int(len(grid)),
        "full_fov_deg": list(BASE.FULL_FOVS),
        "local_fitted_full_fov_deg": list(BASE.LOCAL_FOVS),
        "fixed_half_angle_deg": list(BASE.FIXED_HALF_ANGLES),
        "results": results,
        "elapsed_s": time.monotonic() - started,
        "bindings": {
            "runner": digest(Path(__file__)),
            "conditional_geometry_helpers": digest(HERE / "run.py"),
            "receiver_labels": digest(args.receiver_labels),
            "receipts": {
                session_id: digest(args.cache_root / session_id / "cache_receipt.json")
                for session_id in SESSIONS
            },
            "state_caches": {
                session_id: digest(args.cache_root / session_id / "state_cache.npz")
                for session_id in SESSIONS
            },
        },
    }
    content = json.dumps(document, indent=2, sort_keys=True) + "\n"
    args.output.write_text(content)
    args.output.with_suffix(".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
