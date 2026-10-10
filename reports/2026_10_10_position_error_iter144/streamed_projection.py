"""Weighted target projections with bounded row-block workspace, no N-by-N matrix."""

import numpy as np


def _checked_blocks(factory, columns):
    for delta, spatial, nuisance, weights in factory():
        delta, spatial, nuisance, weights = (
            np.asarray(v, dtype=float) for v in (delta, spatial, nuisance, weights)
        )
        n = len(delta) if delta.ndim == 1 else -1
        if (
            n < 0
            or spatial.shape != (n, 2)
            or nuisance.shape != (n, columns)
            or weights.shape != (n,)
            or any(not np.isfinite(v).all() for v in (delta, spatial, nuisance, weights))
            or np.any(weights < 0)
        ):
            raise ValueError("Finite matching rows and nonnegative weights required")
        if not n:
            continue
        root = np.sqrt(weights)
        design = np.column_stack((nuisance, spatial)) * root[:, None]
        target = delta * root
        if not np.isfinite(design).all() or not np.isfinite(target).all():
            raise ValueError("Whitening overflowed")
        yield delta, design, target, weights


def _span(design, tolerance):
    maximum = np.max(np.abs(design), axis=0, initial=0)
    keep = maximum > 0
    normalized = design[:, keep] / maximum[keep]
    normalized /= np.linalg.norm(normalized, axis=0)
    left, singular, _ = np.linalg.svd(normalized, full_matrices=False)
    threshold = tolerance * singular.max(initial=0)
    selected = singular > threshold
    return left[:, selected], dict(
        rank=int(selected.sum()),
        singular_values=singular.tolist(),
        rank_threshold=float(threshold),
        nonzero_columns=int(keep.sum()),
    )


def decompose_streamed(blocks_factory, *, nuisance_columns, original_row_count, rtol=None):
    """Three-pass, globally normalized augmented thin QR target decomposition.

    The repeatable callable yields (delta, spatial, nuisance, weights) row blocks.
    All passes must yield identical rows in identical order. Missing rows are omitted
    by the caller; original_row_count still fixes the dense reference rank tolerance.
    Workspace is O(block_rows*(P+3) + (P+3)**2), not O(N*P) or O(N**2).
    Priors/bounds are absent: these are free local derivative spans, not covariance.
    Ill-conditioned retained spans amplify floating-point differences from dense
    SVD; equivalence is mathematical, not bitwise or a guarantee near rank cutoffs.
    """
    if not callable(blocks_factory):
        raise ValueError("Repeatable blocks factory required")
    if isinstance(nuisance_columns, bool) or not isinstance(nuisance_columns, (int, np.integer)):
        raise ValueError("Nonnegative nuisance column count required")
    p = int(nuisance_columns)
    if p < 0:
        raise ValueError("Nonnegative nuisance column count required")
    if (
        isinstance(original_row_count, bool)
        or not isinstance(original_row_count, (int, np.integer))
        or original_row_count < 1
    ):
        raise ValueError("Positive original row count required")
    original = int(original_row_count)
    tolerance = np.finfo(float).eps * max(original, p + 2) if rtol is None else rtol
    if not np.isfinite(tolerance) or not 0 < tolerance < 1:
        raise ValueError("Invalid relative rank tolerance")
    maximum = np.zeros(p + 2)
    n = positive = blocks = 0
    total = unweighted = 0.0
    for delta, design, target, weights in _checked_blocks(blocks_factory, p):
        maximum = np.maximum(maximum, np.max(np.abs(design), axis=0))
        n += len(delta)
        blocks += 1
        positive += int(np.count_nonzero(weights))
        total += float(target @ target)
        unweighted += float(delta @ delta)
    if not n or original < n:
        raise ValueError("Original row count must cover nonempty retained rows")
    if not np.isfinite(total) or not np.isfinite(unweighted):
        raise ValueError("Energy overflowed")
    keep = maximum > 0
    squared = np.zeros(int(keep.sum()))
    second_rows = 0
    for delta, design, _, _ in _checked_blocks(blocks_factory, p):
        second_rows += len(delta)
        scaled = design[:, keep] / maximum[keep]
        squared += np.sum(scaled * scaled, axis=0)
    if second_rows != n or np.any(squared <= 0):
        raise ValueError("Blocks factory changed rows or nonzero columns")
    norms = np.sqrt(squared)
    factor = np.empty((0, len(norms) + 1))
    third_rows = 0
    for delta, design, target, _ in _checked_blocks(blocks_factory, p):
        third_rows += len(delta)
        block = np.column_stack((design[:, keep] / maximum[keep] / norms, target))
        factor = np.linalg.qr(np.vstack((factor, block)), mode="r")
    if third_rows != n:
        raise ValueError("Blocks factory changed row count")
    nuisance_count = int(keep[:p].sum())
    qn, rank_n = _span(factor[:, :nuisance_count], tolerance)
    qs, rank_s = _span(factor[:, :-1], tolerance)
    target = factor[:, -1]
    residual_n = target - qn @ (qn.T @ target)
    residual_all = target - qs @ (qs.T @ target)
    remaining_n = float(residual_n @ residual_n)
    outside = float(residual_all @ residual_all)
    roundoff = 128 * np.finfo(float).eps * max(1, total) * max(n, p + 2)
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
        original_row_count=original,
        retained_rows=n,
        positive_weight_rows=positive,
        unweighted_rms_hz=float(np.sqrt(unweighted / n)),
        scope="Free data-only local derivative spans; "
        "no bounded/prior absorption or covariance claim",
        compression=dict(
            method="Three-pass globally normalized augmented thin QR",
            blocks=blocks,
            factor_rows=len(factor),
            factor_columns=factor.shape[1],
        ),
    )


def streamed_decompose(
    delta_hz, spatial, nuisance, weights, *, chunk_rows=4096, original_row_count=None, rtol=None
):
    """Dense-backed convenience; use a factory to avoid full input materialization."""
    delta, spatial, nuisance, weights = (
        np.asarray(v, float) for v in (delta_hz, spatial, nuisance, weights)
    )
    if (
        isinstance(chunk_rows, bool)
        or not isinstance(chunk_rows, (int, np.integer))
        or chunk_rows < 1
        or nuisance.ndim != 2
        or delta.ndim != 1
    ):
        raise ValueError("Positive chunk size and matrix/vector inputs required")
    n = len(delta)
    if spatial.shape != (n, 2) or len(nuisance) != n or weights.shape != (n,):
        raise ValueError("Matching rows required")

    def blocks():
        for start in range(0, n, int(chunk_rows)):
            stop = start + int(chunk_rows)
            yield delta[start:stop], spatial[start:stop], nuisance[start:stop], weights[start:stop]

    return decompose_streamed(
        blocks,
        nuisance_columns=nuisance.shape[1],
        original_row_count=n if original_row_count is None else original_row_count,
        rtol=rtol,
    )
