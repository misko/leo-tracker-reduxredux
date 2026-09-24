#!/usr/bin/env python3
"""TRAIN-only, full-observation DS1 timing inference worker.

The input is one small task JSON.  This module deliberately has no reference
position, evaluation partition, or randomized-mask code path.  It reads all
qualified observations in each requested scan and seals an inference artifact
whose only selection criterion is the capped RF Doppler loss.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Each scheduler job is an independent process.  Keep NumPy's BLAS backend to
# one thread so a 16+ process DS1 queue does not multiply worker threads.
for _thread_limit in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_thread_limit] = "1"

import numpy as np  # noqa: E402  # thread limits must precede NumPy import

ROOT = Path(__file__).resolve().parents[2]
SEARCH_PATH = ROOT / "reports/2026_09_23_long_training_search/search.py"
CAP_HZ = 800.0
RESULT_SCHEMA = "ds1-train-full-inference-result/v1"
CACHE_ROOTS = {
    "20260921_00": Path("/tmp/leo-long-training-cache-full8h"),
    "20260921_16": Path("/tmp/leo-long-training-cache-second8h"),
}
METHODS = {
    "baseline",
    "shared_global_tau",
    "regularized_per_scan_tau",
    "independent_per_track_tau",
}
METHOD_ALIASES = {
    "global_time": "shared_global_tau",
    "per_scan_time": "regularized_per_scan_tau",
    "independent_per_track_time": "independent_per_track_tau",
}


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


@dataclass
class Track:
    session_id: str
    track_id: str
    times_s: np.ndarray
    measured_hz: np.ndarray
    occupied_seconds: int


@dataclass
class Session:
    session_id: str
    candidate_ids: np.ndarray
    grid_s: np.ndarray
    position: np.ndarray
    velocity: np.ndarray
    tracks: list[Track]
    receipt_digest: str
    cache_digest: str


@dataclass
class SessionTimingPlan:
    """Observation-only interpolation and reduction plan for one session.

    None of these values depends on the evaluated receiver position.  Keeping
    them here prevents every geographic visit from rebuilding the same ragged
    track layout and cache-grid interpolation indices.
    """

    starts: np.ndarray
    counts: np.ndarray
    low: np.ndarray
    high: np.ndarray
    low_weight: np.ndarray
    high_weight: np.ndarray


class FullObservationEngine:
    """Numerical scorer with analytic CFO and point-local reassociation."""

    def __init__(self, sessions: list[Session], search: Any, tau_values: np.ndarray):
        self.sessions = sessions
        self.search = search
        self.tau_values = np.asarray(tau_values, float)
        self.total_weight = sum(t.occupied_seconds for s in sessions for t in s.tracks)
        if self.total_weight <= 0:
            raise ValueError("no qualified track support")
        self._plans = {id(session): self._timing_plan(session) for session in sessions}

    def _timing_plan(self, session: Session) -> SessionTimingPlan:
        """Precompute the position-independent portions of every track curve."""
        times = np.concatenate([track.times_s for track in session.tracks])
        counts = np.asarray([len(track.times_s) for track in session.tracks], dtype=int)
        starts = np.cumsum(np.r_[0, counts[:-1]])
        query = times[:, None] + self.tau_values[None, :]
        if query.min() < session.grid_s[0] or query.max() > session.grid_s[-1]:
            raise ValueError(f"timing grid exceeds cache for {session.session_id}")
        fraction = (query - session.grid_s[0]) / (session.grid_s[1] - session.grid_s[0])
        low = np.floor(fraction).astype(int)
        high = np.minimum(low + 1, len(session.grid_s) - 1)
        high_weight = fraction - low
        return SessionTimingPlan(
            starts=starts,
            counts=counts,
            low=low,
            high=high,
            low_weight=1.0 - high_weight,
            high_weight=high_weight,
        )

    def _track_curve(
        self,
        session: Session,
        track: Track,
        latitude: float,
        longitude: float,
        track_index: int | None = None,
        receiver: np.ndarray | None = None,
        up: np.ndarray | None = None,
    ) -> dict:
        if receiver is None or up is None:
            receiver, up = self.search.receiver_ecef(latitude, longitude)
        if track_index is None:
            track_index = session.tracks.index(track)
        plan = self._plans[id(session)]
        start = int(plan.starts[track_index])
        stop = start + int(plan.counts[track_index])
        low = plan.low[start:stop]
        high = plan.high[start:stop]
        low_weight = plan.low_weight[start:stop]
        high_weight = plan.high_weight[start:stop]
        p = session.position[:, low, :] * low_weight[None, :, :, None]
        p += session.position[:, high, :] * high_weight[None, :, :, None]
        v = session.velocity[:, low, :] * low_weight[None, :, :, None]
        v += session.velocity[:, high, :] * high_weight[None, :, :, None]
        delta = p - receiver
        distance = np.linalg.norm(delta, axis=-1)
        prediction = (
            -self.search.REFERENCE_RF_HZ
            / self.search.LIGHT_KM_S
            * np.sum(delta * v, axis=-1)
            / distance
        )
        residual = track.measured_hz[None, :, None] - prediction
        # All observations are used both to profile the constant CFO and score it.
        cfo = np.mean(residual, axis=1)
        # Residual is not needed after profiling CFO.  Reuse its sizeable
        # candidate-by-observation-by-timing buffer for the centered square.
        # This is algebraically and operation-order identical to the former
        # temporary ``error`` array, while avoiding one allocation per track.
        residual -= cfo[:, None, :]
        np.square(residual, out=residual)
        rms = np.sqrt(np.mean(residual, axis=1))
        visible = np.max(np.sum(delta * up, axis=-1) / distance, axis=1) >= 0
        rms = np.where(visible, rms, np.inf)
        winners = np.argmin(rms, axis=0)
        columns = np.arange(len(self.tau_values))
        selected_rms = rms[winners, columns]
        return {
            "loss": np.minimum((selected_rms / CAP_HZ) ** 2, 1.0),
            "rms": selected_rms,
            "available": np.isfinite(selected_rms),
            "winner": winners,
            "cfo": cfo[winners, columns],
        }

    def _session_curve(self, session: Session, latitude: float, longitude: float) -> dict:
        receiver, up = self.search.receiver_ecef(latitude, longitude)
        curves = [
            self._track_curve(session, track, latitude, longitude, index, receiver, up)
            for index, track in enumerate(session.tracks)
        ]
        weighted = sum(
            t.occupied_seconds * c["loss"] for t, c in zip(session.tracks, curves, strict=True)
        )
        return {
            "loss": weighted / sum(t.occupied_seconds for t in session.tracks),
            "tracks": curves,
        }

    def _assignments(self, session: Session, curve: dict, tau_index: int) -> list[dict]:
        out = []
        for track, result in zip(session.tracks, curve["tracks"], strict=True):
            candidate = int(result["winner"][tau_index])
            out.append(
                {
                    "session_id": session.session_id,
                    "track_id": track.track_id,
                    "candidate_id": str(session.candidate_ids[candidate])
                    if result["available"][tau_index]
                    else None,
                    "constant_cfo_hz": float(result["cfo"][tau_index])
                    if result["available"][tau_index]
                    else None,
                    "full_observation_rms_hz": float(result["rms"][tau_index])
                    if result["available"][tau_index]
                    else None,
                    "observation_count": int(len(track.times_s)),
                    "occupied_seconds": track.occupied_seconds,
                }
            )
        return out

    def score(self, latitude: float, longitude: float, method: str, options: dict) -> dict:
        curves = [self._session_curve(s, latitude, longitude) for s in self.sessions]
        weights = np.asarray(
            [sum(t.occupied_seconds for t in s.tracks) for s in self.sessions], float
        )
        losses = np.asarray([c["loss"] for c in curves])
        zero = int(np.argmin(np.abs(self.tau_values)))
        if not np.isclose(self.tau_values[zero], 0.0):
            raise ValueError("tau grid must contain zero")
        if method == "baseline":
            indices = np.full(len(self.sessions), zero, int)
            objective = float(np.sum(weights * losses[:, zero]) / self.total_weight)
            parameters: dict[str, Any] = {"global_tau_s": 0.0}
        elif method == "shared_global_tau":
            aggregate = np.sum(weights[:, None] * losses, axis=0) / self.total_weight
            chosen = int(np.argmin(aggregate))
            indices = np.full(len(self.sessions), chosen, int)
            objective = float(aggregate[chosen])
            parameters = {"global_tau_s": float(self.tau_values[chosen])}
        elif method == "regularized_per_scan_tau":
            sigma = float(options.get("per_scan_sigma_s", 1.0))
            penalty_weight = float(options.get("per_scan_penalty_weight", 0.01))
            delta_limit = float(options.get("per_scan_delta_limit_s", 5.0))
            if sigma <= 0 or penalty_weight < 0 or delta_limit < 0:
                raise ValueError("invalid per-scan regularization")
            objective_by_global = np.full(len(self.tau_values), np.inf)
            index_by_global: list[np.ndarray] = []
            for global_index, global_tau in enumerate(self.tau_values):
                choices = np.full(len(self.sessions), -1, int)
                value = 0.0
                for scan_index, scan_loss in enumerate(losses):
                    delta = self.tau_values - global_tau
                    permitted = np.abs(delta) <= delta_limit + 1e-12
                    local = weights[scan_index] / self.total_weight * scan_loss
                    local = local + penalty_weight * (delta / sigma) ** 2
                    local = np.where(permitted, local, np.inf)
                    choice = int(np.argmin(local))
                    choices[scan_index] = choice
                    value += float(local[choice])
                objective_by_global[global_index] = value
                index_by_global.append(choices)
            global_index = int(np.argmin(objective_by_global))
            indices = index_by_global[global_index]
            deltas = self.tau_values[indices] - self.tau_values[global_index]
            raw_loss = float(
                np.sum(weights * losses[np.arange(len(self.sessions)), indices]) / self.total_weight
            )
            penalty = float(np.sum(penalty_weight * (deltas / sigma) ** 2))
            objective = raw_loss + penalty
            parameters = {
                "global_tau_s": float(self.tau_values[global_index]),
                "per_scan_delta_s": {
                    session.session_id: float(delta)
                    for session, delta in zip(self.sessions, deltas, strict=True)
                },
                "per_scan_penalty": penalty,
            }
        elif method == "independent_per_track_tau":
            indices = np.zeros(len(self.sessions), int)
            selected_tracks: list[list[int]] = []
            total = 0.0
            track_tau: dict[str, float] = {}
            for session_index, (session, curve) in enumerate(
                zip(self.sessions, curves, strict=True)
            ):
                choices = []
                for track, result in zip(session.tracks, curve["tracks"], strict=True):
                    choice = int(np.argmin(result["loss"]))
                    choices.append(choice)
                    total += track.occupied_seconds * float(result["loss"][choice])
                    track_tau[f"{session.session_id}:{track.track_id}"] = float(
                        self.tau_values[choice]
                    )
                selected_tracks.append(choices)
                indices[session_index] = zero
            objective = total / self.total_weight
            parameters = {"per_track_tau_s": track_tau}
            assignments = []
            for session, curve, choices in zip(self.sessions, curves, selected_tracks, strict=True):
                for track, result, choice in zip(
                    session.tracks, curve["tracks"], choices, strict=True
                ):
                    candidate = int(result["winner"][choice])
                    assignments.append(
                        {
                            "session_id": session.session_id,
                            "track_id": track.track_id,
                            "candidate_id": str(session.candidate_ids[candidate])
                            if result["available"][choice]
                            else None,
                            "constant_cfo_hz": float(result["cfo"][choice])
                            if result["available"][choice]
                            else None,
                            "full_observation_rms_hz": float(result["rms"][choice])
                            if result["available"][choice]
                            else None,
                            "observation_count": int(len(track.times_s)),
                            "occupied_seconds": track.occupied_seconds,
                        }
                    )
            return {
                "objective": float(objective),
                "rf_capped_loss": float(objective),
                "parameters": parameters,
                "assignments": assignments,
            }
        else:  # validate_task makes this unreachable; retains a clear programmatic error.
            raise ValueError(f"unknown method: {method}")
        raw_loss = float(
            np.sum(weights * losses[np.arange(len(self.sessions)), indices]) / self.total_weight
        )
        assignments = []
        for session, curve, index in zip(self.sessions, curves, indices, strict=True):
            assignments.extend(self._assignments(session, curve, int(index)))
        return {
            "objective": objective,
            "rf_capped_loss": raw_loss,
            "parameters": parameters,
            "assignments": assignments,
        }


def validate_task(task: dict) -> dict:
    """Validate and normalize the narrow scheduler task contract."""
    required = {"task_id", "group_id", "session_ids", "prior", "method", "output_path"}
    missing = sorted(required - set(task))
    if missing:
        raise ValueError(f"task missing: {', '.join(missing)}")
    partition = task.get("partition", "train")
    if partition != "train":
        raise ValueError("only TRAIN tasks are permitted")
    sessions = task["session_ids"]
    if (
        not isinstance(sessions, list)
        or not sessions
        or not all(isinstance(x, str) for x in sessions)
    ):
        raise ValueError("session_ids must be a nonempty list of strings")
    if len(set(sessions)) != len(sessions):
        raise ValueError("session_ids must be unique")
    raw_session_groups = task.get("session_groups")
    if raw_session_groups is None:
        input_scans = task.get("input_scans")
        if input_scans is None:
            if task["group_id"] not in CACHE_ROOTS:
                raise ValueError("only DS1 TRAIN groups 20260921_00 and 20260921_16 are permitted")
            session_groups = {session_id: task["group_id"] for session_id in sessions}
        else:
            if (
                not isinstance(input_scans, list)
                or [row.get("session_id") for row in input_scans] != sessions
            ):
                raise ValueError("input_scans must be ordered exactly as session_ids")
            if any(row.get("group_id") not in CACHE_ROOTS for row in input_scans):
                raise ValueError("input_scans contains a non-TRAIN group")
            if any(
                row.get("causal_state_cache_root") not in (None, str(CACHE_ROOTS[row["group_id"]]))
                for row in input_scans
            ):
                raise ValueError("input_scans causal cache root mismatch")
            session_groups = {row["session_id"]: row["group_id"] for row in input_scans}
    else:
        if not isinstance(raw_session_groups, dict) or set(raw_session_groups) != set(sessions):
            raise ValueError("session_groups must map exactly every requested session_id")
        if any(group not in CACHE_ROOTS for group in raw_session_groups.values()):
            raise ValueError("every session_groups value must be a DS1 TRAIN group")
        session_groups = {session_id: raw_session_groups[session_id] for session_id in sessions}
    prior = task["prior"]
    latitude = prior.get("lat", prior.get("latitude_deg")) if isinstance(prior, dict) else None
    longitude = prior.get("lon", prior.get("longitude_deg")) if isinstance(prior, dict) else None
    if (
        not isinstance(prior, dict)
        or "name" not in prior
        or latitude is None
        or longitude is None
        or "radius_km" not in prior
    ):
        raise ValueError("prior needs name, lat, lon, radius_km")
    if not isinstance(prior["name"], str) or float(prior["radius_km"]) <= 0:
        raise ValueError("invalid prior")
    requested_method = task["method"]
    normalized_method = METHOD_ALIASES.get(requested_method, requested_method)
    if normalized_method not in METHODS:
        raise ValueError(f"method must be one of {sorted(METHODS)}")
    output = Path(task["output_path"])
    if not output.is_absolute():
        raise ValueError("output_path must be absolute")
    options = dict(task.get("options", {}))
    policy = options.get("observation_policy", "all_qualified_observations")
    if policy != "all_qualified_observations":
        raise ValueError("all-qualified-observations policy is required")
    if options.get("within_track_holdout", "forbidden") != "forbidden":
        raise ValueError("within-track holdout is prohibited")
    cap_hz = float(options.get("frequency_loss_cap_hz", CAP_HZ))
    if not np.isclose(cap_hz, CAP_HZ, rtol=0, atol=1e-12):
        raise ValueError("this runner has a fixed 800 Hz frequency-loss cap")
    tau_limit = float(options.get("tau_limit_s", 5.0))
    tau_step = float(options.get("tau_step_s", 0.25))
    if not (0 < tau_step <= tau_limit <= 5.0):
        raise ValueError("tau range must be inside the causal cache's +/-5 seconds")
    tau_values = np.arange(-tau_limit, tau_limit + tau_step * 0.01, tau_step)
    if not np.any(np.isclose(tau_values, 0.0, rtol=0, atol=1e-10)):
        raise ValueError("tau grid must contain zero")
    levels = tuple(
        float(v) for v in options.get("geographic_levels_km", (100, 50, 25, 12.5, 6.25, 3.125))
    )
    if not levels or any(v <= 0 for v in levels) or any(
        a <= b for a, b in zip(levels, levels[1:], strict=False)
    ):
        raise ValueError("geographic_levels_km must be strictly decreasing positive values")
    beam = int(options.get("beam_width", 3))
    if not 1 <= beam <= 16:
        raise ValueError("beam_width must be between 1 and 16")
    return {
        "task_id": str(task["task_id"]),
        "partition": partition,
        "group_id": task["group_id"],
        "session_ids": sessions,
        "session_groups": session_groups,
        "prior": {
            "name": prior["name"],
            "lat": float(latitude),
            "lon": float(longitude),
            "radius_km": float(prior["radius_km"]),
        },
        "method_requested": requested_method,
        "method": normalized_method,
        "output_path": output,
        "options": {
            **options,
            "tau_limit_s": tau_limit,
            "tau_step_s": tau_step,
            "geographic_levels_km": levels,
            "beam_width": beam,
            "observation_policy": policy,
            "minimum_track_duration_s": float(
                options.get("minimum_track_duration_s", options.get("minimum_track_span_s", 3.0))
            ),
            "frequency_loss_cap_hz": cap_hz,
        },
    }


def _load_sessions(task: dict) -> tuple[list[Session], list[dict]]:
    sessions, bindings = [], []
    minimum_span = float(task["options"]["minimum_track_duration_s"])
    for session_id in task["session_ids"]:
        session_group = task["session_groups"][session_id]
        if len(set(task["session_groups"].values())) == 1:
            root = Path(task["options"].get("cache_root", CACHE_ROOTS[session_group]))
        else:
            root = CACHE_ROOTS[session_group]
        receipt_path, cache_path = (
            root / session_id / "cache_receipt.json",
            root / session_id / "state_cache.npz",
        )
        if not receipt_path.exists() or not cache_path.exists():
            raise FileNotFoundError(f"missing causal DS1 cache for {session_id}")
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("session_id") != session_id:
            raise ValueError("cache receipt session mismatch")
        if not str(receipt.get("candidate_policy", "")).startswith(
            "all causal non-debris STARLINK"
        ):
            raise ValueError("not an all-causal DS1 candidate cache")
        with np.load(cache_path, allow_pickle=False) as archive:
            candidate_ids = archive["candidate_id"]
            grid_s = archive["receive_plus_tau_offset_ns"].astype(float) / 1e9
            position = archive["position_ecef_km"]
            velocity = archive["velocity_ecef_km_s"]
        tracks = []
        for raw in receipt["prepared_evidence"]["tracks"]:
            times = np.asarray(raw["times_s"], float)
            measured = np.asarray(raw["measured_hz"], float)
            if (
                len(times) != len(measured)
                or not np.all(np.isfinite(times))
                or not np.all(np.isfinite(measured))
            ):
                raise ValueError("invalid observation array")
            if np.ptp(times) < minimum_span:
                continue
            tracks.append(
                Track(
                    session_id,
                    str(raw["track_id"]),
                    times,
                    measured,
                    int(len(np.unique(np.floor(times)))),
                )
            )
        if not tracks:
            raise ValueError(f"no full-observation qualified tracks for {session_id}")
        sessions.append(
            Session(
                session_id,
                candidate_ids,
                grid_s,
                position,
                velocity,
                tracks,
                _digest(receipt_path),
                _digest(cache_path),
            )
        )
        bindings.append(
            {
                "session_id": session_id,
                "group_id": session_group,
                "receipt": _digest(receipt_path),
                "cache": _digest(cache_path),
                "qualified_track_count": len(tracks),
                "full_observation_count": int(sum(len(t.times_s) for t in tracks)),
            }
        )
    return sessions, bindings


def _diverse(rows: list[dict], spacing: float, count: int) -> list[dict]:
    kept = []
    for row in sorted(rows, key=lambda x: (x["objective"], x["east_km"], x["north_km"])):
        if all(
            np.hypot(row["east_km"] - old["east_km"], row["north_km"] - old["north_km"]) >= spacing
            for old in kept
        ):
            kept.append(row)
        if len(kept) == count:
            break
    return kept


def _search(engine: FullObservationEngine, task: dict) -> tuple[dict, list[dict]]:
    prior, options = task["prior"], task["options"]
    centre = (prior["lat"], prior["lon"])
    cache: dict[tuple[float, float], dict] = {}
    trace: list[dict] = []

    def visit(east: float, north: float, level: float) -> dict:
        key = (round(east, 9), round(north, 9))
        if key not in cache:
            latitude, longitude = engine.search.offset_coordinate(centre, east, north)
            if (
                engine.search.haversine_km(centre, (latitude, longitude))
                > prior["radius_km"] + 1e-9
            ):
                raise ValueError("search escaped prior")
            result = engine.score(latitude, longitude, task["method"], options)
            cache[key] = {
                "east_km": east,
                "north_km": north,
                "latitude_deg": latitude,
                "longitude_deg": longitude,
                **result,
            }
            trace.append(
                {
                    "level_km": level,
                    "east_km": east,
                    "north_km": north,
                    "latitude_deg": latitude,
                    "longitude_deg": longitude,
                    "objective": result["objective"],
                }
            )
        return cache[key]

    first = options["geographic_levels_km"][0]
    axis = np.arange(-prior["radius_km"], prior["radius_km"] + first * 0.01, first)
    current = [
        visit(float(east), float(north), first)
        for east in axis
        for north in axis
        if np.hypot(east, north) <= prior["radius_km"]
    ]
    beam = _diverse(current, first, options["beam_width"])
    for level in options["geographic_levels_km"][1:]:
        trials = list(beam)
        for parent in beam:
            for east_delta in (-level, 0.0, level):
                for north_delta in (-level, 0.0, level):
                    east, north = parent["east_km"] + east_delta, parent["north_km"] + north_delta
                    if np.hypot(east, north) <= prior["radius_km"] + 1e-9:
                        trials.append(visit(east, north, level))
        beam = _diverse(trials, level, options["beam_width"])
    winner = min(cache.values(), key=lambda x: (x["objective"], x["east_km"], x["north_km"]))
    return winner, trace


def run_task(task: dict) -> dict:
    """Run one validated task and atomically seal the inference JSON and SHA-256."""
    task = validate_task(task)
    if (
        task["output_path"].exists()
        or task["output_path"].with_suffix(task["output_path"].suffix + ".sha256").exists()
    ):
        raise FileExistsError("fresh output path required")
    started = time.monotonic()
    sessions, bindings = _load_sessions(task)
    search = _load(SEARCH_PATH, "ds1_train_full_timing_search")
    # The baseline fixes tau at zero.  Building and scoring the full 41-point
    # timing cube for it was scientifically redundant and dominated runtime.
    requested_values = np.arange(
        -task["options"]["tau_limit_s"],
        task["options"]["tau_limit_s"] + task["options"]["tau_step_s"] * 0.01,
        task["options"]["tau_step_s"],
    )
    values = np.asarray([0.0]) if task["method"] == "baseline" else requested_values
    engine = FullObservationEngine(sessions, search, values)
    winner, trace = _search(engine, task)
    payload = {
        "schema": RESULT_SCHEMA,
        "complete": True,
        "task_id": task["task_id"],
        "partition": task["partition"],
        "group_id": task["group_id"],
        "session_ids": task["session_ids"],
        "session_groups": task["session_groups"],
        "prior": task["prior"],
        "method_requested": task["method_requested"],
        "method": task["method"],
        "observation_policy": "all qualified observations; no randomized TRAIN/held mask",
        "candidate_association": (
            "dynamic full-catalogue reassociation at every geographic/timing evaluation"
        ),
        "cfo_policy": "analytic constant CFO per track from all qualified observations",
        "reference_used_for_fit": False,
        "truth_used_for_fit": False,
        "reference_coordinate_present": False,
        "held_observations_used": False,
        "qualified_track_count": int(sum(len(s.tracks) for s in sessions)),
        "full_observation_count": int(sum(len(t.times_s) for s in sessions for t in s.tracks)),
        "occupied_second_denominator": engine.total_weight,
        "selected": winner,
        "estimated_position": {
            "latitude_deg": winner["latitude_deg"],
            "longitude_deg": winner["longitude_deg"],
            "altitude_m": float(task["options"].get("altitude_m", 0.0)),
        },
        "fitted_parameters": {
            "receiver_position": {
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
            },
            "timing": winner["parameters"],
            "track_associations": winner["assignments"],
        },
        "rf_objective": {
            "selection_value": winner["objective"],
            "full_observation_capped_loss": winner["rf_capped_loss"],
            "frequency_loss_cap_hz": CAP_HZ,
        },
        "observation_use": {
            "policy": "all_qualified_observations",
            "qualified_observation_count": int(
                sum(len(track.times_s) for session in sessions for track in session.tracks)
            ),
            "heldout_observation_count": 0,
        },
        "convergence": {
            "geographic_trace": trace,
            "timing_grid_s": requested_values.tolist(),
            "scored_timing_grid_s": values.tolist(),
            "geographic_levels_km": list(task["options"]["geographic_levels_km"]),
            "beam_width": task["options"]["beam_width"],
        },
        "elapsed_s": time.monotonic() - started,
        "peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "execution": {
            "parallel_unit": "one independently schedulable task process",
            "thread_limits": {
                name: os.environ.get(name)
                for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
            },
        },
        "bindings": {
            "source": _digest(Path(__file__)),
            "search": _digest(SEARCH_PATH),
            "sessions": bindings,
        },
    }
    destination = task["output_path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + f".tmp-{os.getpid()}")
    content = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False, default=_jsonable) + "\n"
    )
    temporary.write_text(content)
    temporary.replace(destination)
    seal = destination.with_suffix(destination.suffix + ".sha256")
    seal.write_text(hashlib.sha256(destination.read_bytes()).hexdigest() + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True, help="minimal scheduler task JSON")
    args = parser.parse_args()
    result = run_task(json.loads(args.task.read_text()))
    print(
        json.dumps(
            {
                "task_id": result["task_id"],
                "method": result["method"],
                "output": "sealed",
                "elapsed_s": result["elapsed_s"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
