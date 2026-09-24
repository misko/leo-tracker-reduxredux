#!/usr/bin/env python3
"""Run a bounded conditional DS2 LT3D-001A geometry/cone diagnostic.

The input is a sealed, target-session-only causal export.  Its candidate list
comes from saved site-assisted reviews, so this is deliberately a geometry
consistency and restricted-candidate position diagnostic, never a blind fix.
No reference coordinate is accepted or read here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from leo.analysis.research.formal_orbit import doppler_hz
from leo.analysis.research.regional_doppler import Region

HERE = Path(__file__).resolve().parent
CAP_HZ = 800.0
PRIOR = {
    "name": "Sacramento-500km",
    "latitude_deg": 38.5816,
    "longitude_deg": -121.4944,
    "width_km": 1000.0,
    "height_km": 1000.0,
}
FULL_FOVS = (10, 20, 25, 30, 40, 50, 60, 70, 80, 90)
LOCAL_FOVS = (10, 20, 25, 30, 40, 50)
FIXED_HALF_ANGLES = (10, 15, 20, 30)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Episode:
    session_id: str
    track_id: str
    receiver_id: int
    observed: np.ndarray
    training: np.ndarray
    time_s: np.ndarray
    candidate_id: np.ndarray
    position: np.ndarray
    velocity: np.ndarray

    @property
    def weight_s(self) -> float:
        return max(0.01, float(np.ptp(self.time_s)))


def parse(path: Path) -> tuple[list[Episode], dict[str, Any]]:
    raw = json.loads(path.read_text())
    if raw.get("schema") != "ds2-geometry-cone-causal-inputs/v1":
        raise ValueError("unexpected causal input schema")
    if raw.get("identity_policy") != "saved-site-assisted-leading-candidate; conditional-only":
        raise ValueError("input identity policy is not conditional saved evidence")
    episodes = []
    for scan in raw["sessions"]:
        for row in scan["episodes"]:
            episode = Episode(
                scan["session_id"],
                row["track_id"],
                int(row["receiver_id"]),
                np.asarray(row["observed_hz"], float),
                np.asarray(row["training"], bool),
                np.asarray(row["time_s"], float),
                np.asarray(row["candidate_id"], str),
                np.asarray(row["position_ecef_km"], float),
                np.asarray(row["velocity_ecef_km_s"], float),
            )
            if episode.receiver_id not in (0, 1) or len(episode.observed) < 4:
                raise ValueError(f"invalid episode {episode.track_id}")
            if not np.any(episode.training) or not np.any(~episode.training):
                raise ValueError(f"missing randomized holdout {episode.track_id}")
            episodes.append(episode)
    return episodes, raw


def enu_directions(
    latitude: float, longitude: float, receiver: np.ndarray, position: np.ndarray
) -> np.ndarray:
    lat, lon = np.radians([latitude, longitude])
    basis = np.asarray(
        [
            [-np.sin(lon), np.cos(lon), 0.0],
            [-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)],
            [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)],
        ]
    )
    delta = position - receiver
    delta /= np.linalg.norm(delta, axis=-1, keepdims=True)
    return delta @ basis.T


def orientations() -> np.ndarray:
    # Coarse but complete upward hemisphere search: 15-degree tilt/yaw/azimuth.
    rows = [(0, 0, yaw) for yaw in range(0, 360, 15)]
    rows += [
        (tilt, azimuth, yaw)
        for tilt in range(5, 46, 5)
        for azimuth in range(0, 360, 15)
        for yaw in range(0, 360, 15)
    ]
    return np.asarray(rows, dtype=np.int16)


def axes(grid: np.ndarray) -> np.ndarray:
    body = np.asarray(
        [
            [-np.sin(np.radians(10)), 0.0, np.cos(np.radians(10))],
            [np.sin(np.radians(10)), 0.0, np.cos(np.radians(10))],
        ]
    )
    tilt, azimuth, yaw = grid.T.astype(float)
    common = (
        Rotation.from_euler("z", azimuth[:, None], degrees=True)
        * Rotation.from_euler("y", tilt[:, None], degrees=True)
        * Rotation.from_euler("z", -azimuth[:, None], degrees=True)
    )
    transform = common * Rotation.from_euler("z", yaw[:, None], degrees=True)
    result = np.stack((transform.apply(body[0]), transform.apply(body[1])), axis=1)
    assert np.allclose(
        np.sum(result[:, 0] * result[:, 1], axis=1), np.cos(np.radians(20)), atol=1e-10
    )
    return result


def point(region: Region, xy: np.ndarray) -> tuple[float, float, np.ndarray]:
    item = region.points([float(xy[0])], [float(xy[1])])
    return float(item.latitude_deg[0]), float(item.longitude_deg[0]), np.asarray(item.ecef_km[0])


def prepared(episodes: list[Episode], region: Region, xy: np.ndarray) -> list[dict[str, Any]]:
    lat, lon, receiver = point(region, xy)
    rows = []
    for item in episodes:
        prediction = np.asarray(
            [doppler_hz(receiver, p, v) for p, v in zip(item.position, item.velocity, strict=True)]
        )
        raw = item.observed[None, :] - prediction
        offsets = np.mean(raw[:, item.training], axis=1)
        errors = raw - offsets[:, None]
        rms = np.sqrt(np.mean(errors[:, item.training] ** 2, axis=1))
        cost = np.minimum((rms / CAP_HZ) ** 2, 1.0)
        directions = enu_directions(lat, lon, receiver, item.position)
        visible = np.max(directions[:, :, 2], axis=1) >= 0.0
        viable = visible & (cost < 1.0)
        baseline = int(np.argmin(np.where(visible, cost, np.inf))) if np.any(visible) else None
        rows.append(
            {
                "episode": item,
                "errors": errors,
                "cost": cost,
                "directions": directions,
                "visible": visible,
                "viable": viable,
                "baseline": baseline,
            }
        )
    return rows


def baseline_loss(rows: list[dict[str, Any]]) -> float:
    numerator = 0.0
    denom = 0.0
    for row in rows:
        weight = row["episode"].weight_s
        numerator += weight * (1.0 if row["baseline"] is None else row["cost"][row["baseline"]])
        denom += weight
    return numerator / denom


def fit_baseline(episodes: list[Episode], region: Region) -> dict[str, Any]:
    def loss(xy: np.ndarray) -> float:
        return baseline_loss(prepared(episodes, region, xy))

    grid = np.arange(-500.0, 501.0, 250.0)
    seeds = sorted(
        (loss(np.asarray([east, north])), east, north) for east in grid for north in grid
    )[:5]
    attempts = []
    for _, east, north in seeds:
        fit = minimize(
            loss,
            np.asarray([east, north]),
            method="Powell",
            bounds=[(-500, 500), (-500, 500)],
            options={"maxiter": 180, "xtol": 0.02, "ftol": 1e-7},
        )
        attempts.append(fit)
    winner = min(attempts, key=lambda value: float(value.fun))
    latitude, longitude, _ = point(region, winner.x)
    return {
        "xy_km": winner.x.tolist(),
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "training_capped_loss": float(winner.fun),
        "attempt_count": len(attempts),
        "converged": bool(winner.success),
        "message": str(winner.message),
    }


def fit_orientation(
    rows: list[dict[str, Any]], mount_axes: np.ndarray, mapping: tuple[int, int], full_fov: float
) -> tuple[int, float]:
    threshold = np.cos(np.radians(full_fov / 2))
    score = np.zeros(len(mount_axes))
    for row in rows:
        base = row["baseline"]
        if base is None or row["cost"][base] >= 1:
            continue
        direction = row["directions"][base, row["episode"].training]
        axis = mount_axes[:, mapping[row["episode"].receiver_id]]
        contained = np.min(axis @ direction.T, axis=1) >= threshold
        score += row["episode"].weight_s * (1 - row["cost"][base]) * contained
    best = int(np.argmax(score))
    return best, float(score[best])


def score_cone(
    rows: list[dict[str, Any]],
    mount_axes: np.ndarray,
    orientation: int,
    mapping: tuple[int, int],
    full_fov: float,
) -> dict[str, Any]:
    threshold = np.cos(np.radians(full_fov / 2))
    train_num = held_num = held_sq = 0.0
    held_count = supported = changed = 0
    supported_weight = 0.0
    assignments = []
    for row in rows:
        item = row["episode"]
        axis = mount_axes[orientation, mapping[item.receiver_id]]
        minimum = np.min(row["directions"][:, item.training] @ axis, axis=1)
        feasible = row["viable"] & (minimum >= threshold)
        candidate = (
            int(np.argmin(np.where(feasible, row["cost"], np.inf))) if np.any(feasible) else None
        )
        weight = item.weight_s
        if candidate is None:
            train_cost = held_cost = 1.0
        else:
            supported += 1
            supported_weight += weight
            changed += candidate != row["baseline"]
            train_cost = float(row["cost"][candidate])
            held = row["errors"][candidate, ~item.training]
            held_cost = min(float(np.mean(held**2)) / CAP_HZ**2, 1.0)
            held_sq += float(np.sum(held**2))
            held_count += len(held)
        train_num += weight * train_cost
        held_num += weight * held_cost
        assignments.append(
            {
                "track_id": item.track_id,
                "receiver_id": item.receiver_id,
                "baseline_candidate_id": None
                if row["baseline"] is None
                else str(item.candidate_id[row["baseline"]]),
                "cone_candidate_id": None
                if candidate is None
                else str(item.candidate_id[candidate]),
            }
        )
    denom = sum(row["episode"].weight_s for row in rows)
    return {
        "training_capped_loss": train_num / denom,
        "held_capped_loss": held_num / denom,
        "supported_tracks": supported,
        "unsupported_tracks": len(rows) - supported,
        "supported_occupied_second_fraction": supported_weight / denom,
        "changed_candidate_id_count": changed,
        "held_rms_hz_supported": None if not held_count else float(np.sqrt(held_sq / held_count)),
        "assignments": assignments,
    }


def profile_quantiles(
    rows: list[dict[str, Any]], mount_axes: np.ndarray, mapping: tuple[int, int]
) -> dict[str, Any]:
    values = []
    for row in rows:
        base = row["baseline"]
        if base is not None:
            item = row["episode"]
            midpoint = row["directions"][base, len(item.observed) // 2]
            values.append((item.receiver_id, midpoint, item.weight_s))
    if not values:
        return {"state": "insufficient"}
    rid = np.asarray([x[0] for x in values], int)
    directions = np.asarray([x[1] for x in values])
    weights = np.asarray([x[2] for x in values])
    best = None
    for index, axes_for_orientation in enumerate(mount_axes):
        selected = axes_for_orientation[np.asarray(mapping)[rid]]
        angle = np.degrees(np.arccos(np.clip(np.sum(selected * directions, axis=1), -1, 1)))
        order = np.argsort(angle)
        cumulative = np.cumsum(weights[order]) / weights.sum()
        quantiles = {
            str(q): float(angle[order[np.searchsorted(cumulative, q, side="left")]])
            for q in (0.5, 0.8, 0.95)
        }
        candidate = (quantiles["0.8"], index, quantiles)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return {"state": "complete", "orientation_index": best[1], "required_half_angles_deg": best[2]}


def evaluate_location(
    episodes: list[Episode],
    region: Region,
    xy: np.ndarray,
    mount_axes: np.ndarray,
    widths: tuple[int, ...],
) -> dict[str, Any]:
    rows = prepared(episodes, region, xy)
    mappings = ((0, 1), (1, 0))
    scenarios = []
    for width in widths:
        candidates = []
        for mapping in mappings:
            orient, gain = fit_orientation(rows, mount_axes, mapping, width)
            value = score_cone(rows, mount_axes, orient, mapping, width)
            value.update(
                {
                    "mapping": list(mapping),
                    "orientation_index": orient,
                    "stage_baseline_gain": gain,
                    "full_fov_deg": width,
                }
            )
            candidates.append(value)
        scenarios.append(
            min(candidates, key=lambda value: (value["training_capped_loss"], value["mapping"]))
        )
    lat, lon, _ = point(region, xy)
    return {
        "xy_km": list(map(float, xy)),
        "latitude_deg": lat,
        "longitude_deg": lon,
        "baseline_training_capped_loss": baseline_loss(rows),
        "track_count": len(rows),
        "scenarios": scenarios,
        "cone_quantiles": [
            dict(mapping=list(mapping), **profile_quantiles(rows, mount_axes, mapping))
            for mapping in mappings
        ],
    }


def local_cone_grid(
    episodes: list[Episode], region: Region, baseline_xy: np.ndarray, mount_axes: np.ndarray
) -> dict[str, Any]:
    cells = []
    for east in (-50.0, 0.0, 50.0):
        for north in (-50.0, 0.0, 50.0):
            cells.append(
                evaluate_location(
                    episodes, region, baseline_xy + [east, north], mount_axes, LOCAL_FOVS
                )
            )
    winners = {}
    for width in LOCAL_FOVS:
        choices = [(cell["scenarios"][LOCAL_FOVS.index(width)], cell) for cell in cells]
        best, cell = min(
            choices, key=lambda item: (item[0]["training_capped_loss"], item[1]["xy_km"])
        )
        winners[str(width)] = {
            "full_fov_deg": width,
            "xy_km": cell["xy_km"],
            "latitude_deg": cell["latitude_deg"],
            "longitude_deg": cell["longitude_deg"],
            **best,
        }
    return {"grid_spacing_km": 50.0, "cells": cells, "winners": winners}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HERE / "causal-inputs.json")
    parser.add_argument("--output", type=Path, default=HERE / "inference.json")
    args = parser.parse_args()
    started = time.monotonic()
    episodes, raw = parse(args.input)
    region = Region(
        PRIOR["latitude_deg"], PRIOR["longitude_deg"], PRIOR["width_km"], PRIOR["height_km"]
    )
    grid, mount_axes = orientations(), axes(orientations())
    by_session = {
        sid: [item for item in episodes if item.session_id == sid]
        for sid in sorted({item.session_id for item in episodes})
    }
    results = []
    for label, bundle in [*by_session.items(), ("joint-three-geometry-captures", episodes)]:
        baseline = fit_baseline(bundle, region)
        detailed = evaluate_location(
            bundle, region, np.asarray(baseline["xy_km"]), mount_axes, FULL_FOVS
        )
        local = local_cone_grid(bundle, region, np.asarray(baseline["xy_km"]), mount_axes)
        fixed = {
            str(angle): next(x for x in detailed["scenarios"] if x["full_fov_deg"] == 2 * angle)
            for angle in FIXED_HALF_ANGLES
        }
        results.append(
            {
                "label": label,
                "session_ids": sorted({item.session_id for item in bundle}),
                "baseline": baseline,
                "staged_full_fov": detailed,
                "fixed_hard_half_angle": fixed,
                "local_fitted_cone": local,
            }
        )
    out = {
        "schema": "ds2-lt3d-geometry-cone-conditional-inference/v1",
        "complete": True,
        "reference_used_for_inference": False,
        "held_used_for_selection": False,
        "identity_scope": "saved site-assisted review candidates; conditional diagnostic only",
        "position_scope": (
            "restricted-candidate conditional position diagnostic; not blind positioning"
        ),
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
        "input_sha256": digest_file(args.input),
        "orientation_count": int(len(grid)),
        "full_fov_deg": list(FULL_FOVS),
        "local_fitted_full_fov_deg": list(LOCAL_FOVS),
        "fixed_half_angle_deg": list(FIXED_HALF_ANGLES),
        "results": results,
        "elapsed_s": time.monotonic() - started,
        "bindings": {
            "source": digest_file(Path(__file__)),
            "station_geometry": digest_file(
                HERE.parents[1] / "src/leo/station/gauss-r21-lt3d-001a-20260920-v1.json"
            ),
        },
    }
    args.output.write_text(canonical(out))
    args.output.with_suffix(".sha256").write_text(
        hashlib.sha256(args.output.read_bytes()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
