"""Compare a supplied region with an unrestricted local Doppler location."""

from collections import defaultdict
from itertools import product
from unittest.mock import patch

import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr

from tools.pipeline_eval.variants import (
    orbit_projector,
    portable_gate,
    portable_gate_coverage,
    portable_v5,
)

METHOD = "tile_region_support"
BOUNDARY = "Portable compact v5 after conditional held support for the tile interior"
SIGMA = portable_v5.TRACK_CONFIG["noise_sigma_hz"]
ALIAS_PERIOD = portable_v5.TRACK_CONFIG["alias_spacing_hz"]
MASS = 0.95
RADIUS_WIDTHS = 5


def tile_mass_lower_bound(point, covariance, radius):
    """Union bound on the conditional Gaussian mass inside a square."""
    standard = np.sqrt(np.diag(covariance))
    if not np.isfinite(standard).all() or np.any(standard <= 0):
        return 0.0
    tails = ndtr((-radius - point) / standard) + ndtr((point - radius) / standard)
    return float(max(0.0, 1 - sum(tails)))


def seed_at(point, region, units, index, grid, prior, projector):
    """One orbit competes for each independent observed time-frequency arc."""
    lat, lon = region.latlon(point)
    if not (-90 < lat < 90 and -180 <= lon <= 180):
        return -np.inf, np.asarray(point), []
    f, elev, h = projector.evaluate(grid, lat, lon)
    total, choices = 0.0, []
    for lanes in units:
        costs = []
        for arc in lanes:
            ix = index[id(arc)]
            cost, _, _ = portable_gate.phase_profile(
                arc.train_y - f[:, ix] * arc.scale, h[:, ix] * arc.scale, prior, SIGMA
            )
            cost[elev[:, ix].min(axis=1) < 0] = np.inf
            costs.append(cost)
        average = np.mean(costs, axis=0)
        orbit = int(np.argmin(average))
        if average[orbit] <= (portable_gate.MAX_TRAIN_RMS_SIGMAS * SIGMA) ** 2:
            total += float(np.log1p((5 * SIGMA) ** 2 / (SIGMA**2 + average[orbit])))
            choices.append((orbit, lanes))
    return total, np.asarray(point), choices


def wide_seed(region, arcs, sky, projector):
    units = list(portable_gate_coverage.units(arcs))
    prior = np.clip(sky["phase_sigma_s"], 0.05, 2)
    t = np.unique(np.concatenate([a.train_time for a in arcs]))
    grid = orbit_projector.prepare(sky, t)
    index = {id(a): np.searchsorted(t, a.train_time) for a in arcs}

    def search(point):
        return seed_at(point, region, units, index, grid, prior, projector)

    offsets = np.arange(-RADIUS_WIDTHS, RADIUS_WIDTHS + 1) * region.width_km
    midpoints = (offsets[1:] + offsets[:-1]) / 2
    found = max(
        map(search, (*product(offsets, repeat=2), *product(midpoints, repeat=2))),
        key=lambda r: r[0],
    )
    limit = RADIUS_WIDTHS * region.width_km
    for step in (
        region.width_km / 2,
        region.width_km / 4,
        region.width_km / 8,
        region.width_km / 16,
    ):
        points = [
            np.clip(found[1] + (x, y), -limit, limit)
            for x, y in product((-step, 0, step), repeat=2)
        ]
        found = max(map(search, points), key=lambda r: r[0])
    return found, units


class FixedOrbitModel:
    """Fit shared orbital phases and independent lane intercepts on training alone."""

    def __init__(self, choices, sky, region, projector):
        physical = sorted({j for j, _ in choices})
        lookup = {j: i for i, j in enumerate(physical)}
        self.orbits = physical
        self.region = region
        self.projector = projector
        self.arcs = [(lookup[j], a, 1 / len(lanes)) for j, lanes in choices for a in lanes]
        limited = {k: sky[k][physical] for k in ("position_km", "velocity_km_s")}
        limited["time_s"] = sky["time_s"]
        times = np.unique(np.concatenate([a.train_time for _, a, _ in self.arcs]))
        self.training_grid = orbit_projector.prepare(limited, times)
        held = np.unique(np.concatenate([a.held_time for _, a, _ in self.arcs]))
        self.held_grid = orbit_projector.prepare(limited, held)
        self.train_index = [np.searchsorted(times, a.train_time) for _, a, _ in self.arcs]
        self.held_index = [np.searchsorted(held, a.held_time) for _, a, _ in self.arcs]
        self.prior = np.clip(sky["phase_sigma_s"][physical], 0.05, 2)

    def estimate(self, point, omitted):
        f, elevation, h = self.projector.evaluate(self.training_grid, *self.region.latlon(point))
        information = (SIGMA / self.prior) ** 2
        response = np.zeros_like(information)
        raw = []
        for (j, arc, weight), ix in zip(self.arcs, self.train_index, strict=True):
            y = arc.train_y - f[j, ix] * arc.scale
            x = h[j, ix] * arc.scale
            yy, xx = y - y.mean(), x - x.mean()
            raw.append((y, x))
            if j != omitted:
                information[j] += weight * np.mean(xx**2)
                response[j] += weight * np.mean(xx * yy)
        phase = np.clip(response / information, -2, 2)
        alpha = np.array(
            [(y - phase[j] * x).mean() for (j, _, _), (y, x) in zip(self.arcs, raw, strict=True)]
        )
        residual = [
            np.r_[
                ((y - phase[j] * x - bias) / SIGMA) * np.sqrt(weight / len(ix)),
                np.minimum(elevation[j, ix], 0) * np.sqrt(weight / len(ix)),
            ]
            for (j, _, weight), ix, (y, x), bias in zip(
                self.arcs, self.train_index, raw, alpha, strict=True
            )
            if j != omitted
        ]
        err = np.concatenate([*residual, phase / self.prior])
        return err, alpha, phase

    def fit(self, start, lo, hi, omitted=None):
        return least_squares(
            lambda point: self.estimate(point, omitted)[0],
            np.clip(start, lo, hi),
            bounds=(lo, hi),
            loss="soft_l1",
            max_nfev=32,
        )

    def held(self, point):
        _, offset, phase = self.estimate(point, None)
        f, elevation, h = self.projector.evaluate(self.held_grid, *self.region.latlon(point))
        score = defaultdict(list)
        residuals = []
        for (j, a, weight), ids, bias in zip(self.arcs, self.held_index, offset, strict=True):
            z = portable_gate.wrap(a.held_y - (f[j, ids] + phase[j] * h[j, ids]) * a.scale - bias)
            ratio = ALIAS_PERIOD / (np.sqrt(2 * np.pi) * SIGMA) * np.exp(-0.5 * (z / SIGMA) ** 2)
            ratio[elevation[j, ids] < 0] = 0
            score[j].append((weight, float(np.mean(np.log(0.2 + 0.8 * ratio)))))
            residuals.append(z)
        log_score = np.array(
            [
                np.average([v for _, v in score[j]], weights=[w for w, _ in score[j]])
                for j in range(len(self.orbits))
            ]
        )
        return log_score, float(np.sqrt(np.mean(np.concatenate(residuals) ** 2)))


def exterior(model, start, radius, limit):
    """Identical model and data, with the site constrained to each exterior face."""
    options = []
    for axis in range(2):
        for sign in (-1, 1):
            lo, hi = np.full(2, -limit), np.full(2, limit)
            if sign > 0:
                lo[axis] = radius
            else:
                hi[axis] = -radius
            options.append(model.fit(start, lo, hi))
    return min(options, key=lambda fit: fit.cost)


def stable_held_difference(delta):
    # A single contested emitter must not determine the sign of the region comparison.
    return float((np.sum(delta) - np.max(delta)) / (len(delta) - 1))


def evidence(document, prepared, region, projector):
    arcs, metrics = portable_gate.make_arcs(document)
    metrics["validation_arcs"] = len(arcs)
    sky = prepared["sky"]["bank"]
    limit = region.width_km * RADIUS_WIDTHS
    if len(arcs) < portable_gate.MIN_FAMILIES:
        return False, dict(metrics, support_status="too few independent arcs")
    # Restrict this tangent-plane experiment to continuous local coordinates.
    for xy in product((-limit, limit), repeat=2):
        lat, lon = region.latlon(xy)
        if not (-90 < lat < 90 and -180 <= lon <= 180):
            return False, dict(metrics, support_status="local search crosses geographic seam")

    (train_score, seed, labels), units = wide_seed(region, arcs, sky, projector)
    metrics.update(
        assigned_units=len(labels), held_arc_units=len(units), seed_local_km=seed.tolist()
    )
    if len({j for j, _ in labels}) < portable_gate.MIN_FAMILIES:
        return False, dict(metrics, support_status="too few distinct fitted orbits")
    radius = region.half_width_km
    model = FixedOrbitModel(labels, sky, region, projector)
    free = model.fit(seed, [-limit, -limit], [limit, limit])
    inside = model.fit(free.x, [-radius, -radius], [radius, radius])
    outside = exterior(model, free.x, radius, limit)
    conditional_information = free.jac.T @ free.jac
    if np.linalg.matrix_rank(conditional_information) < 2:
        return False, dict(metrics, support_status="singular local displacement information")
    drop = np.array(
        [model.fit(free.x, [-limit, -limit], [limit, limit], j).x for j in range(len(model.orbits))]
    )
    centered = drop - drop.mean(axis=0)
    covariance = (
        np.linalg.inv(conditional_information) + (len(drop) - 1) / len(drop) * centered.T @ centered
    )
    mass = tile_mass_lower_bound(free.x, covariance, radius)
    in_score, in_rms = model.held(inside.x)
    out_score, out_rms = model.held(outside.x)
    delta = in_score - out_score
    stability = stable_held_difference(delta)
    admitted = mass >= MASS and stability > 0 and float(np.mean(in_score)) > 0
    return admitted, dict(
        metrics,
        support_status="inside supported" if admitted else "tile ambiguous or exterior supported",
        free_local_km=free.x.tolist(),
        inside_local_km=inside.x.tolist(),
        exterior_local_km=outside.x.tolist(),
        conditional_tile_mass_lower=mass,
        conditional_sigma_km=np.sqrt(np.diag(covariance)).tolist(),
        max_delete_orbit_shift_km=float(np.max(np.linalg.norm(drop - free.x, axis=1))),
        held_interior_hz=in_rms,
        held_exterior_hz=out_rms,
        held_log_gain=float(np.mean(delta)),
        worst_delete_orbit_held_gain=stability,
        matched_orbits=len(model.orbits),
        train_score=train_score,
    )


def run(document, *, tile, archive, bound, library):
    with patch.object(portable_gate, "evidence", evidence):
        result = portable_gate.run(
            document, tile=tile, archive=archive, bound=bound, library=library
        )
    result["boundary"] = BOUNDARY
    return result
