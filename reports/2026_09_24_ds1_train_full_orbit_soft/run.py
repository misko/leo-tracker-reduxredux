#!/usr/bin/env python3
"""TRAIN-only full-observation DS1 orbit and association task runner.

The command accepts one task JSON and creates one sealed inference JSON.  It
does not accept a reference coordinate, an observation mask, an old location,
or an old association as input.  Candidate identities are re-evaluated from
all observations at each searched point.  The causal-rate arms use exact SGP4
phase nodes for their selected final candidate support and require the exact
winner replay gate to pass before an artifact is marked qualified.

The rate arms deliberately use a staged hard association: all candidates are
scored at every evaluated location using every observation, then the selected
support is fitted jointly for one bounded rate per NORAD.  A full exact
candidate-by-rate soft orbit search is outside this bounded runner; the result
records that limitation instead of claiming a joint global optimum.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SEARCH = ROOT / "reports/2026_09_23_long_training_search/search.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
CAP_HZ = 800.0
RATE_SIGMA_S_H = 0.09176615913014215
RATE_BOUND_S_H = 0.25
EXACT_TOLERANCE_HZ = 0.2
CACHE_ROOTS = {
    "20260921_00": Path("/tmp/leo-long-training-cache-full8h"),
    "20260921_16": Path("/tmp/leo-long-training-cache-second8h"),
}
HARD_METHODS = {"causal_per_norad_orbit_rate", "global_tau_per_norad_orbit_rate"}
SOFT_METHODS = {"soft_joint_association", "soft_association_global_tau"}
METHODS = HARD_METHODS | SOFT_METHODS
METHOD_ALIASES = {
    "global_time_plus_per_norad_orbit_rate": "global_tau_per_norad_orbit_rate",
    "soft_association": "soft_joint_association",
    "soft_association_plus_global_time": "soft_association_global_tau",
}
UNSUPPORTED_METHODS = {
    "soft_association_plus_global_time_orbit_rate",
    "soft_association_plus_global_time_and_orbit_rate",
}
_EXACT_ENGINE: FullObservationEngine | None = None
_EXACT_ORBIT: Any = None


def _fit_exact_finalist(row: dict[str, Any]) -> dict[str, Any]:
    """Fork-safe exact fit for one already RF-selected geographic basin."""
    if _EXACT_ENGINE is None or _EXACT_ORBIT is None:
        raise RuntimeError("exact finalist worker has no inherited engine")
    data = _make_exact_prepared(
        _EXACT_ENGINE, _EXACT_ORBIT, row["latitude_deg"], row["longitude_deg"], row["tau_s"]
    )
    receiver, _up = _EXACT_ENGINE.search.receiver_ecef(row["latitude_deg"], row["longitude_deg"])
    fit = _rate_fit_full(data, receiver, _EXACT_ENGINE.search, _EXACT_ORBIT)
    return {
        **row,
        "objective": fit["full_observation_capped_loss"],
        "fit": fit,
        "associations": data.assignments,
        "screening_objective": row["objective"],
    }


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: Any, *names: str) -> float:
    for name in names:
        if name in value:
            answer = float(value[name])
            if math.isfinite(answer):
                return answer
    raise ValueError(f"missing finite value: one of {names}")


def validate_task(task: dict[str, Any]) -> dict[str, Any]:
    """Normalize the narrow public task contract and reject forbidden inputs."""
    required = {"task_id", "group_id", "session_ids", "prior", "method", "output_path"}
    missing = required - task.keys()
    if missing:
        raise ValueError(f"task missing required fields: {sorted(missing)}")
    forbidden = {"reference", "reference_position", "truth", "training_mask", "held_mask"}
    present = forbidden & task.keys()
    if present:
        raise ValueError(f"task must not supply truth or an observation mask: {sorted(present)}")
    requested_method = str(task["method"])
    if requested_method in UNSUPPORTED_METHODS:
        raise ValueError(
            "soft association + global time + per-NORAD rate is not implemented; "
            "do not schedule it as a surrogate for a joint fit"
        )
    method = METHOD_ALIASES.get(requested_method, requested_method)
    if method not in METHODS:
        raise ValueError(f"unsupported method: {method}")
    ids = tuple(map(str, task["session_ids"]))
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("session_ids must be a nonempty unique list")
    prior = task["prior"]
    if not isinstance(prior, dict):
        raise ValueError("prior must be an object")
    normalized = {
        "task_id": str(task["task_id"]),
        "group_id": str(task["group_id"]),
        "session_ids": ids,
        "prior": {
            "name": str(prior.get("name", "unnamed")),
            "latitude_deg": _number(prior, "latitude_deg", "lat"),
            "longitude_deg": _number(prior, "longitude_deg", "lon"),
            "radius_km": _number(prior, "radius_km", "radius"),
        },
        "method": method,
        "requested_method": requested_method,
        "output_path": Path(task["output_path"]),
        "options": dict(task.get("options", {})),
    }
    if not normalized["task_id"] or normalized["prior"]["radius_km"] <= 0:
        raise ValueError("task id and positive prior radius are required")
    raw_groups = task.get("session_groups")
    if raw_groups is None:
        scans = task.get("input_scans")
        if isinstance(scans, list) and [str(row.get("session_id")) for row in scans] == list(ids):
            groups = {sid: str(row["group_id"]) for sid, row in zip(ids, scans, strict=True)}
        else:
            groups = {sid: normalized["group_id"] for sid in ids}
    elif not isinstance(raw_groups, dict) or set(map(str, raw_groups)) != set(ids):
        raise ValueError("session_groups must map every and only requested session ID")
    else:
        groups = {sid: str(raw_groups[sid]) for sid in ids}
    if any(group not in CACHE_ROOTS for group in groups.values()):
        raise ValueError("session_groups may contain only the two DS1 TRAIN groups")
    normalized["session_groups"] = groups
    return normalized


@dataclass
class Track:
    session_id: str
    track_id: str
    times: np.ndarray
    measured: np.ndarray
    weight: int


@dataclass
class Session:
    session_id: str
    candidate_id: np.ndarray
    grid: np.ndarray
    position: np.ndarray
    velocity: np.ndarray
    tracks: list[Track]
    cache_path: Path
    receipt_digest: str
    cache_digest: str


class FullObservationEngine:
    def __init__(self, task: dict[str, Any]) -> None:
        self.search = load(SEARCH, "ds1_train_full_search")
        self.sessions: list[Session] = []
        for sid in task["session_ids"]:
            group = task["session_groups"][sid]
            roots = task["options"].get("cache_roots", {})
            if roots:
                if group not in roots:
                    raise ValueError(f"cache_roots lacks session group {group}")
                cache_root = Path(roots[group])
            elif "cache_root" in task["options"]:
                if len(set(task["session_groups"].values())) != 1:
                    raise ValueError(
                        "combined TRAIN tasks require options.cache_roots, not cache_root"
                    )
                cache_root = Path(task["options"]["cache_root"])
            else:
                cache_root = CACHE_ROOTS[group]
            root = cache_root / sid
            receipt_path, cache_path = root / "cache_receipt.json", root / "state_cache.npz"
            if not receipt_path.is_file() or not cache_path.is_file():
                raise FileNotFoundError(f"missing causal cache for {sid}")
            receipt = json.loads(receipt_path.read_text())
            if receipt.get("session_id") != sid:
                raise ValueError(f"cache receipt session mismatch: {sid}")
            if not str(receipt.get("candidate_policy", "")).startswith(
                "all causal non-debris STARLINK"
            ):
                raise ValueError(f"cache is not the required causal full-catalogue policy: {sid}")
            if receipt.get("bindings", {}).get("state_cache") != digest(cache_path):
                raise ValueError(f"cache binding mismatch: {sid}")
            with np.load(cache_path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files}
            candidates = np.asarray(arrays["candidate_id"])
            position, velocity = arrays["position_ecef_km"], arrays["velocity_ecef_km_s"]
            if position.shape != velocity.shape or position.shape[0] != len(candidates):
                raise ValueError(f"malformed candidate state cache: {sid}")
            tracks = []
            for item in receipt["prepared_evidence"]["tracks"]:
                times = np.asarray(item["times_s"], dtype=float)
                measured = np.asarray(item["measured_hz"], dtype=float)
                if len(times) != len(measured) or np.ptp(times) < 3.0:
                    continue
                if not np.all(np.isfinite(times)) or not np.all(np.isfinite(measured)):
                    raise ValueError(f"nonfinite observation: {sid}")
                tracks.append(
                    Track(
                        sid,
                        str(item["track_id"]),
                        times,
                        measured,
                        int(len(np.unique(np.floor(times)))),
                    )
                )
            if not tracks:
                raise ValueError(f"no eligible full-observation tracks: {sid}")
            grid = np.asarray(arrays["receive_plus_tau_offset_ns"], dtype=float) / 1e9
            if grid.ndim != 1 or len(grid) < 2 or not np.allclose(np.diff(grid), grid[1] - grid[0]):
                raise ValueError(f"irregular state grid: {sid}")
            self.sessions.append(
                Session(
                    sid,
                    candidates,
                    grid,
                    position,
                    velocity,
                    tracks,
                    root,
                    digest(receipt_path),
                    digest(cache_path),
                )
            )

    @property
    def bindings(self) -> list[dict[str, str]]:
        return [
            {
                "session_id": item.session_id,
                "receipt": item.receipt_digest,
                "cache": item.cache_digest,
            }
            for item in self.sessions
        ]

    def interpolate(
        self, session: Session, times: np.ndarray, offsets: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        query = times[:, None] + offsets[None, :]
        if query.min() < session.grid[0] or query.max() > session.grid[-1]:
            raise ValueError("requested global-time/phase state falls outside causal cache")
        step = session.grid[1] - session.grid[0]
        value = (query - session.grid[0]) / step
        low = np.floor(value).astype(int)
        high = np.minimum(low + 1, len(session.grid) - 1)
        fraction = value - low
        p = session.position[:, low, :] * (1 - fraction)[None, :, :, None]
        p += session.position[:, high, :] * fraction[None, :, :, None]
        v = session.velocity[:, low, :] * (1 - fraction)[None, :, :, None]
        v += session.velocity[:, high, :] * fraction[None, :, :, None]
        return p, v

    def predictions(
        self, session: Session, track: Track, lat: float, lon: float, tau: float
    ) -> tuple[np.ndarray, np.ndarray]:
        receiver, up = self.search.receiver_ecef(lat, lon)
        p, v = self.interpolate(session, track.times, np.asarray([tau]))
        delta = p[:, :, 0, :] - receiver
        distance = np.linalg.norm(delta, axis=-1)
        predicted = (
            -self.search.REFERENCE_RF_HZ
            / self.search.LIGHT_KM_S
            * np.sum(delta * v[:, :, 0, :], axis=-1)
            / distance
        )
        visible = np.max(np.sum(delta * up, axis=-1) / distance, axis=1) >= 0.0
        return predicted, visible

    def hard_association(
        self, lat: float, lon: float, tau: float
    ) -> tuple[float, list[dict[str, Any]]]:
        total, denominator, rows = 0.0, 0, []
        for session in self.sessions:
            for track in session.tracks:
                prediction, visible = self.predictions(session, track, lat, lon, tau)
                residual = track.measured[None, :] - prediction
                cfo = np.mean(residual, axis=1)
                rms = np.sqrt(np.mean((residual - cfo[:, None]) ** 2, axis=1))
                rms = np.where(visible, rms, np.inf)
                winner = int(np.argmin(rms))
                valid = bool(np.isfinite(rms[winner]))
                loss = 1.0 if not valid else min((float(rms[winner]) / CAP_HZ) ** 2, 1.0)
                total += track.weight * loss
                denominator += track.weight
                rows.append(
                    {
                        "session_id": session.session_id,
                        "track_id": track.track_id,
                        "candidate_id": str(session.candidate_id[winner]) if valid else None,
                        "cfo_hz": float(cfo[winner]) if valid else None,
                        "full_observation_rms_hz": float(rms[winner]) if valid else None,
                        "weight_s": track.weight,
                    }
                )
        return total / denominator, rows

    def soft_association(
        self, lat: float, lon: float, tau: float
    ) -> tuple[float, list[dict[str, Any]]]:
        """Full-observation mixture likelihood with analytic candidate-specific CFO."""
        signal_sigma, null_sigma, signal_prior = 250.0, 30_000.0, 0.5
        total, count, rows = 0.0, 0, []
        for session in self.sessions:
            catalogue = len(session.candidate_id)
            for track in session.tracks:
                prediction, visible = self.predictions(session, track, lat, lon, tau)
                residual = track.measured[None, :] - prediction
                offsets = np.mean(residual, axis=1)
                centered = residual - offsets[:, None]
                z = centered / signal_sigma
                log_likelihood = -np.sum(np.sqrt(1.0 + z * z) - 1.0, axis=1) - len(
                    track.times
                ) * math.log(signal_sigma)
                log_likelihood = np.where(visible, log_likelihood, -np.inf)
                null_centered = track.measured - np.mean(track.measured)
                null_log = -float(
                    np.sum(np.sqrt(1.0 + (null_centered / null_sigma) ** 2) - 1.0)
                ) - len(track.times) * math.log(null_sigma)
                components = np.append(
                    log_likelihood + math.log(signal_prior / catalogue),
                    null_log + math.log1p(-signal_prior),
                )
                maximum = float(np.max(components))
                log_evidence = maximum + math.log(float(np.sum(np.exp(components - maximum))))
                posterior = np.exp(components - log_evidence)
                leader = int(np.argmax(posterior[:-1]))
                ordered = np.argsort(posterior[:-1])[::-1]
                runner_up = int(ordered[1]) if len(ordered) > 1 else leader
                total -= track.weight * log_evidence / len(track.times)
                count += track.weight
                rows.append(
                    {
                        "session_id": session.session_id,
                        "track_id": track.track_id,
                        "candidate_id": str(session.candidate_id[leader]),
                        "candidate_posterior": float(posterior[leader]),
                        "runner_up_candidate_id": str(session.candidate_id[runner_up]),
                        "runner_up_posterior": float(posterior[runner_up]),
                        "unassigned_posterior": float(posterior[-1]),
                        "cfo_hz": float(offsets[leader]),
                        "full_observation_rms_hz": float(np.sqrt(np.mean(centered[leader] ** 2))),
                        "weight_s": track.weight,
                    }
                )
        return total / count, rows


def _rate_fit_full(data: Any, receiver: np.ndarray, search: Any, orbit: Any) -> dict[str, Any]:
    """Fit all-observation CFOs and bounded causal rates on a staged hard support."""
    labels, source = np.unique(data.source, return_inverse=True)
    tracks, track = np.unique(data.track, return_inverse=True)
    weights = data.weights

    def evaluate(rates: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        phase = data.age_h * rates[source]
        predicted = orbit.doppler(
            receiver, orbit.quartic(data.p_nodes, phase), orbit.quartic(data.v_nodes, phase), search
        )
        residual = data.y - predicted
        cfo = np.asarray([np.mean(residual[track == n]) for n in range(len(tracks))])
        error = residual - cfo[track]
        loss = sum(
            weights[str(name)]
            * min((float(np.sqrt(np.mean(error[track == n] ** 2))) / CAP_HZ) ** 2, 1.0)
            for n, name in enumerate(tracks)
        ) / sum(weights.values())
        return float(loss), cfo, error, phase

    def objective(rates: np.ndarray) -> float:
        _loss, _cfo, error, _phase = evaluate(rates)
        z = error / 250.0
        return float(
            np.sum(np.sqrt(1.0 + z * z) - 1.0) + 0.5 * np.sum((rates / RATE_SIGMA_S_H) ** 2)
        )

    fitted = minimize(
        objective,
        np.zeros(len(labels)),
        method="L-BFGS-B",
        bounds=[(-RATE_BOUND_S_H, RATE_BOUND_S_H)] * len(labels),
        options={"maxiter": 120, "ftol": 1e-11, "gtol": 1e-7},
    )
    null_loss, _, _, _ = evaluate(np.zeros(len(labels)))
    fitted_loss, cfo, _error, phase = evaluate(np.asarray(fitted.x, dtype=float))
    rates = np.asarray(fitted.x, dtype=float)
    rejected = fitted_loss > null_loss + 1e-12
    if rejected:
        rates = np.zeros(len(labels))
        fitted_loss, cfo, _error, phase = evaluate(rates)
    return {
        "full_observation_capped_loss": float(fitted_loss),
        "full_observation_capped_rms_hz": float(CAP_HZ * math.sqrt(fitted_loss)),
        "null_rate_full_observation_capped_loss": float(null_loss),
        "rate_fit_rejected_by_full_observation_loss": bool(rejected),
        "converged": bool(fitted.success),
        "iterations": int(fitted.nit),
        "message": str(fitted.message),
        "rate_corrections_s_h": {
            str(name): float(rate) for name, rate in zip(labels, rates, strict=True)
        },
        "rate_boundary_count": int(np.sum(np.abs(rates) >= RATE_BOUND_S_H - 1e-8)),
        "maximum_phase_s": float(np.max(np.abs(phase))),
        "track_cfo_hz": {str(name): float(value) for name, value in zip(tracks, cfo, strict=True)},
    }


def _make_exact_prepared(
    engine: FullObservationEngine,
    orbit: Any,
    lat: float,
    lon: float,
    tau: float,
    selected_associations: list[dict[str, Any]] | None = None,
) -> Any:
    """Adapt the reviewed exact-node builder after replacing every old mask with all True."""

    class Adapter:
        sessions: list[dict[str, Any]]

        def profile(
            self,
            latitude: float,
            longitude: float,
            taus: np.ndarray,
            _held: bool,
            assignments: bool,
        ):
            rows = []
            for value in taus:
                if selected_associations is None:
                    _loss, chosen = engine.hard_association(latitude, longitude, float(value))
                else:
                    chosen = selected_associations
                rows.append(chosen)
            losses = [
                engine.hard_association(latitude, longitude, float(value))[0] for value in taus
            ]
            return np.asarray(losses), np.zeros(len(taus)), rows

    adapter = Adapter()
    adapter.sessions = []
    for session in engine.sessions:
        adapter.sessions.append(
            {
                "session_id": session.session_id,
                "cache_path": str(session.cache_path),
                "tracks": [
                    {
                        "track_id": t.track_id,
                        "times": t.times,
                        "measured": t.measured,
                        "train": np.ones(len(t.times), dtype=bool),
                        "weight": t.weight,
                    }
                    for t in session.tracks
                ],
            }
        )
    return orbit.prepare(adapter, lat, lon, tau)


def _taus(task: dict[str, Any]) -> tuple[float, ...]:
    if task["method"] in {"global_tau_per_norad_orbit_rate", "soft_association_global_tau"}:
        values = task["options"].get("tau_grid_s", [-5, -3, -1, 0, 1, 3, 5])
        answer = tuple(sorted({float(value) for value in values}))
        if not answer or answer[0] < -5.0 or answer[-1] > 5.0:
            raise ValueError("global tau grid must be nonempty and lie in the cache's +/-5 s range")
        return answer
    return (0.0,)


def _search(
    task: dict[str, Any], engine: FullObservationEngine
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prior, options = task["prior"], task["options"]
    levels = tuple(float(v) for v in options.get("search_levels_km", (100.0, 25.0, 6.25, 1.5625)))
    if (
        not levels
        or any(v <= 0 for v in levels)
        or any(a <= b for a, b in zip(levels, levels[1:], strict=False))
    ):
        raise ValueError("search_levels_km must be strictly decreasing positive values")
    beam_width = int(options.get("beam_width", 3))
    if not 1 <= beam_width <= 16:
        raise ValueError("beam_width must be 1..16")
    orbit = None
    tau_values = _taus(task)
    cache: dict[tuple[float, float, float], dict[str, Any]] = {}
    trace: list[dict[str, Any]] = []

    def score(east: float, north: float, tau: float, level: float) -> dict[str, Any]:
        key = (round(east, 8), round(north, 8), round(tau, 8))
        if key in cache:
            return cache[key]
        latitude, longitude = engine.search.offset_coordinate(
            (prior["latitude_deg"], prior["longitude_deg"]), east, north
        )
        if (
            engine.search.haversine_km(
                (prior["latitude_deg"], prior["longitude_deg"]), (latitude, longitude)
            )
            > prior["radius_km"] + 1e-9
        ):
            raise ValueError("trial left the declared prior")
        if task["method"] in HARD_METHODS:
            # Reacquire hard identities from all observations at every point,
            # then reserve direct SGP4 rate fitting for final basins only.
            objective, associations = engine.hard_association(latitude, longitude, tau)
            item = {
                "associations": associations,
                "screening_model": "cached nominal full-observation hard association",
            }
        else:
            objective, associations = engine.soft_association(latitude, longitude, tau)
            item = {"soft_associations": associations}
        row = {
            "east_km": east,
            "north_km": north,
            "latitude_deg": latitude,
            "longitude_deg": longitude,
            "tau_s": tau,
            "objective": float(objective),
            "level_km": level,
            **item,
        }
        cache[key] = row
        trace.append(
            {
                key: value
                for key, value in row.items()
                if key not in {"prepared", "fit", "associations", "soft_associations"}
            }
        )
        return row

    def diverse(rows: list[dict[str, Any]], spacing: float) -> list[dict[str, Any]]:
        retained = []
        for row in sorted(
            rows,
            key=lambda x: (
                x["objective"],
                abs(x["tau_s"]),
                x["tau_s"],
                x["east_km"],
                x["north_km"],
            ),
        ):
            if all(
                np.hypot(row["east_km"] - old["east_km"], row["north_km"] - old["north_km"])
                >= spacing
                for old in retained
            ):
                retained.append(row)
            if len(retained) == beam_width:
                break
        return retained

    radius, first = prior["radius_km"], levels[0]
    # Always retain the declared prior centre, including small smoke priors
    # whose radius is narrower than the first coarse spacing.
    axis = np.unique(np.append(np.arange(-radius, radius + first * 0.01, first), 0.0))
    current = [
        score(float(e), float(n), tau, first)
        for e in axis
        for n in axis
        for tau in tau_values
        if np.hypot(e, n) <= radius + 1e-9
    ]
    beam = diverse(current, first)
    for level in levels[1:]:
        expanded = list(beam)
        for parent in beam:
            for east_delta in (-level, 0.0, level):
                for north_delta in (-level, 0.0, level):
                    east, north = parent["east_km"] + east_delta, parent["north_km"] + north_delta
                    if np.hypot(east, north) <= radius + 1e-9:
                        for tau in tau_values:
                            expanded.append(score(east, north, tau, level))
        beam = diverse(expanded, level)
    winner = min(
        cache.values(),
        key=lambda x: (x["objective"], abs(x["tau_s"]), x["tau_s"], x["east_km"], x["north_km"]),
    )
    if task["method"] in HARD_METHODS:
        orbit = load(ORBIT, "ds1_train_full_orbit_exact")
        final_count = int(options.get("exact_rate_finalists", beam_width))
        if not 1 <= final_count <= 16:
            raise ValueError("exact_rate_finalists must be 1..16")
        finalist_pool = sorted(
            cache.values(),
            key=lambda x: (
                x["objective"],
                abs(x["tau_s"]),
                x["tau_s"],
                x["east_km"],
                x["north_km"],
            ),
        )
        finalists = []
        for row in finalist_pool:
            if all(
                np.hypot(row["east_km"] - old["east_km"], row["north_km"] - old["north_km"])
                >= levels[-1]
                for old in finalists
            ):
                finalists.append(row)
            if len(finalists) == final_count:
                break
        exact_workers = int(options.get("exact_rate_workers", 1))
        if not 1 <= exact_workers <= 32:
            raise ValueError("exact_rate_workers must be 1..32")
        global _EXACT_ENGINE, _EXACT_ORBIT
        _EXACT_ENGINE, _EXACT_ORBIT = engine, orbit
        if exact_workers == 1 or len(finalists) == 1:
            exact_rows = [_fit_exact_finalist(row) for row in finalists]
        else:
            # Each finalist is independent after the RF-only basin selection.
            # Fork retains the immutable state cache without reloading it per
            # worker.  The caller should set BLAS thread counts to one.
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=min(exact_workers, len(finalists)),
                mp_context=multiprocessing.get_context("fork"),
            ) as pool:
                exact_rows = list(pool.map(_fit_exact_finalist, finalists, chunksize=1))
        for exact in exact_rows:
            trace.append(
                {
                    "stage": "exact_rate_finalist",
                    "latitude_deg": exact["latitude_deg"],
                    "longitude_deg": exact["longitude_deg"],
                    "tau_s": exact["tau_s"],
                    "screening_objective": exact["screening_objective"],
                    "objective": exact["objective"],
                }
            )
        winner = min(
            exact_rows,
            key=lambda x: (
                x["objective"],
                abs(x["tau_s"]),
                x["tau_s"],
                x["east_km"],
                x["north_km"],
            ),
        )
        winner["prepared"] = _make_exact_prepared(
            engine, orbit, winner["latitude_deg"], winner["longitude_deg"], winner["tau_s"]
        )
        winner["exact_rate_finalist_count"] = len(exact_rows)
        winner["exact_rate_workers"] = exact_workers
    return winner, trace


def _exact_winner_gate(
    task: dict[str, Any], engine: FullObservationEngine, winner: dict[str, Any]
) -> dict[str, Any]:
    orbit = load(ORBIT, "ds1_train_full_exact_gate")
    prepared = winner.get("prepared")
    if prepared is None:
        # Soft association selects one reported leader per track for the audit.
        prepared = _make_exact_prepared(
            engine,
            orbit,
            winner["latitude_deg"],
            winner["longitude_deg"],
            winner["tau_s"],
            winner["soft_associations"],
        )
    receiver, _up = engine.search.receiver_ecef(winner["latitude_deg"], winner["longitude_deg"])
    rates = winner.get("fit", {}).get("rate_corrections_s_h", {})
    if not rates:
        rates = {str(value): 0.0 for value in np.unique(prepared.source)}
    gate = orbit.exact_replay_gate(
        prepared, receiver, engine.search, winner["tau_s"], rates, EXACT_TOLERANCE_HZ
    )
    if not gate["passed"]:
        raise RuntimeError("exact SGP4 winner gate failed")
    return gate


def _atomic_write(path: Path, document: dict[str, Any]) -> tuple[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.with_suffix(".sha256").exists():
        raise FileExistsError(f"refusing to overwrite output: {path}")
    encoded = (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)
    checksum = hashlib.sha256(encoded).hexdigest()
    seal = path.with_suffix(".sha256")
    temporary_seal = seal.with_name(f".{seal.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary_seal.write_text(checksum + "\n")
    os.replace(temporary_seal, seal)
    return str(path), "sha256:" + checksum


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    """Run one independent full-observation task and atomically seal its result."""
    normalized = validate_task(task)
    started = time.monotonic()
    engine = FullObservationEngine(normalized)
    winner, trace = _search(normalized, engine)
    exact_gate = _exact_winner_gate(normalized, engine, winner)
    associations = winner.get("associations", winner.get("soft_associations"))
    fitted = winner.get("fit", {"rate_corrections_s_h": {}, "track_cfo_hz": {}})
    if normalized["method"] in SOFT_METHODS:
        fitted = {
            **fitted,
            "track_cfo_hz": {
                f"{row['session_id']}:{row['track_id']}": row["cfo_hz"] for row in associations
            },
            "rate_corrections_s_h": {},
        }
    document = {
        "schema": "ds1-train-full-inference-result/v1",
        "complete": True,
        "qualified": True,
        "task_id": normalized["task_id"],
        "partition": "train",
        "reference_used_for_fit": False,
        "group_id": normalized["group_id"],
        "session_ids": list(normalized["session_ids"]),
        "session_groups": normalized["session_groups"],
        "prior": normalized["prior"],
        "method": normalized["method"],
        "requested_method": normalized["requested_method"],
        "estimated_position": {
            "latitude_deg": winner["latitude_deg"],
            "longitude_deg": winner["longitude_deg"],
        },
        "global_tau_s": winner["tau_s"],
        "rf_objective": {
            "name": "full_observation_rf_objective",
            "value": winner["objective"],
            "selection_uses_reference": False,
        },
        "rf_objective_value": winner["objective"],
        "fitted": fitted,
        "fitted_parameters": {
            "global_tau_s": winner["tau_s"],
            **fitted,
        },
        "track_associations": associations,
        "search_trace": trace,
        "exact_sgp4_winner_gate": exact_gate,
        "observations": {
            "all_qualified_observations_used": True,
            "held_mask_used": False,
            "reference_coordinate_used": False,
            "track_count": sum(len(s.tracks) for s in engine.sessions),
            "observation_count": sum(len(t.times) for s in engine.sessions for t in s.tracks),
        },
        "observation_use": {
            "policy": "all_qualified_observations",
            "heldout_observation_count": 0,
        },
        "causal_tle": {
            "only_receipt_bound_causal_archives": True,
            "rate_prior_sigma_s_h": RATE_SIGMA_S_H,
            "rate_bound_s_h": RATE_BOUND_S_H,
        },
        "association_model": (
            "full-observation hard candidate reacquisition at every point; "
            "exact-rate staged after association"
            if normalized["method"] in HARD_METHODS
            else "full-observation candidate mixture with analytic candidate-specific CFO"
        ),
        "execution_stages": (
            {
                "screening": "cached nominal full-observation hard reassociation "
                "at every geographic/time trial",
                "exact_refinement": "bounded exact SGP4 causal-rate fit only "
                "for deterministic RF-selected basins",
                "exact_finalist_count": winner.get("exact_rate_finalist_count"),
                "exact_rate_workers": winner.get("exact_rate_workers"),
            }
            if normalized["method"] in HARD_METHODS
            else {
                "screening": "full-observation soft candidate mixture "
                "at every geographic/time trial"
            }
        ),
        "limitations": (
            [
                "Causal-rate associations are reacquired at every geographic/time trial, "
                "then rates are fitted on that hard support; this is not a full exact "
                "soft identity-and-rate marginalization."
            ]
            if normalized["method"] in HARD_METHODS
            else [
                "Soft global-time is implemented; soft per-NORAD rate marginalization "
                "remains a separate, more expensive arm."
            ]
        ),
        "elapsed_s": time.monotonic() - started,
        "bindings": {
            "source": digest(Path(__file__)),
            "search": digest(SEARCH),
            "exact_orbit_gate": digest(ORBIT),
            "session_caches": engine.bindings,
        },
    }
    output_path, output_digest = _atomic_write(normalized["output_path"], document)
    return {
        "task_id": normalized["task_id"],
        "output_path": output_path,
        "output_sha256": output_digest,
        "qualified": True,
        "elapsed_s": document["elapsed_s"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True, help="manifest task JSON")
    args = parser.parse_args()
    task = json.loads(args.task.read_text())
    print(json.dumps(run_task(task), sort_keys=True))


if __name__ == "__main__":
    main()
