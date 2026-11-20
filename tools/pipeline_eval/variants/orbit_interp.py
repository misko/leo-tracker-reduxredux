"""Reuse causal SGP4 states and Hermite coefficients in the frozen regional receiver.

The boundary starts with in-memory anonymous tracks and TLE text. This shape
receiver subtracts the level of every fixed-RF track, so an RF-dependent
constant cancels and one computed result serves both calibration arms.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import FunctionType, SimpleNamespace

import numpy as np

from tools.pipeline_eval.reference import grid as _GRID
from tools.pipeline_eval.reference import receiver as _RECEIVER

_STEP_S = _GRID.FINE_ORBIT_STEP_S
_BOUNDARY = "anonymous tracks and causal TLE text to regional receiver decision"


class _FineOrbitCache:
    def __init__(self):
        self.states = {}
        self.evaluations = 0

    def propagate(self, satellites, anchor, knots):
        rows = self.states.setdefault((anchor, knots.tobytes()), {})
        pending = tuple(sat for sat in satellites if sat not in rows)
        if pending:
            valid, position, velocity = _GRID._valid_states(pending, anchor, knots)
            self.evaluations += len(pending) * len(knots)
            rows.update(dict.fromkeys(pending))
            rows.update((sat, (p, v)) for sat, p, v in zip(valid, position, velocity, strict=True))
            if len(pending) == len(satellites):
                return valid, position, velocity
        states = [(sat, row) for sat in satellites if (row := rows[sat]) is not None]
        if not states:
            return _GRID._valid_states((), anchor, knots)
        valid, vectors = zip(*states, strict=True)
        position, velocity = zip(*vectors, strict=True)
        return valid, np.stack(position), np.stack(velocity)


@dataclass(frozen=True)
class _HermiteTile(_GRID.Tile):
    quadratic: np.ndarray
    cubic: np.ndarray

    @classmethod
    def from_tile(cls, tile):
        position = np.ascontiguousarray(tile.positions_km.swapaxes(0, 1))
        velocity = np.ascontiguousarray(tile.velocities_km_s.swapaxes(0, 1))
        movement = position[1:] - position[:-1] - _STEP_S * velocity[:-1]
        velocity_change = _STEP_S * (velocity[1:] - velocity[:-1])
        return cls(
            tile.ecef_center_km,
            tile.enu_frame,
            tile.duration_s,
            tile.knots_s,
            position.swapaxes(0, 1),
            velocity.swapaxes(0, 1),
            tile.stats,
            3 * movement - velocity_change,
            velocity_change - 2 * movement,
        )


def _interpolate(tile, times):
    fractional = (times - tile.knots_s[0]) / _STEP_S
    indices = fractional.astype(int)
    u = (fractional - indices)[:, None, None]
    p0 = tile.positions_km.swapaxes(0, 1)[indices]
    v0 = tile.velocities_km_s.swapaxes(0, 1)[indices]
    quadratic = tile.quadratic[indices]
    cubic = tile.cubic[indices]
    position = p0 + u * (_STEP_S * v0 + u * (quadratic + u * cubic))
    velocity = v0 + u * (2 * quadratic + 3 * u * cubic) / _STEP_S
    acceleration = (2 * quadratic + 6 * u * cubic) / _STEP_S**2
    return position.swapaxes(0, 1), velocity.swapaxes(0, 1), acceleration.swapaxes(0, 1)


def _bind(function, **bindings):
    return FunctionType(
        function.__code__,
        function.__globals__ | bindings,
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )


_TRACK_ARC = _bind(_GRID._track_arc, _interpolated_states=_interpolate)
_ARCS = _bind(_GRID._arcs, _track_arc=_TRACK_ARC)
_FIT = _bind(_GRID.fit_grid, _arcs=_ARCS)
_SCORE = _bind(_GRID.score_at, _arcs=_ARCS)


@dataclass
class _Trial:
    result: dict
    tiles: list
    seconds: float
    sgp4_evaluations: int


def _trial(observation, regions, catalog, *, cached):
    started = perf_counter()
    orbit = _FineOrbitCache() if cached else None
    make_tile = _bind(_GRID.make_tile, _valid_states=orbit.propagate) if orbit else _GRID.make_tile
    tiles = []

    def capture_tile(context, center):
        tile = make_tile(context, center)
        if cached:
            tile = _HermiteTile.from_tile(tile)
        tiles.append(tile)
        return tile

    grid = SimpleNamespace(
        prepare_sky=_GRID.prepare_sky,
        make_tile=capture_tile,
        fit_grid=_FIT if cached else _GRID.fit_grid,
        score_at=_SCORE if cached else _GRID.score_at,
    )
    solve = _bind(_RECEIVER.solve, grid=grid)
    result = solve(observation, regions, catalog)
    seconds = perf_counter() - started
    coarse = result["diagnostics"].get("sky", {}).get("coarse_state_evaluations", 0)
    fine = orbit.evaluations if orbit else sum(t.stats["fine_state_evaluations"] for t in tiles)
    return _Trial(result, tiles, seconds, coarse + fine)


def _projection_peaks(reference, interpolated, origin):
    errors = [
        np.max(np.linalg.norm(left - right, axis=-1))
        for left, right in zip(reference, interpolated, strict=True)
    ]
    doppler = []
    for position, velocity, _ in (reference, interpolated):
        delta = position - origin
        rate = np.einsum("...i,...i->...", delta, velocity) / np.linalg.norm(delta, axis=-1)
        doppler.append(-12e9 * rate / _GRID.LIGHT_SPEED_KM_S)
    return [*errors, np.max(np.abs(doppler[0] - doppler[1]))]


def _projection_error(control, candidate):
    peaks = np.zeros(4)
    rows = 0
    aligned = len(control.tiles) == len(candidate.tiles)
    for original, prepared in zip(control.tiles, candidate.tiles, strict=False):
        if original.positions_km.shape != prepared.positions_km.shape:
            aligned = False
            continue
        if not original.positions_km.size:
            continue
        times = (original.knots_s[:-1, None] + _STEP_S * np.array([0.0, 0.25, 0.75])).ravel()
        for start in range(0, len(times), 32):
            batch = times[start : start + 32]
            reference = _GRID._interpolated_states(original, batch)
            interpolated = _interpolate(prepared, batch)
            peaks = np.maximum(
                peaks, _projection_peaks(reference, interpolated, original.ecef_center_km)
            )
        rows += original.positions_km.shape[0] * len(times)
    return dict(
        projection_rows=rows,
        projection_tables_aligned=aligned,
        position_max_error_km=float(peaks[0]),
        velocity_max_error_km_s=float(peaks[1]),
        acceleration_max_error_km_s2=float(peaks[2]),
        tile_center_12ghz_doppler_max_error_hz=float(peaks[3]),
    )


def _metrics(control, candidate):
    expected, actual = control.result, candidate.result
    expected_d, actual_d = expected["diagnostics"], actual["diagnostics"]
    return dict(
        control_s=control.seconds,
        candidate_s=candidate.seconds,
        control_sgp4_evaluations=control.sgp4_evaluations,
        candidate_sgp4_evaluations=candidate.sgp4_evaluations,
        control_tiles_s=expected_d["stage_seconds"].get("tiles", 0.0),
        candidate_tiles_s=actual_d["stage_seconds"].get("tiles", 0.0),
        control_time_shift_s=expected_d["stage_seconds"].get("time_shift_controls", 0.0),
        candidate_time_shift_s=actual_d["stage_seconds"].get("time_shift_controls", 0.0),
        grid_fits=actual_d["work"]["grid_fits"],
        point_scores=actual_d["work"]["point_scores"],
        null_schedules=actual_d["work"]["null_schedules"],
        same_work=expected_d["work"] == actual_d["work"],
        same_decision=all(
            expected[key] == actual[key] for key in ("status", "reason", "region_id", "latlon")
        ),
        same_forced_position=all(
            expected[key] == actual[key] for key in ("best_region", "best_latlon")
        ),
        same_shape_evidence=all(
            expected_d.get(key) == actual_d.get(key)
            for key in ("regional_scores", "held_evidence", "position_evidence")
        ),
        control_reason=expected["reason"],
        control_latlon=expected["latlon"] or [],
        control_forced_latlon=expected["best_latlon"] or [],
        **_projection_error(control, candidate),
    )


def run(case: dict, work_dir: Path) -> dict:
    observation_path, catalog_path = case.get("observation_path"), case.get("catalog_path")
    if not observation_path or not catalog_path:
        return dict(
            status="unavailable",
            boundary=_BOUNDARY,
            metrics={},
            reason="missing portable observation or causal catalog",
        )
    try:
        observation = json.loads(Path(observation_path).read_bytes())
        catalog = Path(catalog_path).read_bytes()
    except (OSError, ValueError) as error:
        return dict(status="unavailable", boundary=_BOUNDARY, metrics={}, reason=str(error))
    candidate_first = bool(hashlib.sha256(case["id"].encode()).digest()[0] % 2)
    first, second = [
        _trial(observation, case["regions"], catalog, cached=cached)
        for cached in (candidate_first, not candidate_first)
    ]
    control, candidate = (second, first) if candidate_first else (first, second)
    result = candidate.result
    metrics = _metrics(control, candidate)
    metrics["candidate_first"] = candidate_first
    for name, trial in (("control", control), ("candidate", candidate)):
        pooled = trial.result["diagnostics"].get("position_evidence", {}).get("pooled")
        if pooled and pooled["rms_hz"] is not None:
            metrics[f"{name}_pooled_shape_rms_hz"] = pooled["rms_hz"]
    arm = dict(latlon=result["latlon"], forced_latlon=result["best_latlon"])
    return dict(
        status="ok" if result["status"] == "fix" else "withheld",
        boundary=_BOUNDARY,
        reason=result["reason"],
        metrics=metrics,
        arms=dict(c0=arm, fitted_c=arm.copy()),
    )
