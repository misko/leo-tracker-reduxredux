"""Noise-weighted observability diagnostics for an additional physical mode."""

import numpy as np


def project_direction(column, existing, sigma, *, rcond=1e-10):
    """Remove the span of existing modes; return physical and whitened sizes.

    This is an unregularized tangent-space diagnostic, not a posterior or a
    decision to change the existing covariance. Normalize columns before SVD
    so engineering units cannot arbitrarily determine numerical rank.
    """
    y, a, s = np.asarray(column, float), np.asarray(existing, float), np.asarray(sigma, float)
    if y.ndim != 1 or a.ndim != 2 or a.shape[0] != len(y) or s.shape != y.shape or not len(y):
        raise ValueError('matching nonempty mode, design and noise dimensions required')
    if not all(np.isfinite(v).all() for v in (y, a, s)) or np.any(s <= 0) or not 0 < rcond < 1:
        raise ValueError('finite values, positive noise and rank threshold required')
    z, u = y / s, a / s[:, None]
    scales = np.linalg.norm(u, axis=0)
    active = scales > 0
    normalized = u[:, active] / scales[active]
    if normalized.shape[1]:
        left, values, right = np.linalg.svd(normalized, full_matrices=False)
        keep = values > rcond * values[0]
        residual_white = z - left[:, keep] @ (left[:, keep].T @ z)
        coefficient = np.zeros(a.shape[1])
        coefficient[active] = (right[keep].T @ ((left[:, keep].T @ z) / values[keep])) / scales[active]
        rank = int(keep.sum())
    else:
        residual_white, coefficient, rank = z.copy(), np.zeros(a.shape[1]), 0
    residual = residual_white * s
    total, independent = float(z @ z), float(residual_white @ residual_white)
    return dict(independent_hz=residual, representation_coefficient=coefficient,
        existing_rank=rank, raw_RMS_hz=float(np.sqrt(np.mean(y*y))),
        independent_RMS_hz=float(np.sqrt(np.mean(residual*residual))),
        raw_noise_norm=float(np.sqrt(total)), independent_noise_norm=float(np.sqrt(independent)),
        independent_energy_fraction=independent / total if total > 0 else 0.)
