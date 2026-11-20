"""Require held native Doppler support before running the portable v5 search."""

from collections import defaultdict
from dataclasses import dataclass
from importlib import import_module
from itertools import product
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import orbit_projector, portable_v5, v5_core, v5_lean

METHOD = "portable_gate"
BOUNDARY = "Portable compact v5 after out-of-sample native Doppler shape screening"
BLOCK_S = 12
DEVELOPMENT_S = 9
REFERENCE_RF = 11.5e9
COARSE_POINTS = 16
MAX_TRAIN_RMS_SIGMAS = 5
MAX_HELD_RMS_SIGMAS = 3
MIN_HELD_INLIER_FRACTION = 0.8
MIN_FAMILIES = 4
MIN_CHANNELS = 2
MIN_TIME_BINS = 3


def partition(observations):
    train, held = [], []
    for row in observations:
        elapsed = row["time_s"]
        (held if elapsed % BLOCK_S >= DEVELOPMENT_S else train).append(row)
    return train, held


def wrap(values):
    period = portable_v5.TRACK_CONFIG["alias_spacing_hz"]
    return (values + period / 2) % period - period / 2


@dataclass(frozen=True)
class Arc:
    channel: int
    scale: float
    time_bin: int
    train_time: np.ndarray
    train_y: np.ndarray
    held_time: np.ndarray
    held_y: np.ndarray


def make_arcs(document):
    from leo.analysis.localization_v3.tracks import (
        active_curvature,
        graph_tracks,
        winning_observations,
    )

    from leo.analysis.polynomial_tracklets import TrackConfig

    observations, _ = winning_observations(document)
    train, held = partition(observations)
    tracks, _ = graph_tracks(train, TrackConfig(**portable_v5.TRACK_CONFIG))
    lane = defaultdict(list)
    for row in held:
        lane[row["receiver"], row["channel"], row["actual_rf_hz"]].append(row)
    arcs = []
    for track in tracks:
        if not active_curvature(track):
            continue
        time = np.asarray(track["times"])
        take = np.rint(np.linspace(0, len(time) - 1, min(COARSE_POINTS, len(time)))).astype(int)
        use = [
            r
            for r in lane[track["receiver"], track["channel"], track["rf_hz"]]
            if time[0] <= r["time_s"] <= time[-1]
        ]
        if len(use) < 4 or len({int(r["time_s"] // BLOCK_S) for r in use}) < 2:
            continue
        arcs.append(
            Arc(
                track["channel"],
                track["rf_hz"] / REFERENCE_RF,
                int(np.median(time) // 60),
                time[take],
                np.asarray(track["values"])[take],
                np.asarray([r["time_s"] for r in use]),
                np.asarray([r["measured_cfo_hz"] for r in use]),
            )
        )
    return arcs, dict(development_observations=len(train), held_observations=len(held))


def phase_profile(residual, slope, prior_s, sigma):
    """Training-only centered Gaussian regression with one causal orbital phase."""
    level = residual.mean(axis=-1)
    bias_slope = slope.mean(axis=-1)
    x = slope - bias_slope[:, None]
    y = residual - level[:, None]
    phase = np.sum(x * y, axis=-1) / (np.sum(x**2, axis=-1) + (sigma / prior_s) ** 2)
    phase = np.clip(phase, -2, 2)
    cost = np.mean((y - x * phase[:, None]) ** 2, axis=-1)
    cost += (sigma * phase / prior_s) ** 2 / x.shape[1]
    return cost, level - bias_slope * phase, phase


def training_match(arcs, train_grid, train_ids, projector, prior, sigma, point, position):
    f, e, h = projector.evaluate(train_grid, *position)
    chosen, merits = [], defaultdict(float)
    for arc, idx in zip(arcs, train_ids, strict=True):
        residual = arc.train_y - f[:, idx] * arc.scale
        cost, level, phase = phase_profile(residual, h[:, idx] * arc.scale, prior, sigma)
        cost[e[:, idx].min(axis=1) < 0] = np.inf
        j = int(np.argmin(cost))
        if cost[j] >= (MAX_TRAIN_RMS_SIGMAS * sigma) ** 2:
            continue
        chosen.append((arc, j, float(level[j]), float(phase[j])))
        # Two antennas receiving one emitter cannot give that satellite two votes.
        merits[j] = max(merits[j], float(np.exp(-cost[j] / (8 * sigma**2))))
    return sum(merits.values()), point, chosen


def held_match(selected, bank, region, projector, sigma):
    _, point, rows = selected
    good, bins, channels = set(), set(), set()
    family_rms = defaultdict(list)
    total = 0
    for arc, j, offset, phase in rows:
        sky = {k: bank[k][[j]] for k in ("position_km", "velocity_km_s")}
        sky["time_s"] = bank["time_s"]
        grid = orbit_projector.prepare(sky, arc.held_time, phase)
        f, elev, _ = projector.evaluate(grid, *region.latlon(point))
        residual = wrap(arc.held_y - f[0] * arc.scale - offset)
        rms = float(np.sqrt(np.mean(np.minimum(abs(residual), 6 * sigma) ** 2)))
        family_rms[j].append(rms)
        total += len(residual)
        fraction = np.mean(abs(residual) <= MAX_HELD_RMS_SIGMAS * sigma)
        if fraction >= MIN_HELD_INLIER_FRACTION and elev.min() >= 0:
            good.add(j)
            channels.add(arc.channel)
            bins.add(arc.time_bin)
    medians = [float(np.median(value)) for value in family_rms.values()]
    return dict(
        good_families=len(good),
        good_channels=len(channels),
        good_time_bins=len(bins),
        assessed_families=len(medians),
        held_points=total,
        held_family_median_clipped_rms_hz=float(np.median(medians)) if medians else None,
        training_score=selected[0],
        gate_local_km=list(point),
    )


def admit(metrics):
    return (
        metrics["good_families"] >= MIN_FAMILIES
        and metrics["good_channels"] >= MIN_CHANNELS
        and metrics["good_time_bins"] >= MIN_TIME_BINS
    )


def evidence(document, prepared, region, projector):
    arcs, metrics = make_arcs(document)
    metrics["validation_arcs"] = len(arcs)
    if len(arcs) < MIN_FAMILIES:
        return False, metrics
    sky = prepared["sky"]["bank"]
    # Read the causal prior spread, but keep the evidence scale independent of held noise.
    sigma = portable_v5.TRACK_CONFIG["noise_sigma_hz"]
    prior = np.clip(sky["phase_sigma_s"], 0.05, 2)
    times = np.unique(np.concatenate([arc.train_time for arc in arcs]))
    grid = orbit_projector.prepare(sky, times)
    train_ids = [np.searchsorted(times, arc.train_time) for arc in arcs]

    def train(point):
        return training_match(
            arcs, grid, train_ids, projector, prior, sigma, point, region.latlon(point)
        )

    radius = region.half_width_km
    best = max(map(train, region.grid), key=lambda row: row[0])
    for step in (radius / 4, radius / 8):
        points = {
            tuple(np.clip(np.asarray(best[1]) + step * np.asarray(delta), -radius, radius))
            for delta in product((-1, 0, 1), repeat=2)
        }
        best = max(map(train, sorted(points)), key=lambda row: row[0])
    observed = held_match(best, sky, region, projector, sigma)
    return admit(observed), dict(metrics, **observed, gate_projection_calls=projector.calls)


def retain_only(module, operation):
    """Reuse the stable paired exclusion fit when the node and mask are unchanged."""
    original = module.fit_and_gate
    retained = None
    skipped = {}

    def fit(scan, node, keep, stage, *args, **kwargs):
        nonlocal retained
        if stage == "salvage_refit" and retained is not None:
            saved_node, fit_result = retained
            if node is saved_node and np.array_equal(keep, fit_result[1]):
                return (*fit_result[:3], [], fit_result[-1])
        result = original(scan, node, keep, stage, *args, **kwargs)
        if stage == "exclude_refit" and result[-1]:
            retained = (node, result)
        return result

    def retain(scan, node, keep, **kwargs):
        skipped["points_excluded_before_salvage"] = int(np.sum(~keep))
        return node, keep, []

    with patch.object(module, "fit_and_gate", fit), patch.object(module, "salvage", retain):
        result = operation()
    return result, skipped


def run(document, *, tile, archive, bound, library, screen_center=None):
    """Apply the same calibration-invariant gate before either original fit arm."""
    original = v5_core.infer

    def gate(prepared, region, numerical_bound, stage_s):
        if prepared["status"] != "inputs_prepared":
            return original(prepared, region, numerical_bound, stage_s)
        start = perf_counter()
        admitted, metrics = evidence(document, prepared, region, orbit_projector.Projector(library))
        stage_s["geographic_gate"] = perf_counter() - start
        if admitted:
            module = import_module("leo.analysis.localization_v3.conservative_recovery")
            result, skipped = retain_only(
                module, lambda: original(prepared, region, numerical_bound, stage_s)
            )
            result["metrics"]["bounded_recovery"] = skipped
        else:
            result = dict(
                status="withheld",
                reason="native held Doppler lacked independent regional support",
                metrics={"stage_s": stage_s},
                arms={a: {"latlon": None} for a in v5_lean.ARMS},
            )
        result["metrics"]["geographic_gate"] = dict(metrics, admitted=admitted)
        return result

    with patch.object(v5_core, "infer", gate):
        result = portable_v5.run(
            document,
            tile=tile,
            archive=archive,
            bound=bound,
            library=library,
            screen_center=screen_center,
        )
    result["boundary"] = BOUNDARY
    return result
