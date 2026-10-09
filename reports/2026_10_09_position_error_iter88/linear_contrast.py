"""Small reference-free, background-projected receiver-contrast estimators."""

import time

import numpy as np


def _vector(value, name, length=None):
    value = np.asarray(value, dtype=float)
    if value.ndim != 1 or not np.isfinite(value).all():
        raise ValueError(f"{name} must be a finite vector")
    if length is not None and len(value) != length:
        raise ValueError(f"{name} length mismatch")
    return value


def _sigma(value):
    value = float(value)
    if not np.isfinite(value) or value < 0:
        raise ValueError("sigma_hz must be finite and nonnegative")
    return value


def _weights(value, length):
    value = np.ones(length) if value is None else _vector(value, "weights", length)
    if np.any(value <= 0):
        raise ValueError("weights must be strictly positive measurement precisions")
    return value


def _ids(value, name, length):
    value = _vector(value, name, length)
    if np.any(value != np.floor(value)) or np.any(value < 0):
        raise ValueError(f"{name} must contain nonnegative integers")
    if np.any(value > np.iinfo(np.int64).max):
        raise ValueError(f"{name} exceeds integer range")
    return value.astype(np.int64)


def _basis(count):
    """Deterministic orthonormal Helmert basis for the zero-sum subspace."""
    result = np.zeros((count, max(count - 1, 0)))
    for j in range(count - 1):
        scale = np.sqrt((j + 1) * (j + 2))
        result[: j + 1, j] = 1 / scale
        result[j + 1, j] = -(j + 1) / scale
    return result


def projected_ridge(y, design, background, weights, sigma_hz):
    """Solve weighted ridge after eliminating unpenalized background columns.

    Minimize ||sqrt(W)(y-B beta-Z theta)||^2 + ||theta||^2/sigma^2.
    A zero sigma locks theta to zero. No pair-count-square projector is formed.
    """
    begun = time.monotonic()
    y = _vector(y, "y")
    if not len(y):
        raise ValueError("at least one row required")
    weight = _weights(weights, len(y))
    sigma = _sigma(sigma_hz)
    design, background = np.asarray(design, float), np.asarray(background, float)
    for name, matrix in (("design", design), ("background", background)):
        if matrix.ndim != 2 or matrix.shape[0] != len(y) or not np.isfinite(matrix).all():
            raise ValueError(f"invalid {name} matrix")
    root = np.sqrt(weight)
    zw, bw, yw = root[:, None] * design, root[:, None] * background, root * y
    ub, sb, vtb = np.linalg.svd(bw, full_matrices=False)
    background_tolerance = 64 * np.finfo(float).eps * max(bw.shape) * (sb[0] if len(sb) else 0)
    rank_b = int(np.sum(sb > background_tolerance))
    q = ub[:, :rank_b]
    residual_y = yw - q @ (q.T @ yw)
    residual_z = zw - q @ (q.T @ zw)
    # Reference the original design: a wholly projected-away column must not
    # become "identified" merely because its roundoff residue has nonzero norm.
    tolerance = 64 * np.finfo(float).eps * max(zw.shape) * max(np.linalg.norm(zw), 1.0)
    u, singular, vt = np.linalg.svd(residual_z, full_matrices=False)
    keep = singular > tolerance
    rank_z = int(np.sum(keep))
    coefficients = np.zeros(design.shape[1])
    if sigma > 0 and rank_z:
        with np.errstate(over="ignore", divide="ignore"):
            inverse_sigma = np.divide(1.0, sigma)
        denominator = np.hypot(singular[keep], inverse_sigma)
        gain = (singular[keep] / denominator) / denominator
        coefficients = vt[keep].T @ (gain * (u[:, keep].T @ residual_y))
    remaining = yw - zw @ coefficients
    beta = np.zeros(background.shape[1])
    if rank_b:
        beta = vtb[:rank_b].T @ ((q.T @ remaining) / sb[:rank_b])
    # Report the data-null modes, including any unsampled coefficient dimensions.
    identified = vt[keep]
    if design.shape[1]:
        _, _, full_vt = np.linalg.svd(identified, full_matrices=True)
        weak_modes = full_vt[rank_z:].T
    else:
        weak_modes = np.zeros((0, 0))
    return dict(
        coefficients=coefficients,
        background_coefficients=beta,
        background_rank=rank_b,
        data_rank=rank_z,
        regularized_rank=design.shape[1] if sigma > 0 else 0,
        locked_dimensions=design.shape[1] if sigma == 0 else 0,
        singular_values=singular,
        weak_modes=weak_modes,
        rank_tolerance=float(tolerance),
        background_rank_tolerance=float(background_tolerance),
        residual_hz=y - background @ beta - design @ coefficients,
        dimensions=dict(rows=len(y), background=background.shape[1], contrast=design.shape[1]),
        elapsed_s=time.monotonic() - begun,
    )


def _prepare(pair_values_hz, satellite_indices, weights, minimum_pairs):
    values = _vector(pair_values_hz, "pair_values_hz")
    ids = _ids(satellite_indices, "satellite_indices", len(values))
    weight = _weights(weights, len(values))
    if isinstance(minimum_pairs, bool) or int(minimum_pairs) != minimum_pairs or minimum_pairs < 1:
        raise ValueError("minimum_pairs must be a positive integer")
    satellites, counts = np.unique(ids, return_counts=True)
    eligible = satellites[counts >= minimum_pairs]
    mask = np.isin(ids, eligible)
    return values, ids, weight, satellites, counts, eligible, mask


def fit_projected_contrasts(
    pair_values_hz, satellite_indices, time_s, channel, *, sigma_hz, weights=None, minimum_pairs=10
):
    """Estimate eligible satellite contrasts after common time/channel removal."""
    begun = time.monotonic()
    sigma = _sigma(sigma_hz)
    values, ids, weight, satellites, counts, eligible, mask = _prepare(
        pair_values_hz, satellite_indices, weights, minimum_pairs
    )
    times = _vector(time_s, "time_s", len(values))
    channels = _ids(channel, "channel", len(values))
    result = dict(
        satellite_ids=satellites,
        contrasts_hz=np.zeros(len(satellites)),
        pair_counts=counts,
        eligible_satellite_ids=eligible,
        no_op=len(eligible) < 2 or sigma == 0,
        sigma_hz=sigma,
        minimum_pairs=int(minimum_pairs),
        weights_policy="unit precision (1/Hz^2)"
        if weights is None
        else "supplied precision (1/Hz^2)",
        input_pairs=len(values),
        used_pairs=int(mask.sum()) if len(eligible) >= 2 else 0,
        omitted_pairs=int((~mask).sum()) if len(eligible) >= 2 else len(values),
    )
    if len(eligible) < 2:
        result.update(
            background_coefficients=np.zeros(0),
            background_columns=[],
            background_rank=0,
            data_rank=0,
            regularized_rank=0,
            weak_modes=np.zeros((len(eligible), 0)),
            singular_values=np.zeros(0),
            dimensions=dict(rows=0, background=0, contrast=0),
            elapsed_s=time.monotonic() - begun,
        )
        return result
    values, ids, weight, times, channels = (x[mask] for x in (values, ids, weight, times, channels))
    time_center = float(np.average(times, weights=weight))
    centered = times - time_center
    time_scale = max(float(np.max(np.abs(centered))), 1.0)
    channel_ids = np.unique(channels)
    background = np.column_stack(
        [np.ones(len(values)), centered / time_scale]
        + [(channels == item).astype(float) for item in channel_ids[1:]]
    )
    basis = _basis(len(eligible))
    design = basis[np.searchsorted(eligible, ids)]
    fitted = projected_ridge(values, design, background, weight, sigma)
    contrast = basis @ fitted["coefficients"]
    result["contrasts_hz"][np.searchsorted(satellites, eligible)] = contrast
    result.update(fitted)
    result.update(
        background_columns=["intercept", "centered_scaled_time"]
        + [f"channel_{int(item)}" for item in channel_ids[1:]],
        no_op=sigma == 0 or fitted["data_rank"] == 0,
        unsupported_zero=fitted["data_rank"] == 0,
        baseline_channel=int(channel_ids[0]),
        time_center_s=time_center,
        time_scale_s=time_scale,
        weak_modes=basis @ fitted["weak_modes"],
        elapsed_s=time.monotonic() - begun,
    )
    return result


def shrink_zero_sum_means(
    pair_values_hz, satellite_indices, *, sigma_hz, weights=None, minimum_pairs=10
):
    """Grouped KKT solution; use only after common effects are controlled.

    Reduction is O(P+K) once labels are indexed; this wrapper also sorts IDs.
    """
    begun = time.monotonic()
    sigma = _sigma(sigma_hz)
    values, ids, weight, satellites, counts, eligible, mask = _prepare(
        pair_values_hz, satellite_indices, weights, minimum_pairs
    )
    contrasts = np.zeros(len(satellites))
    multiplier = 0.0
    if sigma > 0 and len(eligible) >= 2:
        indices = np.searchsorted(eligible, ids[mask])
        precision = np.bincount(indices, weights=weight[mask], minlength=len(eligible))
        rhs = np.bincount(indices, weights=weight[mask] * values[mask], minlength=len(eligible))
        with np.errstate(over="ignore", divide="ignore"):
            penalty = np.divide(1.0, sigma) ** 2
        inverse = 1 / (precision + penalty)
        if inverse.sum() > 0:
            multiplier = float(np.sum(rhs * inverse) / inverse.sum())
            contrasts[np.searchsorted(satellites, eligible)] = (rhs - multiplier) * inverse
    return dict(
        satellite_ids=satellites,
        contrasts_hz=contrasts,
        pair_counts=counts,
        eligible_satellite_ids=eligible,
        no_op=len(eligible) < 2 or sigma == 0,
        sigma_hz=sigma,
        lagrange_multiplier=multiplier,
        elapsed_s=time.monotonic() - begun,
        scope="Common effects already controlled; no background projection",
    )
