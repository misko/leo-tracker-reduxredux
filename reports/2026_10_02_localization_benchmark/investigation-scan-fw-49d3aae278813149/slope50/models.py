"""Bounded per-scan localization model comparison.

The runner consumes only the duck-typed numerical ``Data`` contract used by
the coherent-localization prototype.  It never opens report JSON, a catalogue,
QNAP storage, or reference truth.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from fast_geometry import ZeroShiftGeometry, usable
from fast_tracks import fit_track_independent, fit_track_shared

for _thread_variable in (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_thread_variable, "1")

ROOT = Path(__file__).resolve().parent
COHERENT_ROOT = ROOT.parent / "2026_10_02_coherent_localization"
ALIAS_HZ = 1.0 / 4.4e-6
SCALE_HZ = 200.0
CAP_HZ = 2000.0
UNMATCHED_COST = 2 * SCALE_HZ**2 * (np.sqrt(1 + (CAP_HZ / SCALE_HZ) ** 2) - 1)
TOTAL_BUDGET_S = 480.0
POSITION_BOUND_KM = 200.0
GRID_STEP_KM = 50.0
SATELLITE_COUNT = 64
PARAMETER_COUNT = 70


def _load_selection_names():
    path = ROOT / "selection.py"
    spec = importlib.util.spec_from_file_location("_localization_benchmark_selection", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.MODEL_NAMES)


MODEL_NAMES = _load_selection_names()
MODEL_BUDGET_S = {
    "track_independent": 55.0,
    "track_constant": 55.0,
    "track_linear": 55.0,
    "glrt_fixed_8": 25.0,
    "glrt_fixed_16": 25.0,
    "glrt_fixed_32": 25.0,
    "glrt_fixed_64": 25.0,
    "glrt_free_16": 55.0,
    "glrt_timing_3s": 80.0,
    "glrt_timing_10s": 80.0,
    "anchors": 18.0,
    "extensions": 30.0,
    "coherent_timing": 20.0,
}


class _LimitReached(RuntimeError):
    pass


class _NoAnchors(RuntimeError):
    pass


def circular(measured, prediction=0.0):
    return (measured - prediction + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def rho(errors):
    clipped = np.minimum(np.abs(np.asarray(errors, dtype=float)), CAP_HZ)
    return 2 * SCALE_HZ**2 * (np.sqrt(1 + (clipped / SCALE_HZ) ** 2) - 1)


def _raw_rho(errors):
    scaled = np.asarray(errors, dtype=float) / SCALE_HZ
    return 2 * SCALE_HZ**2 * (np.sqrt(1 + scaled * scaled) - 1)


def _finite_float(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise _LimitReached("model wall-clock budget reached")


@contextmanager
def _single_numerical_thread():
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:
        yield
    else:
        with threadpool_limits(limits=1):
            yield


def _validate_data(data):
    arrays = {}
    for name in ("times", "measured", "rf", "receiver", "channel", "group", "margin"):
        value = np.asarray(getattr(data, name))
        if value.ndim != 1:
            raise ValueError(f"data.{name} must be one-dimensional")
        arrays[name] = value
    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        raise ValueError("data observation arrays must have one equal nonzero length")
    if not np.all(np.isfinite(arrays["times"])):
        raise ValueError("data.times must be finite")
    if not np.all(np.isfinite(arrays["measured"])):
        raise ValueError("data.measured must be finite")
    if not np.all(np.isfinite(arrays["rf"])):
        raise ValueError("data.rf must be finite")
    if np.any(~np.isin(arrays["receiver"], (0, 1))):
        raise ValueError("data.receiver values must be 0 or 1")
    numbers = np.asarray(data.numbers)
    if numbers.shape != (SATELLITE_COUNT,) or len(np.unique(numbers)) != SATELLITE_COUNT:
        raise ValueError("data.numbers must contain exactly 64 unique candidates")
    initial = np.asarray(data.initial, dtype=float)
    if initial.shape != (PARAMETER_COUNT,) or not np.all(np.isfinite(initial)):
        raise ValueError("data.initial must be a finite length-70 vector")
    tracks = list(data.tracks)
    full_pool = np.arange(SATELLITE_COUNT)
    for track_index, track in enumerate(tracks):
        rows = np.asarray(track["rows"])
        candidates = np.asarray(track["candidate_indices"])
        if rows.ndim != 1 or not np.issubdtype(rows.dtype, np.integer):
            raise ValueError(f"track {track_index} rows must be a one-dimensional integer array")
        if not len(rows) or np.any((rows < 0) | (rows >= len(arrays["times"]))):
            raise ValueError(f"track {track_index} has empty or out-of-range rows")
        if candidates.ndim != 1 or not np.issubdtype(candidates.dtype, np.integer):
            raise ValueError(
                f"track {track_index} candidate_indices must be a one-dimensional integer array"
            )
        if not np.array_equal(np.sort(np.unique(candidates)), full_pool):
            raise ValueError(f"track {track_index} does not expose the common 64-candidate pool")
        if len(np.unique(arrays["receiver"][rows])) != 1:
            raise ValueError(f"track {track_index} spans receivers")
    template = initial.copy()
    template[2:] = 0.0
    prediction, visible = data.predict(template)
    if np.asarray(prediction).shape != (len(arrays["times"]), SATELLITE_COUNT):
        raise ValueError("full data.predict must return observations by 64 candidates")
    if np.asarray(visible).shape != np.asarray(prediction).shape:
        raise ValueError("full data.predict visibility must match prediction")
    if tracks:
        rows = np.asarray(tracks[0]["rows"], dtype=int)[:1]
        satellites = np.zeros(len(rows), dtype=int)
        paired_prediction, paired_visible = data.predict(template, rows=rows, satellites=satellites)
        if np.asarray(paired_prediction).shape != rows.shape:
            raise ValueError("paired data.predict must preserve paired row shape")
        if np.asarray(paired_visible).shape != rows.shape:
            raise ValueError("paired data.predict visibility must preserve paired row shape")
    return arrays, numbers, initial, tracks


class _PredictionCache:
    def __init__(self, data, initial, observation_count, maximum_bytes=512 * 1024**2):
        self.data = data
        self.template = initial.copy()
        self.template[2:] = 0.0
        self.observation_count = observation_count
        self.maximum_bytes = maximum_bytes
        self.bytes = 0
        self.values = OrderedDict()
        self.geometry = ZeroShiftGeometry(data) if usable(data) else None

    @staticmethod
    def _key(point):
        return tuple(np.round(np.asarray(point, dtype=float), 10))

    def get(self, point):
        key = self._key(point)
        if key in self.values:
            prediction, visible = self.values.pop(key)
            self.values[key] = (prediction, visible)
            return prediction, visible
        parameters = self.template.copy()
        parameters[:2] = key
        prediction, visible = (
            self.geometry.predict(key)
            if self.geometry is not None
            else self.data.predict(parameters)
        )
        prediction = np.asarray(prediction, dtype=float)
        visible = np.asarray(visible, dtype=bool)
        expected = (self.observation_count, SATELLITE_COUNT)
        if prediction.shape != expected or visible.shape != expected:
            raise ValueError("data.predict changed shape during position search")
        size = prediction.nbytes + visible.nbytes
        while self.values and self.bytes + size > self.maximum_bytes:
            old_prediction, old_visible = self.values.popitem(last=False)[1]
            self.bytes -= old_prediction.nbytes + old_visible.nbytes
        if size <= self.maximum_bytes:
            self.values[key] = (prediction, visible)
            self.bytes += size
        return prediction, visible


class _Context:
    def __init__(self, data, arrays, numbers, initial, tracks, deadline):
        self.data = data
        self.arrays = arrays
        self.numbers = numbers
        self.initial = initial
        self.tracks = tracks
        self.deadline = deadline
        self.cache = _PredictionCache(data, initial, len(arrays["times"]))
        self.results = {}
        self.artifacts = {}

    def downstream_initial(self):
        receipt = self.results.get("track_linear")
        if receipt is not None and receipt["success"]:
            return np.asarray(receipt["parameters"], dtype=float), "track_linear"
        status = receipt["status"] if receipt is not None else "not_run"
        return self.initial.copy(), f"data.initial_fallback_after_track_linear_{status}"


class _DeadlineData:
    def __init__(self, data, deadline):
        self._data = data
        self._deadline = deadline

    def __getattr__(self, name):
        return getattr(self._data, name)

    def predict(self, *args, **kwargs):
        _check_deadline(self._deadline)
        return self._data.predict(*args, **kwargs)


def _correction(data, parameters):
    receivers = np.asarray(data.receiver, dtype=int)
    centered = np.asarray(data.times, dtype=float) - 150.0
    return parameters[2 + 2 * receivers] + parameters[3 + 2 * receivers] * centered


def _best_group_assignments(residual, visible, groups):
    residual = np.asarray(residual, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    groups = np.asarray(groups)
    if residual.ndim != 2 or visible.shape != residual.shape or len(groups) != len(residual):
        raise ValueError("group assignment inputs have incompatible shapes")
    usable = visible & np.isfinite(residual)
    absolute = np.where(usable, np.abs(residual), np.inf)
    satellites = np.argmin(absolute, axis=1)
    row_index = np.arange(len(groups))
    errors = residual[row_index, satellites]
    errors = np.where(usable[row_index, satellites], errors, np.inf)
    ordering = np.lexsort((row_index, np.abs(errors), groups))
    first = np.r_[True, groups[ordering][1:] != groups[ordering][:-1]]
    rows = ordering[first]
    return rows, satellites[rows], errors[rows]


def _stable_argmin(values):
    values = np.asarray(values, dtype=float)
    minimum = float(np.min(values))
    close = np.flatnonzero(np.isclose(values, minimum, rtol=1e-10, atol=1e-6))
    return int(close[0]) if len(close) else int(np.argmin(values))


def _glrt_details(context, parameters, candidate_count=SATELLITE_COUNT):
    prediction, visible = context.data.predict(np.asarray(parameters, dtype=float))
    prediction = np.asarray(prediction, dtype=float)[:, :candidate_count]
    visible = np.asarray(visible, dtype=bool)[:, :candidate_count]
    residual = circular(context.arrays["measured"][:, None], prediction)
    rows, satellites, errors = _best_group_assignments(residual, visible, context.arrays["group"])
    matched = np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
    return {
        "rows": rows,
        "satellites": satellites,
        "errors": errors,
        "matched": matched,
        "objective": float(np.mean(rho(errors))),
    }


def _common_diagnostic(context, parameters):
    details = _glrt_details(context, parameters, SATELLITE_COUNT)
    errors = details["errors"]
    matched = details["matched"]
    within_1000 = np.isfinite(errors) & (np.abs(errors) < 1000.0)
    return {
        "definition": (
            "all raw source groups; nearest visible row/candidate among the common 64; "
            "soft-L1 scale 200 Hz with absolute residual capped at 2000 Hz"
        ),
        "groups": int(len(errors)),
        "objective": details["objective"],
        "within_1000_hz": int(np.sum(within_1000)),
        "matched_below_2000_hz": int(np.sum(matched)),
        "matched_rms_hz": (
            float(np.sqrt(np.mean(errors[matched] ** 2))) if np.any(matched) else None
        ),
    }


def _line_step(times, values, weights, initial, slope_limit):
    total = float(np.sum(weights))
    if total <= 0:
        return np.asarray(initial, dtype=float)
    mean_time = float(np.sum(weights * times) / total)
    mean_value = float(np.sum(weights * values) / total)
    variance = float(np.sum(weights * (times - mean_time) ** 2))
    slope = float(
        np.clip(
            np.sum(weights * (times - mean_time) * (values - mean_value)) / max(variance, 1e-20),
            -slope_limit,
            slope_limit,
        )
    )
    return np.array([mean_value - slope * mean_time, slope])


def _exclusive_track_rows(context):
    cached = context.artifacts.get("exclusive_track_rows")
    if cached is not None:
        return cached
    seen_groups = set()
    exclusive = {}
    input_observations = 0
    for track_index, track in enumerate(context.tracks):
        rows = np.asarray(track["rows"], dtype=int)
        input_observations += len(rows)
        retained = []
        for row in rows:
            group = context.arrays["group"][row]
            group = group.item() if isinstance(group, np.generic) else group
            if group in seen_groups:
                continue
            seen_groups.add(group)
            retained.append(int(row))
        exclusive[track_index] = np.asarray(retained, dtype=int)
    accounting = {
        "rows": exclusive,
        "input_track_observations": int(input_observations),
        "modeled_track_observations": int(sum(len(rows) for rows in exclusive.values())),
        "unique_track_source_groups": int(len(seen_groups)),
        "duplicate_track_group_rows": int(input_observations - len(seen_groups)),
        "raw_source_groups": int(len(np.unique(context.arrays["group"]))),
        "raw_source_groups_without_track_rows": int(
            len(np.unique(context.arrays["group"])) - len(seen_groups)
        ),
        "policy": (
            "Before any fit, each raw source group is owned by its first source-order track "
            "and first source-order row; later occurrences are excluded deterministically."
        ),
    }
    context.artifacts["exclusive_track_rows"] = accounting
    return accounting


def _track_blocks(context, prediction, visible):
    accounting = _exclusive_track_rows(context)
    blocks = []
    for track_index, track in enumerate(context.tracks):
        rows = accounting["rows"][track_index]
        if not len(rows):
            continue
        times = context.arrays["times"][rows]
        order = np.lexsort((rows, times))
        measured_ordered = circular(context.arrays["measured"][rows[order]])
        phase = measured_ordered * (2 * np.pi / ALIAS_HZ)
        unwrapped_ordered = np.unwrap(phase) * (ALIAS_HZ / (2 * np.pi))
        unwrapped_measured = np.empty(len(rows), dtype=float)
        unwrapped_measured[order] = unwrapped_ordered
        blocks.append(
            {
                "track_index": track_index,
                "track_id": str(track.get("track_id", track_index)),
                "rows": rows,
                "receiver": int(context.arrays["receiver"][rows[0]]),
                "times": times - 150.0,
                "residual": unwrapped_measured[:, None] - prediction[rows],
                "visible": np.any(visible[rows], axis=0),
            }
        )
    return blocks


def _robust_column_locations(values):
    locations = np.mean(values, axis=0)
    for _iteration in range(15):
        errors = values - locations[None, :]
        weights = 1.0 / np.sqrt(1 + (errors / SCALE_HZ) ** 2)
        updated = np.sum(weights * values, axis=0) / np.maximum(np.sum(weights, axis=0), 1e-20)
        if np.max(np.abs(updated - locations), initial=0.0) < 0.01:
            locations = updated
            break
        locations = updated
    return locations


def _fit_track_independent(blocks):
    selected = []
    for block in blocks:
        offsets = _robust_column_locations(block["residual"])
        costs = np.mean(_raw_rho(block["residual"] - offsets[None, :]), axis=0)
        costs = np.where(block["visible"], costs, np.inf)
        satellite = _stable_argmin(costs)
        cost = float(costs[satellite])
        errors = block["residual"][:, satellite] - offsets[satellite]
        selected.append(
            {
                **block,
                "satellite": satellite,
                "offset_hz": float(offsets[satellite]),
                "alias_branch": None,
                "cost": cost,
                "errors": errors,
                "accepted": bool(np.isfinite(cost) and cost < UNMATCHED_COST),
            }
        )
    objective = float(np.mean([min(row["cost"], UNMATCHED_COST) for row in selected]))
    return objective, selected, {}


def _shared_candidate(block, line):
    expected = line[0] + line[1] * block["times"]
    difference = block["residual"] - expected[:, None]
    branches = np.rint(np.mean(difference, axis=0) / ALIAS_HZ)
    errors = difference - branches[None, :] * ALIAS_HZ
    costs = np.mean(_raw_rho(errors), axis=0)
    costs = np.where(block["visible"], costs, np.inf)
    satellite = _stable_argmin(costs)
    return satellite, float(branches[satellite]), float(costs[satellite]), errors[:, satellite]


def _receiver_line_starts(blocks, initial):
    folded = []
    for block in blocks:
        means = np.mean(block["residual"], axis=0)
        folded.extend(circular(means[block["visible"]]).tolist())
    starts = [np.asarray(initial, dtype=float)]
    if folded:
        histogram, edges = np.histogram(folded, bins=128, range=(-ALIAS_HZ / 2, ALIAS_HZ / 2))
        for index in np.argsort(-histogram, kind="stable")[:2]:
            starts.append(np.array([(edges[index] + edges[index + 1]) / 2, 0.0]))
    unique = []
    for start in starts:
        if not any(np.linalg.norm(start - previous) < 1e-9 for previous in unique):
            unique.append(start)
    return unique


def _fit_receiver_shared(blocks, initial, slope_limit):
    if not blocks:
        return np.asarray(initial, dtype=float), []
    best = None
    for start in _receiver_line_starts(blocks, initial):
        line = start.copy()
        line[1] = np.clip(line[1], -slope_limit, slope_limit)
        for _iteration in range(20):
            choices = [_shared_candidate(block, line) for block in blocks]
            time_parts = []
            value_parts = []
            weight_parts = []
            for block, (satellite, branch, cost, errors) in zip(blocks, choices, strict=True):
                if not np.isfinite(cost) or cost >= UNMATCHED_COST:
                    continue
                values = block["residual"][:, satellite] - branch * ALIAS_HZ
                weights = np.full(len(values), 1.0 / len(values))
                weights /= np.sqrt(1 + (errors / SCALE_HZ) ** 2)
                time_parts.append(block["times"])
                value_parts.append(values)
                weight_parts.append(weights)
            if not time_parts:
                break
            updated = _line_step(
                np.concatenate(time_parts),
                np.concatenate(value_parts),
                np.concatenate(weight_parts),
                line,
                slope_limit,
            )
            change = abs(updated[0] - line[0]) + 150 * abs(updated[1] - line[1])
            line = updated
            if change < 0.05:
                break
        choices = [_shared_candidate(block, line) for block in blocks]
        score = float(np.mean([min(choice[2], UNMATCHED_COST) for choice in choices]))
        if best is None or score < best[0]:
            best = score, line, choices
    return best[1], best[2]


def _fit_track_shared(blocks, initial_parameters, slope_limit):
    _, independent, _ = _fit_track_independent(blocks)
    seeded_parameters = np.asarray(initial_parameters, dtype=float).copy()
    for receiver in (0, 1):
        local = [row for row in independent if row["receiver"] == receiver and row["accepted"]]
        if not local:
            continue
        times = np.asarray([np.mean(row["times"]) for row in local])
        offsets = np.asarray([row["offset_hz"] for row in local])
        initial_line = initial_parameters[2 + 2 * receiver : 4 + 2 * receiver]
        expected = initial_line[0] + initial_line[1] * times
        offsets -= np.rint((offsets - expected) / ALIAS_HZ) * ALIAS_HZ
        seeded_parameters[2 + 2 * receiver : 4 + 2 * receiver] = _line_step(
            times, offsets, np.ones(len(times)), initial_line, slope_limit
        )
    lines = {}
    choice_by_track = {}
    for receiver in (0, 1):
        local = [block for block in blocks if block["receiver"] == receiver]
        initial = seeded_parameters[2 + 2 * receiver : 4 + 2 * receiver]
        line, choices = _fit_receiver_shared(local, initial, slope_limit)
        lines[receiver] = line
        for block, choice in zip(local, choices, strict=True):
            choice_by_track[block["track_index"]] = choice
    selected = []
    for block in blocks:
        satellite, branch, cost, errors = choice_by_track[block["track_index"]]
        selected.append(
            {
                **block,
                "satellite": satellite,
                "offset_hz": float(lines[block["receiver"]][0]),
                "alias_branch": int(branch),
                "cost": cost,
                "errors": errors,
                "accepted": bool(np.isfinite(cost) and cost < UNMATCHED_COST),
            }
        )
    objective = float(np.mean([min(row["cost"], UNMATCHED_COST) for row in selected]))
    return objective, selected, lines


def _track_evaluate(context, point, mode):
    prediction, visible = context.cache.get(point)
    blocks = _track_blocks(context, prediction, visible)
    if mode == "independent":
        return fit_track_independent(blocks)
    return fit_track_shared(blocks, context.initial, 0.0 if mode == "constant" else 50.0)


def _grid_points():
    values = np.arange(-POSITION_BOUND_KM, POSITION_BOUND_KM + 0.1, GRID_STEP_KM)
    return [np.array([east, north], dtype=float) for east in values for north in values]


def _unique_points(points):
    unique = []
    keys = set()
    for point in points:
        clipped = np.clip(np.asarray(point, dtype=float), -POSITION_BOUND_KM, POSITION_BOUND_KM)
        key = tuple(np.round(clipped, 8))
        if key not in keys:
            keys.add(key)
            unique.append(clipped)
    return unique


def _search_position(evaluate, preferred, deadline, maxfev=240):
    grid = []
    for point in _grid_points():
        _check_deadline(deadline)
        score, details = evaluate(point)
        if np.isfinite(score):
            grid.append((float(score), point.copy(), details))
    if not grid:
        raise RuntimeError("broad position grid produced no finite objective")
    grid.sort(key=lambda row: (row[0], row[1][0], row[1][1]))
    candidates = _unique_points([preferred, *[row[1] for row in grid[:3]]])
    ranked = sorted(((evaluate(point)[0], point) for point in candidates), key=lambda row: row[0])
    seeds = [row[1] for row in ranked[:2]]
    runs = []
    successful = []
    attempts = [(grid[0][0], grid[0][1])]
    from scipy.optimize import minimize

    for seed in seeds:
        _check_deadline(deadline)

        def objective(point):
            _check_deadline(deadline)
            return evaluate(point)[0]

        try:
            simplex = np.tile(seed, (3, 1))
            simplex[1, 0] += 5 if seed[0] <= POSITION_BOUND_KM - 5 else -5
            simplex[2, 1] += 5 if seed[1] <= POSITION_BOUND_KM - 5 else -5
            fitted = minimize(
                objective,
                seed,
                method="Nelder-Mead",
                bounds=[(-POSITION_BOUND_KM, POSITION_BOUND_KM)] * 2,
                options={
                    "maxfev": maxfev,
                    "xatol": 0.02,
                    "fatol": 0.05,
                    "initial_simplex": simplex,
                },
            )
        except _LimitReached:
            runs.append(
                {
                    "seed": seed.tolist(),
                    "success": False,
                    "status": "limit_reached",
                    "message": "model wall-clock budget reached",
                }
            )
            break
        score = float(fitted.fun) if np.isfinite(fitted.fun) else math.inf
        run = {
            "seed": seed.tolist(),
            "point": np.asarray(fitted.x, dtype=float).tolist(),
            "objective": _finite_float(score),
            "success": bool(fitted.success and np.isfinite(score)),
            "optimizer_status": int(fitted.status),
            "message": str(fitted.message),
            "evaluations": int(fitted.nfev),
        }
        runs.append(run)
        if np.isfinite(score):
            attempts.append((score, np.asarray(fitted.x, dtype=float)))
        if run["success"]:
            successful.append((score, np.asarray(fitted.x, dtype=float)))
    if successful:
        score, point = min(successful, key=lambda row: row[0])
        final_score, details = evaluate(point)
        return {
            "success": True,
            "status": "converged",
            "message": "bounded broad grid and local search converged",
            "objective": float(final_score),
            "point": point,
            "details": details,
            "grid_best": {"point": grid[0][1].tolist(), "objective": grid[0][0]},
            "local_runs": runs,
        }
    _, point = min(attempts, key=lambda row: row[0])
    score, details = evaluate(point)
    return {
        "success": False,
        "status": "limit_reached"
        if any(row.get("status") == "limit_reached" for row in runs)
        else "optimizer_failed",
        "message": "; ".join(row["message"] for row in runs) or "no local search completed",
        "objective": float(score),
        "point": point,
        "details": details,
        "grid_best": {"point": grid[0][1].tolist(), "objective": grid[0][0]},
        "local_runs": runs,
    }


def _track_receipt(context, model_name, deadline):
    mode = model_name.removeprefix("track_")
    preferred = context.initial[:2]
    if mode != "independent":
        independent = context.results.get("track_independent")
        if independent is not None and independent["success"]:
            preferred = np.asarray(independent["parameters"][:2], dtype=float)
    search = _search_position(
        lambda point: (lambda fitted: (fitted[0], fitted))(_track_evaluate(context, point, mode)),
        preferred,
        deadline,
        maxfev=240,
    )
    objective, selected, lines = search["details"]
    parameters = np.zeros(PARAMETER_COUNT)
    parameters[:2] = search["point"]
    if mode != "independent":
        for receiver in (0, 1):
            parameters[2 + 2 * receiver : 4 + 2 * receiver] = lines[receiver]
    accepted = [row for row in selected if row["accepted"]]
    errors = np.concatenate([row["errors"] for row in accepted]) if accepted else np.array([])
    assigned_rows = (
        np.concatenate([row["rows"] for row in accepted]).astype(int)
        if accepted
        else np.empty(0, dtype=int)
    )
    nuisance = []
    if mode == "independent":
        nuisance = [
            {
                "track_id": row["track_id"],
                "track_index": row["track_index"],
                "offset_hz": row["offset_hz"],
            }
            for row in selected
        ]
    tracks = [
        {
            "track_id": row["track_id"],
            "track_index": row["track_index"],
            "catalog_number": context.numbers[row["satellite"]].item()
            if isinstance(context.numbers[row["satellite"]], np.generic)
            else context.numbers[row["satellite"]],
            "satellite_index": row["satellite"],
            "accepted": row["accepted"],
            "cost": _finite_float(row["cost"]),
            "observations": int(len(row["rows"])),
            "offset_hz": row["offset_hz"],
            "alias_branch": row["alias_branch"],
        }
        for row in selected
    ]
    free = ["east_km", "north_km"]
    if mode == "independent":
        free.extend(f"track_offset_hz[{row['track_id']}]" for row in selected)
    else:
        for receiver in (0, 1):
            free.append(f"rx{receiver}_intercept_hz_at_150s")
            if mode == "linear":
                free.append(f"rx{receiver}_slope_hz_s")
    accounting = _exclusive_track_rows(context)
    return {
        "parameters": parameters,
        "success": search["success"],
        "status": search["status"],
        "message": search["message"],
        "objective": objective,
        "free_parameters": free,
        "assigned_groups": int(len(np.unique(context.arrays["group"][assigned_rows]))),
        "assigned_observations": int(len(assigned_rows)),
        "assigned_tracks": int(len(accepted)),
        "fixed_assignment_rms_hz": (float(np.sqrt(np.mean(errors**2))) if len(errors) else None),
        "common_full_group_diagnostic": (
            None if mode == "independent" else _common_diagnostic(context, parameters)
        ),
        "nuisance_parameters": nuisance,
        "tracks": tracks,
        "candidate_scope": (
            "Every whole track selects one satellite from the same supplied 64-candidate pool; "
            "this intentionally differs from the older per-track top-five prototype."
        ),
        "track_alias_policy": (
            "A working copy of each retained track is stably sorted by time and source row, "
            "unwrapped at the native 1/4.4us alias period, restored to source-row order, and "
            "differenced from unwrapped TLE prediction. Raw data.measured is unchanged. Integer "
            "alias lifts are exactly nuisance-equivalent; unwrap branch continuity across long "
            "observation gaps remains a conditional ambiguity."
        ),
        "track_group_accounting": {
            key: value for key, value in accounting.items() if key != "rows"
        },
        "objective_comparability": (
            "Track objective is equal-weighted over retained whole tracks after deterministic "
            "raw-group exclusivity. Its source-group universe may be smaller than the GLRT raw "
            "group universe, so objective magnitude is not directly comparable to GLRT models."
        ),
        "training_scope": (
            "all deterministically retained group-exclusive track observations; no holdout"
        ),
        "initialization_provenance": (
            "broad +/-200 km grid; independent whole-track robust offsets seed shared RX lines"
            if mode != "independent"
            else "broad +/-200 km grid; per-track robust offset profiling"
        ),
        "search": {
            "grid_step_km": GRID_STEP_KM,
            "grid_best": search["grid_best"],
            "local_runs": search["local_runs"],
        },
    }


def _profile_receiver_glrt(context, base, visible, candidate_count, receiver, initial):
    lane = context.arrays["receiver"] == receiver
    if not np.any(lane):
        return np.asarray(initial, dtype=float)
    times = context.arrays["times"] - 150.0
    base_residual = context.arrays["measured"][:, None] - base[:, :candidate_count]
    finite = circular(base_residual[lane] - initial[1] * times[lane, None])
    finite = finite[np.isfinite(finite) & visible[lane, :candidate_count]]
    starts = [np.asarray(initial, dtype=float)]
    if len(finite):
        histogram, edges = np.histogram(finite, bins=128, range=(-ALIAS_HZ / 2, ALIAS_HZ / 2))
        for index in np.argsort(-histogram, kind="stable")[:2]:
            starts.append(np.array([(edges[index] + edges[index + 1]) / 2, 0.0]))
    best = None
    for start in starts:
        line = start.copy()
        for _iteration in range(15):
            correction = line[0] + line[1] * times
            residual = circular(base_residual, correction[:, None])
            rows, _, errors = _best_group_assignments(
                residual[lane], visible[lane, :candidate_count], context.arrays["group"][lane]
            )
            absolute_rows = np.flatnonzero(lane)[rows]
            use = np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
            if not np.any(use):
                break
            selected = absolute_rows[use]
            values = errors[use] + line[0] + line[1] * times[selected]
            weights = 1.0 / np.sqrt(1 + (errors[use] / SCALE_HZ) ** 2)
            updated = _line_step(times[selected], values, weights, line, 50.0)
            change = abs(updated[0] - line[0]) + 150 * abs(updated[1] - line[1])
            line = updated
            if change < 0.05:
                break
        correction = line[0] + line[1] * times
        residual = circular(base_residual, correction[:, None])
        _, _, errors = _best_group_assignments(
            residual[lane], visible[lane, :candidate_count], context.arrays["group"][lane]
        )
        score = float(np.mean(rho(errors)))
        if best is None or score < best[0]:
            best = score, line
    return best[1]


def _glrt_at_point(context, point, candidate_count, frozen_parameters=None, profile=False):
    base, visible = context.cache.get(point)
    parameters = np.zeros(PARAMETER_COUNT)
    parameters[:2] = point
    if profile:
        seed = context.initial if frozen_parameters is None else frozen_parameters
        for receiver in (0, 1):
            parameters[2 + 2 * receiver : 4 + 2 * receiver] = _profile_receiver_glrt(
                context,
                base,
                visible,
                candidate_count,
                receiver,
                seed[2 + 2 * receiver : 4 + 2 * receiver],
            )
    elif frozen_parameters is not None:
        parameters[2:6] = frozen_parameters[2:6]
    correction = _correction(context.data, parameters)
    residual = circular(
        context.arrays["measured"][:, None],
        base[:, :candidate_count] + correction[:, None],
    )
    rows, satellites, errors = _best_group_assignments(
        residual, visible[:, :candidate_count], context.arrays["group"]
    )
    return float(np.mean(rho(errors))), {
        "parameters": parameters,
        "rows": rows,
        "satellites": satellites,
        "errors": errors,
    }


def _glrt_receipt(context, model_name, deadline):
    initial, provenance = context.downstream_initial()
    profile = model_name == "glrt_free_16"
    candidate_count = 16 if profile else int(model_name.rsplit("_", 1)[1])
    search = _search_position(
        lambda point: _glrt_at_point(
            context,
            point,
            candidate_count,
            frozen_parameters=initial,
            profile=profile,
        ),
        initial[:2],
        deadline,
        maxfev=240,
    )
    details = search["details"]
    parameters = details["parameters"]
    errors = details["errors"]
    matched = np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
    free = ["east_km", "north_km"]
    if profile:
        free.extend(
            [
                "rx0_intercept_hz_at_150s",
                "rx0_slope_hz_s",
                "rx1_intercept_hz_at_150s",
                "rx1_slope_hz_s",
            ]
        )
    receipt = {
        "parameters": parameters,
        "success": search["success"],
        "status": search["status"],
        "message": search["message"],
        "objective": search["objective"],
        "free_parameters": free,
        "assigned_groups": int(np.sum(matched)),
        "total_source_groups": int(len(errors)),
        "fixed_assignment_rms_hz": (
            float(np.sqrt(np.mean(errors[matched] ** 2))) if np.any(matched) else None
        ),
        "common_full_group_diagnostic": _common_diagnostic(context, parameters),
        "candidate_count": candidate_count,
        "candidate_scope": f"nested frozen prefix {candidate_count} of supplied 64 candidates",
        "training_scope": "all raw source groups; no holdout",
        "rx_policy": (
            "profiled jointly with position" if profile else f"frozen RX line: {provenance}"
        ),
        "initialization_provenance": provenance,
        "search": {
            "grid_step_km": GRID_STEP_KM,
            "grid_best": search["grid_best"],
            "local_runs": search["local_runs"],
        },
    }
    context.artifacts[model_name] = {
        "parameters": parameters.copy(),
        "rows": details["rows"].copy(),
        "satellites": details["satellites"].copy(),
    }
    return receipt


class _TimingObjective:
    def __init__(self, context, frozen, sigma_s, bound_s, deadline):
        self.context = context
        self.frozen = np.asarray(frozen, dtype=float).copy()
        self.frozen[6:] = 0.0
        self.sigma_s = float(sigma_s)
        self.bound_s = float(bound_s)
        self.deadline = deadline
        self.calls = 0
        self.last = None

    def parameters(self, vector):
        parameters = self.frozen.copy()
        parameters[:2] = vector[:2]
        parameters[6:] = vector[2:]
        return parameters

    def evaluate(self, vector):
        _check_deadline(self.deadline)
        self.calls += 1
        parameters = self.parameters(vector)
        prediction, visible = self.context.data.predict(parameters)
        prediction = np.asarray(prediction, dtype=float)
        visible = np.asarray(visible, dtype=bool)
        residual = circular(self.context.arrays["measured"][:, None], prediction)
        rows, satellites, errors = _best_group_assignments(
            residual, visible, self.context.arrays["group"]
        )
        data_objective = float(np.sum(rho(errors)) / (2 * SCALE_HZ**2))
        prior = float(0.5 * np.sum((vector[2:] / self.sigma_s) ** 2))
        derivative = np.zeros(len(errors))
        active = np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
        derivative[active] = (
            errors[active] / SCALE_HZ**2 / np.sqrt(1 + (errors[active] / SCALE_HZ) ** 2)
        )
        gradient = np.zeros_like(vector)
        for coordinate, step in ((0, 0.01), (1, 0.01)):
            plus = parameters.copy()
            minus = parameters.copy()
            plus[coordinate] += step
            minus[coordinate] -= step
            plus_prediction, _ = self.context.data.predict(plus, rows=rows, satellites=satellites)
            minus_prediction, _ = self.context.data.predict(minus, rows=rows, satellites=satellites)
            prediction_derivative = circular(plus_prediction, minus_prediction) / (2 * step)
            gradient[coordinate] = -float(np.sum(derivative * prediction_derivative))
        step = 0.001
        plus = parameters.copy()
        minus = parameters.copy()
        plus[6:] += step
        minus[6:] -= step
        plus_prediction, _ = self.context.data.predict(plus, rows=rows, satellites=satellites)
        minus_prediction, _ = self.context.data.predict(minus, rows=rows, satellites=satellites)
        prediction_derivative = circular(plus_prediction, minus_prediction) / (2 * step)
        gradient[2:] = np.bincount(
            satellites, weights=-derivative * prediction_derivative, minlength=SATELLITE_COUNT
        )
        gradient[2:] += vector[2:] / self.sigma_s**2
        self.last = {
            "parameters": parameters,
            "rows": rows,
            "satellites": satellites,
            "errors": errors,
            "data_objective": data_objective,
            "prior_objective": prior,
        }
        return data_objective + prior, gradient


def _timing_receipt(context, model_name, deadline):
    initial, provenance = context.downstream_initial()
    baseline = context.artifacts.get("glrt_fixed_64")
    if baseline is not None and context.results.get("glrt_fixed_64", {}).get("success"):
        start_position = baseline["parameters"][:2]
        baseline_provenance = "successful glrt_fixed_64 position"
    else:
        start_position = initial[:2]
        baseline_status = context.results.get("glrt_fixed_64", {}).get("status", "not_run")
        baseline_provenance = f"{provenance}; fallback after glrt_fixed_64_{baseline_status}"
    sigma_s, bound_s = (1.0, 3.0) if model_name.endswith("3s") else (10.0 / 3.0, 10.0)
    objective = _TimingObjective(context, initial, sigma_s, bound_s, deadline)
    starts = [
        ("zero timing", np.r_[position, np.zeros(SATELLITE_COUNT)])
        for position in _unique_points([start_position, initial[:2]])
    ]
    previous = context.results.get("glrt_timing_3s", {})
    if model_name == "glrt_timing_10s" and previous.get("success"):
        warm = np.asarray(previous["parameters"], dtype=float)
        starts.insert(0, ("successful glrt_timing_3s", np.r_[warm[:2], warm[6:]]))
    from scipy.optimize import minimize

    runs = []
    successful = []
    best_attempt = None
    for seed_kind, vector in starts:
        position = vector[:2]
        try:
            fitted = minimize(
                objective.evaluate,
                vector,
                jac=True,
                method="L-BFGS-B",
                bounds=[(-POSITION_BOUND_KM, POSITION_BOUND_KM)] * 2
                + [(-bound_s, bound_s)] * SATELLITE_COUNT,
                options={"maxiter": 700, "maxfun": 1000, "ftol": 1e-9, "gtol": 1e-4, "maxls": 25},
            )
        except _LimitReached:
            runs.append(
                {
                    "seed_position": position.tolist(),
                    "seed_kind": seed_kind,
                    "seed_timing_norm_s": float(np.linalg.norm(vector[2:])),
                    "success": False,
                    "status": "limit_reached",
                    "message": "model wall-clock budget reached",
                }
            )
            break
        run = {
            "seed_position": position.tolist(),
            "seed_kind": seed_kind,
            "seed_timing_norm_s": float(np.linalg.norm(vector[2:])),
            "success": bool(fitted.success and np.isfinite(fitted.fun)),
            "optimizer_status": int(fitted.status),
            "message": str(fitted.message),
            "iterations": int(fitted.nit),
            "evaluations": int(fitted.nfev),
            "objective": _finite_float(fitted.fun),
        }
        runs.append(run)
        attempt = (
            float(fitted.fun),
            np.asarray(fitted.x, dtype=float),
            run,
            None if objective.last is None else dict(objective.last),
        )
        if best_attempt is None or attempt[0] < best_attempt[0]:
            best_attempt = attempt
        if run["success"]:
            successful.append(attempt)
    if best_attempt is None:
        raise _LimitReached("timing model did not complete an optimizer run")
    winner = min(successful, key=lambda row: row[0]) if successful else best_attempt
    parameters = objective.parameters(winner[1])
    details = _glrt_details(context, parameters)
    details["parameters"] = parameters
    details["data_objective"] = float(np.sum(rho(details["errors"])) / (2 * SCALE_HZ**2))
    details["prior_objective"] = float(0.5 * np.sum((parameters[6:] / sigma_s) ** 2))
    value = details["data_objective"] + details["prior_objective"]
    errors = details["errors"]
    matched = np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
    status = (
        "converged"
        if successful
        else (
            "limit_reached"
            if any(row.get("status") == "limit_reached" for row in runs)
            else "optimizer_failed"
        )
    )
    parameters = details["parameters"]
    group_count = len(errors)
    comparable_objective = float(2 * SCALE_HZ**2 * value / group_count)
    return {
        "parameters": parameters,
        "success": bool(successful),
        "status": status,
        "message": winner[2]["message"],
        "objective": comparable_objective,
        "optimizer_objective": float(value),
        "frequency_objective": float(2 * SCALE_HZ**2 * details["data_objective"] / group_count),
        "timing_prior_objective": details["prior_objective"],
        "free_parameters": ["east_km", "north_km"]
        + [f"tau_{index}_s" for index in range(SATELLITE_COUNT)],
        "assigned_groups": int(np.sum(matched)),
        "total_source_groups": int(group_count),
        "fixed_assignment_rms_hz": (
            float(np.sqrt(np.mean(errors[matched] ** 2))) if np.any(matched) else None
        ),
        "common_full_group_diagnostic": _common_diagnostic(context, parameters),
        "candidate_count": SATELLITE_COUNT,
        "rx_policy": f"RX intercepts/slopes frozen at receive time: {provenance}",
        "timing_sigma_s": sigma_s,
        "timing_bound_s": bound_s,
        "timing_at_bound": int(np.sum(np.abs(parameters[6:]) >= bound_s - 1e-6)),
        "initialization_provenance": baseline_provenance,
        "optimizer_runs": runs,
        "objective_units": (
            "mean capped soft-L1 frequency loss plus Gaussian penalty scaled by "
            "2*200^2/source-group-count"
        ),
    }


_COHERENT_MODULES = None


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _coherent_modules():
    global _COHERENT_MODULES
    if _COHERENT_MODULES is not None:
        return _COHERENT_MODULES
    common = _load_module("_localization_benchmark_coherent_common", COHERENT_ROOT / "common.py")
    previous_common = sys.modules.get("common")
    sys.modules["common"] = common
    try:
        anchors = _load_module(
            "_localization_benchmark_coherent_anchors", COHERENT_ROOT / "anchors.py"
        )
        association = _load_module(
            "_localization_benchmark_coherent_association", COHERENT_ROOT / "association.py"
        )
        refinement = _load_module(
            "_localization_benchmark_coherent_refinement", Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_02_localization_benchmark/investigation-scan-fw-49d3aae278813149/slope50/refinement.py')
        )
    finally:
        if previous_common is None:
            del sys.modules["common"]
        else:
            sys.modules["common"] = previous_common
    _COHERENT_MODULES = anchors, association, refinement
    return _COHERENT_MODULES


def _validate_assignments(context, assignments):
    rows = np.asarray(assignments.get("rows", []), dtype=int)
    satellites = np.asarray(assignments.get("satellites", []), dtype=int)
    weights = np.asarray(assignments.get("weights", []), dtype=float)
    if not len(rows):
        raise _NoAnchors("no usable coherent assignments")
    if not (rows.shape == satellites.shape == weights.shape):
        raise ValueError("coherent assignment arrays have unequal shapes")
    if len(np.unique(context.arrays["group"][rows])) != len(rows):
        raise ValueError("coherent assignments do not have raw-group exclusivity")
    if np.any(~np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError("coherent assignment weights must be positive and finite")


def _coherent_assignment_metrics(context, parameters, assignments):
    rows = np.asarray(assignments["rows"], dtype=int)
    satellites = np.asarray(assignments["satellites"], dtype=int)
    weights = np.asarray(assignments["weights"], dtype=float)
    prediction, visible = context.data.predict(parameters, rows=rows, satellites=satellites)
    errors = circular(context.arrays["measured"][rows], prediction)
    usable = np.asarray(visible, dtype=bool) & np.isfinite(errors)
    return {
        "assigned_groups": int(len(rows)),
        "assigned_satellites": int(len(np.unique(satellites))),
        "effective_weight": float(np.sum(weights)),
        "fixed_assignment_rms_hz": (
            float(np.sqrt(np.average(errors[usable] ** 2, weights=weights[usable])))
            if np.any(usable)
            else None
        ),
        "assigned_visible_within_1000_hz": int(np.sum(usable & (np.abs(errors) < 1000.0))),
    }


def _successful_fit(fits):
    successful = [
        fit for fit in fits if fit.get("success") and np.isfinite(fit.get("objective", np.nan))
    ]
    return min(successful, key=lambda fit: fit["objective"]) if successful else None


def _build_anchor_artifact(context, deadline):
    if "anchors" in context.artifacts:
        return context.artifacts["anchors"]
    anchors_module, _, refinement = _coherent_modules()
    bounded_data = _DeadlineData(context.data, deadline)
    initial, provenance = context.downstream_initial()
    _check_deadline(deadline)
    assignments = anchors_module.select_anchors(bounded_data, initial, max_tracks=12)
    _validate_assignments(context, assignments)
    fits = []
    for offset in ([0.0, 0.0], [5.0, -5.0]):
        _check_deadline(deadline)
        start = initial.copy()
        start[:2] = np.clip(start[:2] + offset, -POSITION_BOUND_KM, POSITION_BOUND_KM)
        fits.append(
            refinement.fit_fixed(bounded_data, assignments, start, timing=False, max_nfev=100)
        )
    fitted = _successful_fit(fits)
    if fitted is None:
        message = "; ".join(str(fit.get("message", "fit failed")) for fit in fits)
        raise RuntimeError(f"anchor refinements failed: {message}")
    artifact = {
        "assignments": assignments,
        "fit": fitted,
        "parameters": np.asarray(fitted["parameters"], dtype=float),
        "initialization_provenance": provenance,
        "starts": fits,
    }
    context.artifacts["anchors"] = artifact
    return artifact


def _build_extension_artifact(context, deadline):
    if "extensions" in context.artifacts:
        return context.artifacts["extensions"]
    _, association, refinement = _coherent_modules()
    bounded_data = _DeadlineData(context.data, deadline)
    anchor = _build_anchor_artifact(context, deadline)
    parameters = anchor["parameters"].copy()
    anchors = anchor["assignments"]
    previous_keys = None
    iterations = []
    converged = False
    assignments = None
    fitted = None
    for iteration in range(6):
        _check_deadline(deadline)
        assignments = association.associate(bounded_data, parameters, anchors)
        _validate_assignments(context, assignments)
        fitted = refinement.fit_fixed(
            bounded_data, assignments, parameters, timing=False, max_nfev=100
        )
        if not fitted.get("success") or not np.isfinite(fitted.get("objective", np.nan)):
            raise RuntimeError(f"extension refinement failed: {fitted.get('message', 'unknown')}")
        parameters = np.asarray(fitted["parameters"], dtype=float)
        keys = set(
            zip(
                context.arrays["group"][assignments["rows"]].tolist(),
                np.asarray(assignments["satellites"], dtype=int).tolist(),
                strict=True,
            )
        )
        iterations.append(
            {
                "iteration": iteration,
                "objective": float(fitted["objective"]),
                "assigned_groups": int(len(assignments["rows"])),
                "changed_group_satellite_pairs": (
                    None if previous_keys is None else len(keys.symmetric_difference(previous_keys))
                ),
            }
        )
        if previous_keys == keys:
            converged = True
            break
        previous_keys = keys
    artifact = {
        "assignments": assignments,
        "fit": fitted,
        "parameters": parameters,
        "iterations": iterations,
        "converged": converged,
        "anchors": anchor,
    }
    if converged:
        context.artifacts["extensions"] = artifact
    return artifact


def _coherent_receipt(context, model_name, deadline):
    _, _, refinement = _coherent_modules()
    bounded_data = _DeadlineData(context.data, deadline)
    if model_name == "anchors":
        artifact = _build_anchor_artifact(context, deadline)
        assignments = artifact["assignments"]
        fitted = artifact["fit"]
        parameters = artifact["parameters"]
        status = "converged"
        success = True
        message = str(fitted.get("message", "anchor fit converged"))
        extra = {
            "selected_anchor_tracks": int(
                assignments.get("diagnostics", {}).get("selected_track_count", 0)
            ),
            "anchor_diagnostics": assignments.get("diagnostics"),
            "optimizer_starts": artifact["starts"],
        }
        coherent_provenance = artifact["initialization_provenance"]
    elif model_name == "extensions":
        artifact = _build_extension_artifact(context, deadline)
        assignments = artifact["assignments"]
        fitted = artifact["fit"]
        parameters = artifact["parameters"]
        success = artifact["converged"]
        status = "converged" if success else "limit_reached"
        message = (
            str(fitted.get("message", "extension fit converged"))
            if success
            else "association did not stabilize within six iterations"
        )
        extra = {
            "association_iterations": artifact["iterations"],
            "association_converged": artifact["converged"],
            "association_diagnostics": assignments.get("diagnostics"),
        }
        coherent_provenance = artifact["anchors"]["initialization_provenance"]
    else:
        extension = _build_extension_artifact(context, deadline)
        if not extension["converged"]:
            assignments = extension["assignments"]
            parameters = extension["parameters"]
            fitted = extension["fit"]
            success = False
            status = "limit_reached"
            message = "independent extension chain did not stabilize within six iterations"
            extra = {
                "association_iterations": extension["iterations"],
                "association_converged": False,
            }
        else:
            assignments = extension["assignments"]
            _check_deadline(deadline)
            fitted = refinement.fit_fixed(
                bounded_data,
                assignments,
                extension["parameters"],
                timing=True,
                sigma_s=1.0,
                bound_s=3.0,
                max_nfev=130,
            )
            parameters = np.asarray(fitted["parameters"], dtype=float)
            success = bool(fitted.get("success") and np.isfinite(fitted.get("objective", np.nan)))
            status = "converged" if success else "optimizer_failed"
            message = str(fitted.get("message", "coherent timing fit failed"))
            extra = {
                "association_iterations": extension["iterations"],
                "association_converged": True,
                "timing_sigma_s": 1.0,
                "timing_bound_s": 3.0,
                "timing_diagnostics": fitted.get("diagnostics"),
            }
        coherent_provenance = extension["anchors"]["initialization_provenance"]
    metrics = _coherent_assignment_metrics(context, parameters, assignments)
    free = [
        "east_km",
        "north_km",
        "rx0_intercept_hz_at_150s",
        "rx0_slope_hz_s",
        "rx1_intercept_hz_at_150s",
        "rx1_slope_hz_s",
    ]
    if model_name == "coherent_timing":
        active = fitted.get("diagnostics", {}).get("active_timing_satellites", [])
        free.extend(f"tau_{satellite}_s" for satellite in active)
    return {
        "parameters": parameters,
        "success": success,
        "status": status,
        "message": message,
        "objective": _finite_float(fitted.get("objective", np.nan)),
        "free_parameters": free,
        **metrics,
        "common_full_group_diagnostic": _common_diagnostic(context, parameters),
        "candidate_scope": "conditional associations within the supplied 64-candidate pool",
        "training_scope": "all admitted raw groups; one original observation per group",
        "initialization_provenance": coherent_provenance,
        **extra,
    }


def _fallback_parameters(context):
    parameters, _ = context.downstream_initial()
    return parameters


def _failure_receipt(context, model_name, status, error):
    parameters = _fallback_parameters(context)
    free = []
    if model_name.startswith("track_") or model_name.startswith("glrt_"):
        free = ["east_km", "north_km"]
    return {
        "parameters": parameters,
        "success": False,
        "status": status,
        "message": str(error),
        "error": f"{type(error).__name__}: {error}",
        "objective": None,
        "free_parameters": free,
        "assigned_groups": 0,
        "fixed_assignment_rms_hz": None,
        "common_full_group_diagnostic": None,
        "initialization_provenance": context.downstream_initial()[1],
    }


def _normalize_receipt(model_name, receipt, elapsed_s):
    normalized = dict(receipt)
    parameters = np.asarray(normalized.get("parameters"), dtype=float)
    if parameters.shape != (PARAMETER_COUNT,) or not np.all(np.isfinite(parameters)):
        raise ValueError(f"{model_name} receipt parameters must be finite length 70")
    normalized["model"] = model_name
    normalized["parameters"] = parameters.tolist()
    normalized["success"] = bool(normalized.get("success", False))
    normalized["attempted"] = bool(normalized.get("attempted", True))
    normalized["status"] = str(normalized.get("status", "error"))
    normalized["objective"] = _finite_float(normalized.get("objective", np.nan))
    raw_free_parameters = normalized.get("free_parameters", [])
    if isinstance(raw_free_parameters, (int, np.integer)):
        normalized["free_parameters"] = int(raw_free_parameters)
    else:
        names = list(raw_free_parameters)
        normalized["free_parameter_names"] = names
        normalized["free_parameters"] = len(names)
    normalized["assigned_groups"] = int(normalized.get("assigned_groups", 0))
    normalized["elapsed_s"] = float(elapsed_s)
    normalized["provenance_scope"] = (
        "conditional known-site candidate evidence and supplied initial prior; no reference truth "
        "used for fit or hyperparameter selection; not blind localization validation"
    )
    return normalized


def _dispatch(context, model_name, deadline):
    if model_name.startswith("track_"):
        return _track_receipt(context, model_name, deadline)
    if model_name.startswith("glrt_fixed_") or model_name == "glrt_free_16":
        return _glrt_receipt(context, model_name, deadline)
    if model_name.startswith("glrt_timing_"):
        return _timing_receipt(context, model_name, deadline)
    return _coherent_receipt(context, model_name, deadline)


def run_models(data, checkpoint=None):
    """Run the frozen 13-model sequence for one scan.

    ``checkpoint``, when supplied, is called with the accumulated result mapping
    after every model receipt, including failures and budget-exhausted entries.
    Callback exceptions propagate so callers never mistake a failed persistence
    operation for a completed checkpoint.
    """

    started = time.monotonic()
    overall_deadline = started + TOTAL_BUDGET_S
    arrays, numbers, initial, tracks = _validate_data(data)
    context = _Context(data, arrays, numbers, initial, tracks, overall_deadline)
    with _single_numerical_thread():
        for model_name in MODEL_NAMES:
            model_started = time.monotonic()
            if model_started >= overall_deadline:
                receipt = _failure_receipt(
                    context,
                    model_name,
                    "limit_reached",
                    _LimitReached("whole-scan wall-clock budget reached before model start"),
                )
                receipt["attempted"] = False
            else:
                deadline = min(overall_deadline, model_started + MODEL_BUDGET_S[model_name])
                try:
                    receipt = _dispatch(context, model_name, deadline)
                except _NoAnchors as error:
                    receipt = _failure_receipt(context, model_name, "no_anchors", error)
                except _LimitReached as error:
                    receipt = _failure_receipt(context, model_name, "limit_reached", error)
                except Exception as error:
                    receipt = _failure_receipt(context, model_name, "error", error)
                receipt["attempted"] = True
            normalized = _normalize_receipt(model_name, receipt, time.monotonic() - model_started)
            context.results[model_name] = normalized
            if checkpoint is not None:
                checkpoint(dict(context.results))
    return context.results
