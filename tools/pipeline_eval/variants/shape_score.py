"""Score blind receiver controls with a reusable bound on satellite visibility.

The receiver centers each fixed-RF track. The additive RF calibration term is
therefore eliminated before scoring, so both calibration arms share the result.
"""

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from time import perf_counter
from types import FunctionType, SimpleNamespace

import numpy as np

from tools.pipeline_eval.reference import receiver

grid = receiver.grid

BOUNDARY = "blind regional receiver from anonymous tracks and causal TLE to decision"


@dataclass(frozen=True)
class _PreparedTile(grid.Tile):
    @cached_property
    def hermite(self):
        step = grid.FINE_ORBIT_STEP_S
        p0, p1 = self.positions_km[:, :-1], self.positions_km[:, 1:]
        v0, v1 = self.velocities_km_s[:, :-1], self.velocities_km_s[:, 1:]
        movement = p1 - p0 - step * v0
        velocity_change = step * (v1 - v0)
        return 3 * movement - velocity_change, velocity_change - 2 * movement

    @cached_property
    def possible_visibility(self):
        step = grid.FINE_ORBIT_STEP_S
        p0, p1 = self.positions_km[:, :-1], self.positions_km[:, 1:]
        v0, v1 = self.velocities_km_s[:, :-1], self.velocities_km_s[:, 1:]
        up = self.enu_frame[2]
        possible = np.zeros(p0.shape[:2], dtype=bool)
        # The cubic lies in the hull of its Bézier control points. The horizon
        # expression is convex, so a segment with all four below the margin
        # cannot supply a visible sample. Keep segments near the rounding limit.
        max_component = max(
            np.max(np.abs(self.positions_km), initial=0.0),
            step * np.max(np.abs(self.velocities_km_s), initial=0.0),
            np.max(np.abs(self.ecef_center_km)),
        )
        rounding_margin = 128 * np.finfo(float).eps * max_component
        for control in (p0, p0 + (step / 3) * v0, p1 - (step / 3) * v1, p1):
            delta = control - self.ecef_center_km
            height = (delta @ up) + 0.02 * np.linalg.norm(delta, axis=-1)
            possible |= ~(height < -rounding_margin)
        return possible


def _make_tile(context, center):
    return _PreparedTile(**vars(grid.make_tile(context, center)))


def _interpolated_visible_states(tile, times):
    step = grid.FINE_ORBIT_STEP_S
    fractional = (times - tile.knots_s[0]) / step
    knots = fractional.astype(int)
    u = (fractional - knots)[None, :, None]
    sites = np.flatnonzero(tile.possible_visibility[:, knots].all(axis=1))[:, None]
    quadratic, cubic = tile.hermite
    p0 = tile.positions_km[sites, knots]
    v0 = tile.velocities_km_s[sites, knots]
    quadratic, cubic = quadratic[sites, knots], cubic[sites, knots]
    position = p0 + u * (step * v0 + u * (quadratic + u * cubic))
    velocity = v0 + u * (2 * quadratic + 3 * u * cubic) / step
    acceleration = (2 * quadratic + 6 * u * cubic) / step**2
    return position, velocity, acceleration


def _with_dependencies(function, **dependencies):
    # Bind replacements on a private globals dictionary so matched runs can
    # share the frozen modules without changing the reference solver.
    return FunctionType(function.__code__, {**function.__globals__, **dependencies})


_track_arc = _with_dependencies(grid._track_arc, _interpolated_states=_interpolated_visible_states)
_arcs = _with_dependencies(grid._arcs, _track_arc=_track_arc)
_score_at = _with_dependencies(grid.score_at, _arcs=_arcs)
solve = _with_dependencies(
    receiver.solve,
    grid=SimpleNamespace(
        HALF_WIDTH_KM=grid.HALF_WIDTH_KM,
        prepare_sky=grid.prepare_sky,
        make_tile=_make_tile,
        fit_grid=grid.fit_grid,
        score_at=_score_at,
    ),
)


def _answer(result):
    return tuple(
        result[key]
        for key in ("status", "reason", "region_id", "latlon", "best_region", "best_latlon")
    )


def run(case: dict, work_dir: Path) -> dict:
    observation_path = case.get("observation_path")
    catalog_path = case.get("catalog_path")
    if not observation_path or not catalog_path:
        return dict(
            status="unavailable",
            boundary=BOUNDARY,
            metrics={},
            reason="missing_observation_or_catalog",
        )
    try:
        observation = json.loads(Path(observation_path).read_bytes())
        catalog = Path(catalog_path).read_bytes()
    except (OSError, ValueError) as error:
        return dict(
            status="unavailable",
            boundary=BOUNDARY,
            metrics={},
            reason=f"unreadable_observation_or_catalog: {error}",
        )

    arguments = observation, case["regions"], catalog
    # Alternate which method runs first across cases to balance cold caches.
    candidate_first = sum(case["id"].encode()) % 2
    methods = (("control", receiver.solve), ("candidate", solve))
    results, elapsed = {}, {}
    for name, method in methods[::-1] if candidate_first else methods:
        started = perf_counter()
        results[name] = method(*arguments)
        elapsed[f"{name}_s"] = perf_counter() - started
    control_result, candidate_result = results["control"], results["candidate"]
    control = control_result["diagnostics"]
    candidate = candidate_result["diagnostics"]
    paired_evidence = ("regional_scores", "region_result", "held_evidence", "position_evidence")
    metrics = {
        **elapsed,
        **candidate["work"],
        "matched_decision": _answer(control_result) == _answer(candidate_result),
        "matched_work": control["work"] == candidate["work"],
        "matched_evidence": all(control.get(key) == candidate.get(key) for key in paired_evidence),
        "matched_null_maxima": (
            control.get("held_evidence", {}).get("null_maxima")
            == candidate.get("held_evidence", {}).get("null_maxima")
        ),
        "tracks": candidate.get("track_counts", {}).get("received", 0),
        "control_time_shift_s": control["stage_seconds"].get("time_shift_controls", 0.0),
        "candidate_time_shift_s": candidate["stage_seconds"].get("time_shift_controls", 0.0),
        "calibration_invariant": True,
    }
    arm = dict(latlon=candidate_result["latlon"], forced_latlon=candidate_result["best_latlon"])
    pooled = candidate.get("position_evidence", {}).get("pooled")
    if arm["latlon"] is not None and pooled is not None and pooled["rms_hz"] is not None:
        arm["rf_rms_hz"] = pooled["rms_hz"]
    return dict(
        status="ok" if candidate_result["status"] == "fix" else "withheld",
        boundary=BOUNDARY,
        reason=candidate_result["reason"],
        arms=dict(c0=dict(arm), fitted_c=dict(arm)),
        metrics=metrics,
    )
