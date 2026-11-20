"""Optimistic site observability of actual simultaneous beacon frequencies."""

from dataclasses import dataclass
from itertools import product
from types import SimpleNamespace

import numpy as np

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from tools.pipeline_eval.reference import grid
from tools.pipeline_eval.scoring import ARMS

BOUNDARY = "Released measured beacon frequencies with author-assisted identities and causal TLE"
RF_HZ = 11_325_000_000
HALF_WIDTH_KM = 12.5
BLOCK_S = 4.0
BIN_SIGMA_HZ = (2_000_000 / 28_000) / np.sqrt(12.0)


@dataclass(frozen=True)
class Contrast:
    time_index: np.ndarray
    counts: np.ndarray
    arc_basis: np.ndarray
    rank: int

    def project(self, rows):
        value = _center_epochs(np.asarray(rows, float), self.time_index, self.counts)
        return value - (value @ self.arc_basis) @ self.arc_basis.T


def _center_epochs(values, time_index, counts):
    rows = np.atleast_2d(values)
    totals = np.zeros((len(rows), len(counts)))
    np.add.at(totals.T, time_index, rows.T)
    result = rows - (totals / counts)[:, time_index]
    return result.reshape(values.shape)


def contrast(arcs, times):
    """Orthogonal projection away from all epoch and arc DC nuisance terms."""
    _, time, counts = np.unique(times, return_inverse=True, return_counts=True)
    _, source = np.unique(arcs, return_inverse=True)
    if not len(time):
        return Contrast(time, counts, np.empty((0, 0)), 0)
    arc_matrix = np.eye(int(source.max()) + 1)[source].T
    data = _center_epochs(arc_matrix, time, counts).T
    basis, singular, _ = np.linalg.svd(data, full_matrices=False)
    rank = int(np.count_nonzero(singular > 1e-10))
    return Contrast(time, counts, basis[:, :rank], len(time) - len(counts) - rank)


def folded_split(times):
    return (np.floor(np.asarray(times) / BLOCK_S).astype(np.int64) % 2) == 0


def _state_rows(catalogue_text, observation, arc_index, time_index, times):
    cat = parse_element_sets(catalogue_text)
    labels = observation["arc_labels"]
    mapping = {}
    for index, name in enumerate(cat.names):
        mapping.setdefault(name, []).append(index)
    kept = np.unique(arc_index)
    if any(len(mapping.get(labels[i], ())) != 1 for i in kept):
        raise ValueError("a measured orbit label lacks a unique causal record")
    indices = [mapping[labels[i]][0] for i in kept]
    cutoff = observation["cutoff_utc_ns"]
    epochs = cat.element_epoch_utc_ns()
    if any(epochs[i] > cutoff for i in indices):
        raise ValueError("post-cutoff element in measured site query")
    utc = observation["anchor_utc_ns"] + np.rint(times * 1e9).astype(np.int64)
    sample = SamplingGrid(tuple(map(int, utc)), 0, 1.0)
    state = propagate_grid(cat, sample, indices=indices)
    jd, fraction = julian_day_from_utc_ns(utc)
    p, v = teme_to_ecef(state.position_teme_km, state.velocity_teme_km_s,
                       greenwich_mean_sidereal_time_rad(jd, fraction))
    rows = np.searchsorted(kept, arc_index)
    valid = state.error_code[rows, time_index] == 0
    if not valid.all():
        raise ValueError("author-labeled causal orbit failed at a measured epoch")
    return p[rows, time_index], v[rows, time_index], [cat.satellite_numbers[i] for i in indices]


def _predict(xy, tile, p, v):
    receiver, up, coordinates = grid._sites(tile, xy)
    delta = p - receiver[:, None, :]
    horizon = np.sum(delta * up[:, None, :], axis=-1) >= 0
    rates = np.sum(delta * v, axis=-1) / np.linalg.norm(delta, axis=-1)
    return -RF_HZ / grid.LIGHT_SPEED_KM_S * rates, horizon, coordinates


def _square(step):
    return np.asarray(list(product(np.arange(-HALF_WIDTH_KM, HALF_WIDTH_KM + 0.1, step), repeat=2)))


def solve(observation, catalogue, center):
    t, k, y = (np.asarray(observation[field]) for field in ("time_s", "arc_index", "frequency_hz"))
    if (
        t.ndim != 1 or t.shape != k.shape or t.shape != y.shape
        or not np.isfinite(t).all() or not np.isfinite(y).all()
        or (k.size and not np.issubdtype(k.dtype, np.integer)) or np.any(k < 0)
        or np.any(k >= len(observation["arc_labels"])) or np.any(t < 0)
        or np.any(t > observation["duration_s"])
        or observation["catalog_timestamp_ns"] > observation["cutoff_utc_ns"]
        or observation["cutoff_utc_ns"] > observation["anchor_utc_ns"]
    ):
        raise ValueError("invalid measured beacon support, timeline or causal archive")
    times, time_index = np.unique(t, return_inverse=True)
    train = folded_split(t)
    hold = ~train
    fit, check = contrast(k[train], t[train]), contrast(k[hold], t[hold])
    metrics = dict(exact_epoch_count=len(times), edges=len(t), training_rank=fit.rank,
                   held_rank=check.rank, rf_hz=RF_HZ, c_algebraically_absorbed=True)

    def diagnostic(reason, guess=None, rms=None):
        return dict(
            status="withheld", reason=reason, boundary=BOUNDARY, metrics=metrics,
            arms={arm: dict(latlon=None, forced_latlon=guess, rf_rms_hz=rms) for arm in ARMS},
        )

    if min(fit.rank, check.rank) < 2 or len(times) < 3:
        return diagnostic("insufficient clock-invariant contrasts")
    p, v, labels = _state_rows(catalogue, observation, k, time_index, times)
    metrics["causal_norads"] = labels
    lat, lon = center
    tile = SimpleNamespace(ecef_center_km=geodetic_to_ecef_km(lat, lon, 0.0),
                           enu_frame=ecef_to_enu_matrix(lat, lon))

    def loss(points):
        pred, visible, _ = _predict(points, tile, p[train], v[train])
        err = np.sum(fit.project(pred - y[train]) ** 2, axis=1) / fit.rank
        return np.where(visible.all(axis=1), err, np.inf)

    points = _square(2.5)
    losses = loss(points)
    if not np.isfinite(losses).any():
        return diagnostic("no geometry above horizon in the offered tile")
    best = points[np.argmin(losses)]
    for step in (1.0, 0.25):
        points = best + step * np.asarray(list(product((-1, 0, 1), repeat=2)))
        points = points[(abs(points) <= HALF_WIDTH_KM).all(axis=1)]
        best = points[np.argmin(loss(points))]
    pred, visible, label = _predict(best[None], tile, p, v)
    coords = label[0].tolist()
    metrics["training_rf_rms_hz"] = float(np.sqrt(loss(best[None])[0]))
    metrics["fit_east_north_km"] = best.tolist()
    if not visible[:, hold].all():
        return diagnostic("held orbit geometry below horizon", coords)
    rms = float(np.linalg.norm(check.project(pred[0, hold] - y[hold])) / np.sqrt(check.rank))
    offsets = np.r_[np.eye(2), -np.eye(2)] * 0.25
    shifted, _, _ = _predict(best + offsets, tile, p[hold], v[hold])
    gradient = check.project((shifted[:2] - shifted[2:]) / 0.5)
    singular = np.linalg.svd(gradient, compute_uv=False)
    metrics["held_rf_rms_hz"] = rms
    metrics["held_singular_hz_per_km"] = singular.tolist()
    weakest = float(singular[-1])
    metrics["quantization_only_worst_sd_km"] = BIN_SIGMA_HZ / weakest if weakest > 1e-8 else None
    return diagnostic("author-assisted orbit identity control", coords, rms)
