"""Conditional Gaussian Jacobian diagnostic, not a calibrated position covariance."""

import numpy as np


def _summary(design, threshold):
    _, singular, right = np.linalg.svd(design, full_matrices=False)
    information = design.T @ design
    if len(singular) == 0:
        directions = np.eye(2)
    elif len(singular) == 1:
        first = right[0]
        directions = np.column_stack([first, [-first[1], first[0]]])
    else:
        directions = right.T
    singular = np.pad(singular, (0, 2 - len(singular)))
    return dict(
        information=information,
        singular_values=singular,
        right_directions=directions,
        rank=int(np.sum(singular > threshold)),
        rank_threshold=threshold,
    )


def diagnose(spatial, nuisance, weights, *, rtol=None, prior_information=None):
    """Return raw and nuisance-projected data information in physical coordinates.

    Spatial columns must already represent the caller's physical x/y units.
    Weights are finite nonnegative precisions. Relative SVD tolerance defaults to
    machine epsilon times max(n, nuisance columns, 2); all rank tests use that
    explicit tolerance against the corresponding *unprojected* design norm.
    Nonzero whitened nuisance columns are normalized to unit Euclidean norm
    before SVD, preserving their span under independent column rescaling.
    Directions are column vectors; their signs and repeated-eigenvalue bases are
    arbitrary. Priors are reported separately and do not alter data-only ranks.
    Optional prior_information is spatial-only additive information. It does
    not restore nuisance-prior constraints: free per-satellite timing columns
    can legitimately collapse data-only spatial information, even when the
    actual timing prior makes the operational model identifiable.
    """
    spatial = np.asarray(spatial, dtype=float)
    nuisance = np.asarray(nuisance, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if spatial.ndim != 2 or spatial.shape[1] != 2:
        raise ValueError("spatial must have shape (n, 2)")
    n = len(spatial)
    if nuisance.ndim != 2 or len(nuisance) != n or weights.shape != (n,):
        raise ValueError("nuisance and weights must match spatial rows")
    if not all(np.isfinite(a).all() for a in (spatial, nuisance, weights)):
        raise ValueError("inputs must be finite")
    if np.any(weights < 0):
        raise ValueError("weights must be nonnegative")
    tolerance = np.finfo(float).eps * max(n, nuisance.shape[1], 2) if rtol is None else rtol
    if not np.isfinite(tolerance) or tolerance < 0 or tolerance >= 1:
        raise ValueError("rtol must be finite in [0, 1)")
    root = np.sqrt(weights)[:, None]
    x, z = root * spatial, root * nuisance
    # Max-first normalization avoids overflow/underflow from nuisance units.
    scales = np.max(np.abs(z), axis=0) if n else np.zeros(z.shape[1])
    nonzero = scales > 0
    normalized = z[:, nonzero] / scales[nonzero]
    normalized /= np.linalg.norm(normalized, axis=0)
    z = normalized
    if z.shape[1]:
        left, singular, _ = np.linalg.svd(z, full_matrices=False)
        nuisance_threshold = tolerance * (singular[0] if len(singular) else 0)
        basis = left[:, singular > nuisance_threshold]
    else:
        nuisance_threshold, basis = 0.0, np.empty((n, 0))
    residual = x - basis @ (basis.T @ x)
    norm = np.linalg.norm(x, ord=2) if n else 0.0
    threshold = tolerance * norm
    result = dict(
        scope="Data-only conditional Gaussian frequency-Jacobian information; "
        "not full mixture information or calibrated covariance",
        rtol=float(tolerance),
        positive_weight_rows=int(np.count_nonzero(weights)),
        nuisance_rank=basis.shape[1],
        nuisance_rank_threshold=float(nuisance_threshold),
        nuisance_scaling="Unit norm of each nonzero whitened column, max-first normalization",
        raw=_summary(x, threshold),
        projected=_summary(residual, threshold),
        prior_information=None,
        projected_plus_prior_information=None,
    )
    if prior_information is not None:
        prior = np.asarray(prior_information, dtype=float)
        if prior.shape != (2, 2) or not np.isfinite(prior).all():
            raise ValueError("prior_information must be a finite 2x2 matrix")
        if not np.allclose(prior, prior.T, rtol=0, atol=1e-12):
            raise ValueError("prior_information must be symmetric")
        prior = (prior + prior.T) / 2
        if np.linalg.eigvalsh(prior).min() < 0:
            raise ValueError("prior_information must be positive semidefinite")
        result["prior_information"] = prior.copy()
        result["projected_plus_prior_information"] = result["projected"]["information"] + prior
    return result


def streamed_diagnose(spatial, nuisance, weights, *, chunk_rows=4096, rtol=None):
    """Gram-preserving thin QR; O(chunk_rows*P + P**2) additional workspace.

    Globally normalize whitened nuisance columns before compression. Rank
    tolerance uses original row count, never compressed factor row count.
    """
    spatial, nuisance, weights = (np.asarray(x, float) for x in (spatial, nuisance, weights))
    if spatial.ndim != 2 or spatial.shape[1] != 2 or nuisance.ndim != 2:
        raise ValueError("spatial/nuisance matrices required")
    n, p = len(spatial), nuisance.shape[1]
    if len(nuisance) != n or weights.shape != (n,) or chunk_rows <= 0:
        raise ValueError("matching rows and positive chunk_rows required")
    if not all(np.isfinite(x).all() for x in (spatial, nuisance, weights)) or np.any(weights < 0):
        raise ValueError("finite inputs and nonnegative weights required")
    maximum = np.zeros(p)
    for start in range(0, n, chunk_rows):
        end = min(n, start + chunk_rows)
        block = nuisance[start:end] * np.sqrt(weights[start:end, None])
        maximum = np.maximum(maximum, np.max(np.abs(block), axis=0))
    nonzero = maximum > 0
    squared = np.zeros(p)
    for start in range(0, n, chunk_rows):
        end = min(n, start + chunk_rows)
        block = nuisance[start:end, nonzero] * np.sqrt(weights[start:end, None]) / maximum[nonzero]
        squared[nonzero] += np.sum(block**2, axis=0)
    factor = np.empty((0, 2 + np.count_nonzero(nonzero)))
    for start in range(0, n, chunk_rows):
        end = min(n, start + chunk_rows)
        root = np.sqrt(weights[start:end, None])
        block = np.column_stack(
            [
                spatial[start:end] * root,
                (nuisance[start:end, nonzero] / maximum[nonzero])
                * root
                / np.sqrt(squared[nonzero]),
            ]
        )
        factor = np.linalg.qr(np.vstack([factor, block]), mode="r")
    tolerance = np.finfo(float).eps * max(n, p, 2) if rtol is None else rtol
    result = diagnose(factor[:, :2], factor[:, 2:], np.ones(len(factor)), rtol=tolerance)
    result["positive_weight_rows"] = int(np.count_nonzero(weights))
    result["compression"] = dict(
        method="Streamed thin QR",
        original_rows=n,
        factor_rows=len(factor),
        chunk_rows=chunk_rows,
        original_nuisance_columns=p,
    )
    return result
