"""Frequency-normalized curvature localization from anonymous beacon tracks."""

from dataclasses import dataclass
from time import perf_counter

import numpy as np

from tools.pipeline_eval.qualification import physical_transfer_solver as reference

TRAIN = 6
SAMPLES = 9
SCALE = 1500 / 11_325_000_000
BOUNDARY = "Prepared measured anonymous beacon curves and causal orbits through position"


def curvature_basis(times):
    """An orthonormal basis for the subspace orthogonal to constant and drift."""
    t = np.asarray(times, dtype=float)
    if t.ndim != 1 or len(t) < 3 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("curvature needs finite, strictly increasing source times")
    plane = np.column_stack((np.ones_like(t), (t - t.mean()) / np.ptp(t)))
    orthogonal, _ = np.linalg.qr(plane, mode="complete")
    return orthogonal[:, 2:]


@dataclass(frozen=True)
class Curvature:
    arc: reference.Arc
    training: np.ndarray
    held: np.ndarray


def _prepare(observation, catalogue):
    if observation["catalog_timestamp_ns"] > observation["cutoff_utc_ns"]:
        raise ValueError("orbit catalogue arrived after the acquisition cutoff")
    if not observation["tracks"]:
        return [], 0
    records = [row for row in observation["tracks"] if len(row["times"]) >= SAMPLES]
    arcs, n_orbits = reference.prepare(dict(observation, tracks=records), catalogue)
    outputs = []
    for arc, track in zip(arcs, records, strict=True):
        times = np.asarray(track["times"], float)
        index = np.rint(np.linspace(0, len(times) - 1, SAMPLES)).astype(int)
        times = times[index]
        outputs.append(
            Curvature(arc, curvature_basis(times[:TRAIN]), curvature_basis(times[TRAIN:]))
        )
    return outputs, n_orbits


def curvature_loss(residual, basis):
    return np.mean((residual @ basis / SCALE) ** 2, axis=-1)


def _scores(curve, xyz, up):
    arc = curve.arc
    extent = np.linalg.norm(arc.position[:, TRAIN // 2], axis=1).max(initial=6370)
    horizon = 2 * np.sin(0.5 * np.arccos(6350 / extent))
    candidates = arc.sky.query_ball_point(up, horizon, return_sorted=False)
    counts = np.fromiter(map(len, candidates), dtype=int, count=len(candidates))
    train = np.full(len(counts), np.inf)
    held = np.full_like(train, np.inf)
    orbits = np.full(len(counts), -1)
    if not counts.any():
        return train, held, orbits
    sites = np.repeat(np.arange(len(counts)), counts)
    sats = np.concatenate(candidates).astype(int, copy=False)
    delta = arc.position[sats] - xyz[sites, None]
    distance = np.linalg.norm(delta, axis=-1)
    above = np.einsum("nsi,ni->ns", delta, up[sites]) > 0
    residual = arc.frequency / arc.rf_hz + (
        np.einsum("nsi,nsi->ns", delta, arc.velocity[sats]) / (reference.LIGHT_KM_S * distance)
    )
    training = curvature_loss(residual[:, :TRAIN], curve.training)
    validation = curvature_loss(residual[:, TRAIN:], curve.held)
    training[~above[:, :TRAIN].all(axis=1)] = np.inf
    validation[~above[:, TRAIN:].all(axis=1)] = np.inf
    validation[~np.isfinite(training)] = np.inf
    offset = 0
    for row, count in enumerate(counts):
        if count:
            chosen = offset + np.argmin(training[offset : offset + count])
            train[row] = training[chosen]
            held[row] = validation[chosen]
            orbits[row] = arc.numbers[sats[chosen]]
            offset += count
    return train, held, orbits


def evaluate(curves, points):
    xyz, up = reference._xyz(points)
    results = []
    for start in range(0, len(points), 128):
        sl = slice(start, start + 128)
        trained, held, ids = map(
            np.stack, zip(*(_scores(a, xyz[sl], up[sl]) for a in curves), strict=True)
        )
        training = (1 / (1 + trained)).mean(axis=0)
        validation = (1 / (1 + held)).mean(axis=0)
        for i, (train, test) in enumerate(zip(training, validation, strict=True)):
            good = (trained[:, i] <= 1) & (held[:, i] <= 1)
            supported = len(set(ids[good, i]))
            rms = float(np.sqrt(held[good, i].mean()) * 1500) if good.any() else None
            results.append((float(train), float(test), supported, rms))
    return results


def search(curves, tile):
    if tile is None:
        indexes = np.arange(3600)
        initial = np.column_stack(
            (
                np.rad2deg(np.arcsin(1 - (2 * indexes + 1) / len(indexes))),
                (indexes * 137.50776405003785 + 180) % 360 - 180,
            )
        )
        steps, separation = (0.85, 0.25, 0.075, 0.0225), 250

        def inside(points):
            return points

    else:
        center, _ = reference._xyz([tile])
        steps, separation = (0.025, 0.008, 0.0025), 6

        def inside(points):
            xyz, _ = reference._xyz(points)
            return points[np.linalg.norm(xyz - center, axis=1) <= 12.5]

        initial = inside(reference._around(tile, 0.055))
    values = evaluate(curves, initial)
    count = len(initial)
    finalists = []
    for index in reference._best_sites(initial, np.array([r[0] for r in values]), separation):
        point, best = initial[index], values[index]
        finalists.append((point, best))
        for step in steps:
            local = inside(reference._around(point, step))
            fits = evaluate(curves, local)
            count += len(local)
            index = int(np.argmax([r[0] for r in fits]))
            if fits[index][0] > best[0]:
                point, best = local[index], fits[index]
        finalists.append((point, best))
    point, (train, held, orbits, rms) = max(finalists, key=lambda result: result[1][0])
    xyz, _ = reference._xyz([p for p, _ in finalists])
    winner, _ = reference._xyz([point])
    others = [
        v[1]
        for (_, v), d in zip(finalists, np.linalg.norm(xyz - winner, axis=1), strict=True)
        if d > separation
    ]
    return point.tolist(), dict(
        training_score=train,
        validation_score=held,
        validated_orbits=orbits,
        conditional_validation_rms_hz=rms,
        validation_lead=held - max(others) if others else None,
        evaluated_locations=count,
    )


def solve(observation, catalogue, *, tile=None):
    start = perf_counter()
    curves, count = _prepare(observation, catalogue)
    metrics = dict(
        tracks=len(observation["tracks"]),
        fitted_tracks=len(curves),
        causal_orbits=count,
        calibration_constant_cancels=True,
        affine_carrier_error_cancels=True,
    )
    point = None
    published = False
    if len(curves) >= 3:
        point, diagnostics = search(curves, tile)
        metrics.update(diagnostics)
        lead = diagnostics["validation_lead"]
        published = (
            diagnostics["validated_orbits"] >= 3
            and diagnostics["validation_score"] >= 0.35
            and (lead is not None and lead >= 0.08)
        )
    metrics["solver_wall_s"] = perf_counter() - start
    arm = dict(
        latlon=point if published else None,
        forced_latlon=point,
        rf_rms_hz=metrics.get("conditional_validation_rms_hz"),
    )
    return dict(
        status="ok" if published else "withheld",
        metrics=metrics,
        boundary=BOUNDARY,
        reason=None
        if published
        else "insufficient independent held orbit or separated site support",
        arms={"c0": arm, "fitted_c": dict(arm)},
    )
