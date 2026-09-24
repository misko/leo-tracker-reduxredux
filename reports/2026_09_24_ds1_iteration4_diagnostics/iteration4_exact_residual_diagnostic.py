#!/usr/bin/env python3
"""Reference-free exact-winner residual slices and fixed matched ablation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUT = ROOT / "reports/2026_09_24_ds1_joint_rate_search/iteration4-results.json"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE_ROOT = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
SCALE_BOUND = 2.0e-3


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def q(values: np.ndarray) -> dict[str, float]:
    return {
        name: float(np.quantile(values, point))
        for name, point in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9))
    }


def group_stats(key: np.ndarray, error: np.ndarray, limit: int = 12) -> list[dict[str, Any]]:
    rows = []
    for value in sorted(set(map(str, key))):
        mask = key.astype(str) == value
        rows.append(
            {
                "key": value,
                "observations": int(mask.sum()),
                "mean_hz": float(error[mask].mean()),
                "rms_hz": float(np.sqrt(np.mean(error[mask] ** 2))),
            }
        )
    return sorted(rows, key=lambda row: (-row["rms_hz"], -row["observations"], row["key"]))[:limit]


def binned(name: str, value: np.ndarray, error: np.ndarray, count: int = 5) -> dict[str, Any]:
    edges = np.quantile(value, np.linspace(0, 1, count + 1))
    rows = []
    for index in range(count):
        mask = (value >= edges[index]) & (
            (value <= edges[index + 1]) if index == count - 1 else (value < edges[index + 1])
        )
        rows.append(
            {
                "bin": index,
                "low": float(edges[index]),
                "high": float(edges[index + 1]),
                "observations": int(mask.sum()),
                "mean_hz": float(error[mask].mean()),
                "rms_hz": float(np.sqrt(np.mean(error[mask] ** 2))),
            }
        )
    return {"variable": name, "quantile_edges": [float(v) for v in edges], "bins": rows}


def centered(values: np.ndarray, track: np.ndarray) -> np.ndarray:
    answer = values.copy()
    for label in np.unique(track):
        mask = track == label
        answer[mask] -= answer[mask].mean()
    return answer


def capped_loss(error: np.ndarray, track: np.ndarray, weights: dict[str, int]) -> float:
    total = 0.0
    for label, weight in weights.items():
        values = error[track == label]
        total += weight * min((float(np.sqrt(np.mean(values**2))) / 800.0) ** 2, 1.0)
    return total / sum(weights.values())


def task(group: str) -> dict[str, Any]:
    source = json.loads(
        (SOURCE_ROOT / f"one-hour--train-{group}--prefix-6--reno--global_time.json").read_text()
    )
    if source.get("reference_used_for_fit") is not False or source.get("partition") != "train":
        raise ValueError("source must be reference-free TRAIN artifact")
    return {
        "task_id": "iteration4-residual-" + group,
        "group_id": group,
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def diagnose(row: dict[str, Any], existing: Any, orbit: Any) -> dict[str, Any]:
    group, winner = row["group_id"], row["winner"]
    engine = existing.FullObservationEngine(existing.validate_task(task(group)))
    data = existing._make_exact_prepared(
        engine,
        orbit,
        winner["latitude_deg"],
        winner["longitude_deg"],
        winner["tau_s"],
        winner["track_associations"],
    )
    receiver, up = engine.search.receiver_ecef(winner["latitude_deg"], winner["longitude_deg"])
    fit = existing._rate_fit_full(data, receiver, engine.search, orbit)
    labels, source_i = np.unique(data.source.astype(str), return_inverse=True)
    tracks, track_i = np.unique(data.track.astype(str), return_inverse=True)
    rates = np.asarray([fit["rate_corrections_s_h"][str(label)] for label in labels])
    phase = data.age_h * rates[source_i]
    point = orbit.quartic(data.p_nodes, phase)
    predicted = orbit.doppler(receiver, point, orbit.quartic(data.v_nodes, phase), engine.search)
    residual = data.y - predicted
    cfo = np.asarray([residual[track_i == i].mean() for i in range(len(tracks))])
    error = residual - cfo[track_i]
    centered_predicted = centered(predicted, data.track.astype(str))
    # The ablation is fixed before inspecting its outcome: one bounded common
    # fractional Doppler-scale nuisance, fitted only after per-track CFO.
    denominator = float(centered_predicted @ centered_predicted)
    raw_scale = float(centered_predicted @ error / denominator)
    scale = max(-SCALE_BOUND, min(SCALE_BOUND, raw_scale))
    scale_error = centered(error - scale * centered_predicted, data.track.astype(str))
    session_scale = {}
    session_error = error.copy()
    for sid in np.unique(data.session.astype(str)):
        mask = data.session.astype(str) == sid
        local = float(
            centered_predicted[mask]
            @ error[mask]
            / (centered_predicted[mask] @ centered_predicted[mask])
        )
        session_scale[sid] = max(-SCALE_BOUND, min(SCALE_BOUND, local))
        session_error[mask] -= session_scale[sid] * centered_predicted[mask]
    session_error = centered(session_error, data.track.astype(str))
    lat, lon = map(math.radians, (winner["latitude_deg"], winner["longitude_deg"]))
    east = np.asarray([-math.sin(lon), math.cos(lon), 0.0])
    north = np.asarray(
        [-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)]
    )
    unit = (point - receiver) / np.linalg.norm(point - receiver, axis=1)[:, None]
    elevation = np.degrees(np.arcsin(np.clip(unit @ up, -1, 1)))
    azimuth = (np.degrees(np.arctan2(unit @ east, unit @ north)) + 360.0) % 360.0
    duration = np.empty(len(error))
    for label in tracks:
        mask = data.track.astype(str) == label
        duration[mask] = np.ptp(data.time_s[mask])
    scan_time = data.time_s.copy()
    scan_time -= min(scan_time)
    return {
        "group_id": group,
        "winner": {key: winner[key] for key in ("latitude_deg", "longitude_deg", "tau_s")},
        "exact_fit": {
            key: fit[key]
            for key in (
                "full_observation_capped_loss",
                "converged",
                "iterations",
                "rate_boundary_count",
                "maximum_phase_s",
            )
        },
        "observations": int(len(error)),
        "tracks": int(len(tracks)),
        "norads": int(len(labels)),
        "residual_overall": {"rms_hz": float(np.sqrt(np.mean(error**2))), "quantiles_hz": q(error)},
        "by_scan_session": group_stats(data.session.astype(str), error),
        "by_norad_highest_rms": group_stats(data.source.astype(str), error),
        "by_tle_age_h": binned("tle_age_h", data.age_h, error),
        "by_scan_time_s": binned("scan_time_s_from_group_minimum", scan_time, error),
        "by_elevation_deg": binned("elevation_deg", elevation, error),
        "by_azimuth_deg": binned("azimuth_deg", azimuth, error),
        "by_track_duration_s": binned("track_duration_s", duration, error),
        "receiver_channel": {
            "available": False,
            "reason": (
                "iteration-4 receipt exposes session and hashed observation IDs, but no "
                "receiver/channel field"
            ),
        },
        "matched_scale_ablation": {
            "model": "per-track CFO plus one common bounded fractional Doppler scale",
            "bound": SCALE_BOUND,
            "unconstrained_scale": raw_scale,
            "fitted_scale": scale,
            "baseline_capped_loss": capped_loss(error, data.track.astype(str), data.weights),
            "scale_capped_loss": capped_loss(scale_error, data.track.astype(str), data.weights),
            "baseline_rms_hz": float(np.sqrt(np.mean(error**2))),
            "scale_rms_hz": float(np.sqrt(np.mean(scale_error**2))),
            "correlation_with_track_centered_doppler": float(
                np.corrcoef(centered_predicted, error)[0, 1]
            ),
            "session_scale_exploratory": session_scale,
            "session_scale_capped_loss": capped_loss(
                session_error, data.track.astype(str), data.weights
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    document = json.loads(INPUT.read_text())
    if document.get("complete") is not True or document.get("reference_used_for_fit") is not False:
        raise ValueError("invalid reference-free iteration4 input")
    existing, orbit = (
        load(RUNNER, "iteration4_residual_existing"),
        load(ORBIT, "iteration4_residual_orbit"),
    )
    rows = [diagnose(row, existing, orbit) for row in document["results"]]
    payload = {
        "schema": "ds1-iteration4-exact-winner-residual-diagnostic/v1",
        "complete": True,
        "reference_used_for_fit": False,
        "fixed_winner_only": True,
        "input": {"path": str(INPUT), "sha256": digest(INPUT)},
        "ablation_predeclared": {
            "model": "common fractional Doppler scale",
            "bound": SCALE_BOUND,
            "no_candidate_or_position_selection": True,
        },
        "bindings": {
            "driver": digest(Path(__file__)),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "groups": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
