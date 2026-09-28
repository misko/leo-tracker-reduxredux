"""Local training-likelihood curvature for position, timing and shared slope."""

from __future__ import annotations

import math

import ds7_fast_baseline_adapter as baseline
import numpy as np
from scipy.special import logsumexp


def evaluate(tracks, prediction, x):
    """Full-mixture profiled score/gradient and optimistic complete-data Fisher.

    Coordinates: east km, north km, timing seconds, native slope Hz/second.
    Fisher uses Student-t(4, scale=100 Hz) expected location information and
    training responsibilities, profiling each nominee's constant offset.
    It omits missing-label information and is not a calibrated covariance.
    """
    x = np.asarray(x, dtype=float)
    total, gradient, fisher = 0.0, np.zeros(4), np.zeros((4, 4))
    visibility = []
    for track in tracks:
        mask = track["mask"]
        predicted, visible = prediction(track, x[:3])
        column = 11_200_000_000 / float(track["rf_hz"]) * np.asarray(track["times_s"])
        residual = track["y"][None, :] - predicted - x[3] * column[None, :]
        scores, _, audits, offsets = baseline.profile(residual, mask)
        if not all(a["converged"] for a in audits):
            raise RuntimeError("offset stationarity failed")
        scores = np.where(visible, scores, -np.inf)
        normal = float(logsumexp(scores))
        if not math.isfinite(normal):
            raise ValueError("no visible nominee")
        weights = np.exp(scores - normal)
        total += normal - math.log(track["catalogue_size"])
        columns = []
        for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
            plus, minus = x[:3].copy(), x[:3].copy()
            plus[axis] += step
            minus[axis] -= step
            columns.append((prediction(track, plus)[0] - prediction(track, minus)[0]) / (2 * step))
        columns.append(np.broadcast_to(column, predicted.shape))
        design = np.stack(columns, axis=-1)[:, mask, :]
        centered = residual[:, mask] - offsets[:, None]
        influence = 5 * centered / (40000 + centered**2)
        gradient += np.einsum("k,kn,kna->a", weights, influence, design)
        # Expected location Fisher for t_nu is (nu+1)/((nu+3)*scale^2).
        precision = 5 / 7 / 10000
        sums = design.sum(axis=1)
        matrices = precision * np.einsum("kna,knb->kab", design, design)
        matrices -= (
            precision**2
            * np.einsum("ka,kb->kab", sums, sums)
            / (precision * int(mask.sum()) + 1e-12)
        )
        fisher += np.einsum("k,kab->ab", weights, matrices)
        visibility.append(visible.tolist())
    return {"score": total, "gradient": gradient, "fisher": fisher, "visibility": visibility}


def observed_hessian(evaluator, x, steps):
    """Negative score Hessian from the full profiled-mixture gradient."""
    columns, visibility = [], []
    for axis, step in enumerate(steps):
        plus, minus = np.array(x, dtype=float), np.array(x, dtype=float)
        plus[axis] += step
        minus[axis] -= step
        a, b = evaluator(plus), evaluator(minus)
        columns.append(-(a["gradient"] - b["gradient"]) / (2 * step))
        visibility.extend([a["visibility"], b["visibility"]])
    raw = np.stack(columns, axis=1)
    return raw, visibility


def position_information(matrix, nuisance):
    """Profile selected nuisance coordinates; refuse nonpositive nuisance blocks."""
    matrix = np.asarray(matrix)
    block = matrix[np.ix_(nuisance, nuisance)]
    if np.linalg.eigvalsh(block).min() <= 0:
        return None
    cross = matrix[np.ix_([0, 1], nuisance)]
    result = matrix[:2, :2] - cross @ np.linalg.solve(block, cross.T)
    return (result + result.T) / 2


def retention(matrix):
    """Information fractions after adding slope to timing as a nuisance."""
    fixed = position_information(matrix, [2])
    free = position_information(matrix, [2, 3])
    if fixed is None or free is None:
        return {"status": "nonpositive_nuisance_block"}
    values, vectors = np.linalg.eigh(fixed)
    if values.min() <= 0 or np.linalg.eigvalsh(free).min() <= 0:
        return {
            "status": "nonpositive_position_information",
            "fixed_slope": fixed.tolist(),
            "free_slope": free.tolist(),
        }
    inverse_root = (vectors / np.sqrt(values)) @ vectors.T
    ratios = np.linalg.eigvalsh(inverse_root @ free @ inverse_root)
    return {
        "status": "positive",
        "fixed_slope": fixed.tolist(),
        "free_slope": free.tolist(),
        "information_retention_eigenvalues": ratios.tolist(),
        "worst_direction_standard_error_inflation": float(1 / np.sqrt(ratios.min())),
    }
