"""Prototype fixed quadratic prior for position-confounded slope modes."""

import numpy as np


def coupling(responsibilities, spatial_hz_per_km, times_s, centers_s, satellite_basis):
    """Conditional-mixture position/slope cross information at a hypothesis seed.

    This is a local diagnostic approximation, not the exact mixture Hessian.
    A common frequency-noise scale multiplies all entries and leaves its row space unchanged.
    No reference coordinates or errors are accepted. Freeze the result before optimizing.
    """
    weights = np.asarray(responsibilities, dtype=float)
    spatial = np.asarray(spatial_hz_per_km, dtype=float)
    times = np.asarray(times_s, dtype=float)
    centers = np.asarray(centers_s, dtype=float)
    basis = np.asarray(satellite_basis, dtype=float)
    if weights.ndim != 2:
        raise ValueError("Expected observation-by-satellite responsibilities")
    n, k = weights.shape
    if spatial.shape != (n, k, 2) or times.shape != (n,) or centers.shape != (k,):
        raise ValueError("Incompatible observation/satellite geometry shapes")
    if basis.shape != (k, max(k - 1, 0)):
        raise ValueError("Expected zero-sum satellite slope basis")
    if not all(np.isfinite(x).all() for x in (weights, spatial, times, centers, basis)):
        raise ValueError("Nonfinite geometry or responsibilities")
    if np.any(weights < 0) or np.any(weights.sum(axis=1) > 1 + 1e-8):
        raise ValueError("Invalid mixture responsibilities")
    if not np.allclose(basis.T @ basis, np.eye(basis.shape[1]), atol=1e-10, rtol=0):
        raise ValueError("Satellite basis must be orthonormal")
    if not np.allclose(basis.sum(axis=0), 0, atol=1e-10, rtol=0):
        raise ValueError("Satellite basis must exclude common slope")
    delta = (times[:, None] - centers[None, :]) / 100
    return np.einsum("nk,nki,nk,kd->id", weights, spatial, delta, basis)


def precision(cross_information, *, wide_sigma=0.5, protected_sigma=0.25, rank_rtol=1e-10):
    """Keep wide prior except at most two geometry-confounded coefficient modes.

    Clock coordinates represent Hz per100s; physical slopes divide them by100.
    Output is their quadratic precision, to replace only the satellite-slope block.
    """
    cross = np.asarray(cross_information, dtype=float)
    if cross.ndim != 2 or cross.shape[0] != 2 or not np.isfinite(cross).all():
        raise ValueError("Expected finite two-position-coordinate cross information")
    if not (np.isfinite(wide_sigma) and np.isfinite(protected_sigma)
            and 0 < protected_sigma <= wide_sigma and 0 < rank_rtol < 1):
        raise ValueError("Invalid Gaussian sigmas or rank tolerance")
    _, singular, vectors = np.linalg.svd(cross, full_matrices=False)
    rank = int(np.sum(singular > singular[0] * rank_rtol)) if len(singular) and singular[0] else 0
    directions = vectors[:rank]
    projector = directions.T @ directions
    loose = 1 / (100 * wide_sigma)**2
    tight = 1 / (100 * protected_sigma)**2
    matrix = loose * np.eye(cross.shape[1]) + (tight - loose) * projector
    return dict(precision=matrix, projector=projector, rank=rank, singular_values=singular)
