"""Session-local anonymous Doppler likelihoods for a stationary receiver."""

from collections import Counter
from itertools import product
from types import SimpleNamespace

import numpy as np
from scipy.special import logsumexp

from ..reference import grid
from . import trackless_likelihood as rate

DRIFT_HZ_S = np.array([-35.0, 0.0, 35.0])
LOG_DRIFT_PRIOR = np.log([0.22, 0.56, 0.22])
MODES = ("synchronous", "time_shuffle")
OFFERS = {"containing": (0, 0), "near_missing": (20, 0), "far_missing": (50, 0)}
OFFSETS_KM = (-10, -5, 0, 5, 10)


def design(center):
    """Give all offers and controls the same geodetic likelihood candidate set."""
    sites, offers = {}, {}
    for label, (east, north) in OFFERS.items():
        points = [(east + x, north + y) for x, y in product(OFFSETS_KM, repeat=2)]
        for xy in points:
            sites[xy] = list(rate._offset(center, *xy))
        offers[label] = dict(center=sites[east, north], width_km=25, points=points)
    for xy in ((-50, 0), (0, -50), (0, 50)):
        sites[xy] = list(rate._offset(center, *xy))
    return sites, offers


def rate_advantage(predicted, visible, observed, keep, sigma, support, shift):
    """Log density ratio of the existing signal/clutter model versus uniform clutter."""
    residual = observed[None, :, :] - predicted[:, :, None] - shift[None, :, None]
    density = np.exp(-0.5 * (residual / sigma[None, :, None]) ** 2)
    mass = np.einsum("ijk,ij,jk->j", density, visible, keep, optimize=False)
    norm = visible.sum(axis=0) * keep.sum(axis=1) * sigma * np.sqrt(2 * np.pi)
    mass = np.divide(mass, norm, out=np.zeros_like(mass), where=norm > 0)
    return np.log(0.5 + 0.5 * mass * support)


def marginal(train, held):
    """Integrate one clock drift per receiver and use training to predict held blocks."""
    evidence = logsumexp(train + LOG_DRIFT_PRIOR, axis=-1)
    predictive = logsumexp(train + held + LOG_DRIFT_PRIOR, axis=-1) - evidence
    return evidence.sum(axis=0), predictive.sum(axis=0)


def profiles(capture, center):
    """Return geodetic score arrays with no truth, prior fittings, or satellite identities."""
    sites, _ = design(center)
    groups = {}
    for receiver in sorted({probe["receiver_id"] for probe in capture.probes}):
        probes = [p for p in capture.probes if p["receiver_id"] == receiver]
        port = SimpleNamespace(**(vars(capture) | {"probes": probes}))
        groups[receiver] = rate.slices(port)
    count = Counter(row.epoch for rows in groups.values() for row in rows)
    training = sum((epoch // 5) % 3 != 1 for epoch in count)
    held = len(count) - training
    if len(count) < 15 or len({epoch // 5 for epoch in count if (epoch // 5) % 3 == 1}) < 3:
        raise ValueError("insufficient independent epoch coverage")
    sky = grid.prepare_sky(capture, capture.catalog)
    bank = grid.make_tile(sky, center)
    shape = (len(groups), len(MODES), len(sites), len(DRIFT_HZ_S))
    train_clock, held_clock = np.zeros(shape), np.zeros(shape)
    outcomes = dict(zip(groups, range(len(groups)), strict=True))
    comparisons = 0
    for receiver, rows in groups.items():
        for start in range(0, len(rows), rate.BATCH):
            sub = rows[start : start + rate.BATCH]
            dt = np.array([row.t1 - row.t0 for row in sub])
            args = rate.observations(sub)
            train_weights = np.array(
                [((row.epoch // 5) % 3 != 1) / count[row.epoch] for row in sub]
            )
            held_weights = np.array([((row.epoch // 5) % 3 == 1) / count[row.epoch] for row in sub])
            # Convert absolute oscillator slope to each lane's reference-frequency scale.
            scale = args[-1] * dt / rate.PERIOD
            for mode, offset in enumerate((0, 73)):
                state = rate.geometry(bank, sub, capture.duration_s, offset)
                for site_id, site in enumerate(sites.values()):
                    projection, visible = rate.rates(state, site, dt)
                    comparisons += projection.size
                    for drift, slope in enumerate(DRIFT_HZ_S):
                        values = rate_advantage(projection, visible, *args, slope * scale)
                        index = outcomes[receiver], mode, site_id, drift
                        train_clock[index] += values @ train_weights
                        held_clock[index] += values @ held_weights
    train_score, held_score = marginal(train_clock, held_clock)
    return dict(
        cells=list(sites),
        train=train_score.tolist(),
        held=held_score.tolist(),
        receiver_count=len(groups),
        epochs=len(count),
        train_epochs=training,
        held_epochs=held,
        slices=sum(count.values()),
        endpoint_pairs=sum(len(row.rates) for rows in groups.values() for row in rows),
        orbit_count=bank.stats["fine_satellites"],
        exact_rate_evaluations=comparisons,
    )


def aggregate(records, key, mode=0):
    """Multiply independent session likelihoods by summing their site log evidence."""
    values = np.array([record[key][mode] for record in records], dtype=float)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError("aligned finite session score vectors are required")
    return values.sum(axis=0)
