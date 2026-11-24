"""Conservative signed-frequency certificates for whole fixed-state catalogue blocks."""

from dataclasses import dataclass

import numpy as np


BLOCK = 16
NOISE = 150.
BIAS = 1000.
PERIOD = 1 / 4.4e-6
MAX_ABS_HZ = 2e6
# The largest contrast uses 16 binary64 frequencies and no non-dyadic weights.
# This margin exceeds their summed roundoff, including stock subtraction,
# integer native alias addition and Gaussian constant subtraction.
MARGIN_HZ = 1e-3


def sample_indices(count):
    if count < 4:
        return None
    per_quarter = 4 if count >= 16 else (2 if count >= 8 else 1)
    quarters = np.array_split(np.arange(count), 4)
    return np.concatenate([quarter[np.linspace(0, len(quarter)-1, per_quarter, dtype=int)] for quarter in quarters])


def contrasts(values):
    """Three disjoint-sign orthogonal projections, before length normalization."""
    a, b, c, d = np.moveaxis(values.reshape(*values.shape[:-1], 4, -1).sum(axis=-1), -1, 0)
    return np.stack(((a+b)-(c+d), (a-b)+(c-d), (a-b)-(c-d)), axis=-1)


def white_domain(observed):
    return all(np.isfinite(observed)) and np.max(np.abs(observed)) <= MAX_ABS_HZ


def box_distance(query, lo, hi, dimension):
    delta = np.maximum(np.maximum(lo-query, query-hi) - MARGIN_HZ, 0.)
    return (delta*delta).sum(axis=-1) / dimension


@dataclass(frozen=True)
class NominalBlocks:
    rows: np.ndarray
    starts: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    horizon: np.ndarray
    signed: np.ndarray
    sampled_visible: np.ndarray
    sampled: np.ndarray

    def repeated(self, values):
        return np.repeat(values, np.diff(np.r_[self.starts, len(self.rows)]))

    def lower(self, observed):
        return box_distance(contrasts(observed[self.sampled]), self.lo, self.hi, len(self.sampled))

    def horizon_excluded(self):
        return (self.horizon < 0.).any(axis=1)


def nominal_blocks(frequency, elevation, sampled):
    if (not np.isfinite(frequency).all() or not np.isfinite(elevation).all()
            or np.max(np.abs(frequency)) > MAX_ABS_HZ):
        return None
    signed = contrasts(frequency)
    rows = np.argsort(signed[:, 0], kind="stable")
    starts = np.arange(0, len(rows), BLOCK)
    lo = np.nextafter(np.minimum.reduceat(signed[rows], starts, axis=0), -np.inf)
    hi = np.nextafter(np.maximum.reduceat(signed[rows], starts, axis=0), np.inf)
    horizon = np.maximum.reduceat(elevation[rows], starts, axis=0)
    return NominalBlocks(rows, starts, lo, hi, horizon, signed, (elevation >= 0.).all(axis=1), sampled)


def reject_blocks(index, squared, cutoff, point_count):
    cost_necessary = squared > (cutoff * NOISE ** 2 + MARGIN_HZ)
    rms_necessary = squared > point_count * (450. + MARGIN_HZ) ** 2
    return index.horizon_excluded() | (cost_necessary & rms_necessary)


def independent_incumbent(index, squared, observed, shifted, full_frequency, full_elevation, columns, scale):
    """Attempt exactly one real row from the best eligible nominal block."""
    eligible = index.sampled_visible[index.rows] & ~shifted[index.rows]
    blocks = np.logical_or.reduceat(eligible, index.starts)
    if not blocks.any():
        return None, np.inf
    best = int(np.argmin(np.where(blocks, squared, np.inf)))
    start = index.starts[best]
    candidates = index.rows[start:start+BLOCK][eligible[start:start+BLOCK]]
    differences = index.signed[candidates] - contrasts(observed[index.sampled])
    row = int(candidates[np.argmin(np.sum(differences**2, axis=1))])
    if not np.all(full_elevation[row, columns] >= 0.):
        return row, np.inf
    frequency = scale * full_frequency[row, columns]
    if not white_domain(frequency):
        return row, np.inf
    raw = observed - frequency
    quotient = -raw.mean() / PERIOD
    if abs(quotient-np.floor(quotient)-.5) < 1e-8:
        return row, np.inf
    residual = raw + np.rint(quotient) * PERIOD
    information = len(raw) / NOISE**2
    bias = residual.sum() / NOISE**2 / (information + 1/BIAS**2)
    loss = np.sum(((residual-bias)/NOISE)**2) + (bias/BIAS)**2 + np.log1p(BIAS**2 * information)
    return row, loss + MARGIN_HZ


def exact_protected(visible, terms):
    if not len(visible) or not np.isfinite(terms["cost"]).all():
        return None, np.inf
    cutoff = np.min(terms["cost"], where=visible, initial=np.inf)
    protected = visible & (terms["passing"] | (terms["cost"] == cutoff))
    protected[0] = True
    return protected, cutoff
