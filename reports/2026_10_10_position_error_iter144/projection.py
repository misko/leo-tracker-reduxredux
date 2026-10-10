"""Dense synthetic reference decomposition; not a bounded real-data runner."""

import numpy as np


def _span(design, root, rtol):
    weighted = design * root[:, None]
    # Normalize before SVD so arbitrary nuisance units do not set numerical rank.
    maximum = np.max(abs(weighted), axis=0, initial=0)
    keep = maximum > 0
    normalized = weighted[:, keep] / maximum[keep]
    norm = np.linalg.norm(normalized, axis=0)
    normalized /= norm
    u, singular, _ = np.linalg.svd(normalized, full_matrices=False)
    threshold = rtol * singular.max(initial=0)
    retained = singular > threshold
    return u[:, retained], dict(
        rank=int(retained.sum()),
        singular_values=singular.tolist(),
        rank_threshold=float(threshold),
        nonzero_columns=int(keep.sum()),
    )


def decompose(delta_hz, spatial, nuisance, weights, *, rtol=None, original_row_count=None):
    delta, spatial, nuisance, weights = map(
        lambda x: np.asarray(x, float), (delta_hz, spatial, nuisance, weights)
    )
    n = len(delta) if delta.ndim == 1 else -1
    if (
        n < 1
        or spatial.shape != (n, 2)
        or nuisance.ndim != 2
        or len(nuisance) != n
        or weights.shape != (n,)
        or any(not np.isfinite(x).all() for x in (delta, spatial, nuisance, weights))
        or np.any(weights < 0)
    ):
        raise ValueError("Finite matching rows and nonnegative weights required")
    original = n if original_row_count is None else original_row_count
    if isinstance(original, bool) or not isinstance(original, (int, np.integer)) or original < n:
        raise ValueError("Original row count must be an integer covering retained rows")
    tolerance = np.finfo(float).eps * max(original, nuisance.shape[1] + 2) if rtol is None else rtol
    if not np.isfinite(tolerance) or not 0 < tolerance < 1:
        raise ValueError("Invalid relative rank tolerance")
    root = np.sqrt(weights)
    target = root * delta
    qn, rank_n = _span(nuisance, root, tolerance)
    qs, rank_s = _span(np.column_stack([nuisance, spatial]), root, tolerance)
    residual_n = target - qn @ (qn.T @ target)
    residual_all = target - qs @ (qs.T @ target)
    total = float(target @ target)
    remaining_n = float(residual_n @ residual_n)
    outside = float(residual_all @ residual_all)
    roundoff = 128 * np.finfo(float).eps * max(1, total) * max(n, nuisance.shape[1] + 2)
    if remaining_n > total + roundoff or outside > remaining_n + roundoff:
        raise ValueError("Projection ranks do not yield nested energy decomposition")
    return dict(
        total_weighted_energy=total,
        nuisance_energy=max(0.0, total - remaining_n),
        spatial_conditional_energy=max(0.0, remaining_n - outside),
        outside_energy=outside,
        nuisance_span=rank_n,
        combined_span=rank_s,
        rtol=float(tolerance),
        original_row_count=int(original),
        retained_rows=n,
        positive_weight_rows=int(np.count_nonzero(weights)),
        unweighted_rms_hz=float(np.sqrt(np.mean(delta**2))),
        scope="Free data-only local derivative spans; "
        "no bounded/prior absorption or covariance claim",
    )
