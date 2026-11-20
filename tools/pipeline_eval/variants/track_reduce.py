"""Thin measured CFO tracks before calling the frozen blind regional receiver.

Compression depends only on observed CFO and sample times. Both calibration
arms use the same solve because a constant RF-dependent offset cancels within
each fixed-RF track, in both the interpolation test and the receiver score.
"""

import json
import math
from collections import Counter
from itertools import pairwise
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from tools.pipeline_eval.reference import receiver

BOUNDARY = "decoded CFO tracks through frozen blind regional position and withholding"
# A quarter of the shape noise scale and two fine orbital knot intervals.
MAX_ERROR_HZ = 45.0
MAX_INTERPOLATION_S = 10.0
MIN_POINTS = 4
SCORE_POINT_CAP = receiver.grid.SAMPLES_PER_TRACK


def _track_samples(record, duration):
    try:
        times = np.asarray(record["times"], dtype=float)
        values = np.asarray(record["values"], dtype=float)
        rf_hz = float(record["rf_hz"])
        receiver_id, channel = record["receiver"], record["channel"]
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if (
        times.ndim != 1
        or times.shape != values.shape
        or len(times) < MIN_POINTS
        or not np.isfinite(times).all()
        or not np.isfinite(values).all()
        or not math.isfinite(rf_hz)
        or rf_hz <= 0
        or not isinstance(receiver_id, (str, int))
        or not isinstance(channel, (str, int))
    ):
        return None
    intervals = np.diff(times)
    if (intervals < 0).any():
        order = times.argsort()
        times, values = times[order], values[order]
        intervals = np.diff(times)
    if not 0 <= times[0] < times[-1] <= duration or (intervals <= 0).any():
        return None
    return times, values


def _knots(times, values):
    # Seed the minimum number of points before testing the interpolation bound.
    keep = set(np.rint(np.linspace(0, len(times) - 1, MIN_POINTS)).astype(int).tolist())
    todo = list(pairwise(sorted(keep)))
    limit = min(len(times), SCORE_POINT_CAP)
    if len(keep) >= limit:
        return None
    relative_hz = values - values[0]
    max_error = max_span = 0.0
    while todo:
        first, last = todo.pop()
        if last - first <= 1:
            continue
        offsets_s = times[first + 1 : last] - times[first]
        span = times[last] - times[first]
        if span > MAX_INTERPOLATION_S:
            split = first + 1 + int(np.argmin(np.abs(offsets_s - span / 2)))
        else:
            slope_delta_hz = relative_hz[last] - relative_hz[first]
            predicted = relative_hz[first] + slope_delta_hz * (offsets_s / span)
            errors = np.abs(relative_hz[first + 1 : last] - predicted)
            worst = int(np.argmax(errors))
            error = float(errors[worst])
            if error <= MAX_ERROR_HZ:
                max_error, max_span = max(max_error, error), max(max_span, float(span))
                continue
            split = first + 1 + worst
        keep.add(split)
        if len(keep) >= limit:
            # The receiver would resample a larger representation and drop bounded knots.
            return None
        todo.extend(((first, split), (split, last)))
    return sorted(keep), max_error, max_span


def _reduce(observation):
    """Return an observation and row counts before the receiver's track and sky selection."""
    records = observation["tracks"]
    samples = [_track_samples(record, observation["duration_s"]) for record in records]
    spans = [None if data is None else float(data[0][-1] - data[0][0]) for data in samples]
    span_counts = Counter(spans)
    reduced = list(records)
    metrics = dict(
        original_rows=0,
        reduced_rows=0,
        original_rows_with_solver_cap=0,
        reduced_rows_with_solver_cap=0,
        tracks_reduced=0,
        max_reconstruction_error_hz=0.0,
        max_reconstructed_span_s=0.0,
    )
    for i, (record, data, span) in enumerate(zip(records, samples, spans, strict=True)):
        if data is None:
            continue
        times, values = data
        count = len(times)
        # Equal-span tracks use their samples to break ties for the receiver's track cap.
        knots = _knots(times, values) if span_counts[span] == 1 else None
        if knots is not None:
            kept, error, interpolation_span = knots
            reduced[i] = dict(record, times=times[kept].tolist(), values=values[kept].tolist())
            count = len(kept)
            metrics["tracks_reduced"] += 1
            metrics["max_reconstruction_error_hz"] = max(
                error, metrics["max_reconstruction_error_hz"]
            )
            metrics["max_reconstructed_span_s"] = max(
                interpolation_span, metrics["max_reconstructed_span_s"]
            )
        metrics["original_rows"] += len(times)
        metrics["reduced_rows"] += count
        metrics["original_rows_with_solver_cap"] += min(len(times), SCORE_POINT_CAP)
        metrics["reduced_rows_with_solver_cap"] += min(count, SCORE_POINT_CAP)
    return dict(observation, tracks=reduced), metrics


def _arms(result):
    estimate = {"latlon": result["latlon"], "forced_latlon": result["best_latlon"]}
    pooled = result["diagnostics"].get("position_evidence", {}).get("pooled")
    if pooled is not None and pooled["rms_hz"] is not None:
        estimate["rf_rms_hz"] = pooled["rms_hz"]
    return {"c0": estimate, "fitted_c": dict(estimate)}


def run(case: dict, work_dir: Path) -> dict:
    """Compare original and shortened observations using the same measured receiver call."""
    paths = case.get("observation_path"), case.get("catalog_path")
    if not all(paths) or not all(Path(path).is_file() for path in paths):
        return dict(
            status="unavailable",
            reason="missing_observation_or_catalog",
            boundary=BOUNDARY,
            metrics={},
        )
    observation_path, catalog_path = map(Path, paths)
    try:
        observation = json.loads(observation_path.read_bytes())
        catalog = catalog_path.read_bytes()
        duration = float(observation["duration_s"])
        tracks = observation["tracks"]
        if not math.isfinite(duration) or duration <= 0 or not isinstance(tracks, list):
            raise ValueError("invalid duration or track list")
    except (KeyError, OSError, OverflowError, TypeError, ValueError) as error:
        return dict(status="unavailable", reason=str(error), boundary=BOUNDARY, metrics={})
    observation["duration_s"] = duration
    regions = case.get("regions", [])

    metrics = dict(
        reconstruction_bound_hz=MAX_ERROR_HZ,
        interpolation_span_bound_s=MAX_INTERPOLATION_S,
        calibration_invariant=True,
    )
    results = {}
    order = ("control", "candidate")
    # Balance first-call runtime effects across cases using the opaque ID.
    if sum(case.get("id", "").encode()) % 2:
        order = order[::-1]
    for name in order:
        started, cpu_started = perf_counter(), process_time()
        inputs = observation
        if name == "candidate":
            inputs, counts = _reduce(observation)
            metrics.update(counts, reduction_s=perf_counter() - started)
        result = receiver.solve(inputs, regions, catalog)
        metrics[f"{name}_s"] = perf_counter() - started
        metrics[f"{name}_cpu_s"] = process_time() - cpu_started
        results[name] = result
        metrics[f"{name}_status"] = result["status"]
        metrics[f"{name}_reason"] = result["reason"]
        metrics[f"{name}_region_id"] = result["region_id"]
        diagnostics = result["diagnostics"]
        for key, count in diagnostics.get("track_counts", {}).items():
            metrics[f"{name}_{key}_tracks"] = count
        for key, count in diagnostics["work"].items():
            metrics[f"{name}_{key}"] = count
        for key, seconds in diagnostics["stage_seconds"].items():
            metrics[f"{name}_{key}_s"] = seconds

    control, candidate = results["control"], results["candidate"]
    return dict(
        status="ok" if candidate["status"] == "fix" else "withheld",
        reason=candidate["reason"],
        boundary=BOUNDARY,
        metrics=metrics,
        arms=_arms(candidate),
        control_arms=_arms(control),
    )
