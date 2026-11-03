"""Local position information after Gaussian nuisance projection.

This conditional tangent diagnostic assumes fixed identities, alias branches,
independent measurement noise and a locally correct physical model. Its ellipse
does not account for wrong identities, TLE errors or model discrepancy.
"""

import numpy as np


def projected_position_information(
    position_jacobian, nuisance_jacobian, *, noise_hz=150.0, weights=None, prior_precision=None
):
    """Project whitened position derivatives off augmented nuisance columns.

    Position columns must be east/north derivatives in Hz/km. Nuisance prior
    precision is diagonal and expressed in the nuisance parameters' own units.
    Scaling columns before the SVD makes the result invariant to their units.
    Prior rows retain the information supplied by an explicit Gaussian prior.
    """
    a, b = np.asarray(position_jacobian, float), np.asarray(nuisance_jacobian, float)
    if a.ndim != 2 or a.shape[1] != 2 or not len(a) or b.ndim != 2 or len(b) != len(a):
        raise ValueError("paired nonempty position (n,2) and nuisance (n,k) matrices required")
    w = np.ones(len(a)) if weights is None else np.asarray(weights, float)
    p = np.zeros(b.shape[1]) if prior_precision is None else np.asarray(prior_precision, float)
    if (
        w.shape != (len(a),)
        or p.shape != (b.shape[1],)
        or not all(np.isfinite(x).all() for x in (a, b, w, p))
        or np.any(w < 0)
        or np.any(p < 0)
        or not np.isfinite(noise_hz)
        or noise_hz <= 0
    ):
        raise ValueError(
            "finite matrices, nonnegative weights/precision and positive noise required"
        )
    root = np.sqrt(w) / noise_hz
    aa = np.vstack((a * root[:, None], np.zeros((len(p), 2))))
    raw_scale = float(np.linalg.norm(aa, ord=2) ** 2)
    bb = np.vstack((b * root[:, None], np.diag(np.sqrt(p))))
    scales = np.linalg.norm(bb, axis=0)
    nonzero = scales > 0
    rank = 0
    if np.any(nonzero):
        u, singular, _ = np.linalg.svd(bb[:, nonzero] / scales[nonzero], full_matrices=False)
        rank = int(np.sum(singular > singular[0] * 1e-10))
        aa = aa - u[:, :rank] @ (u[:, :rank].T @ aa)
    information = aa.T @ aa
    values, vectors = np.linalg.eigh(information)
    identified = values > max(float(values[-1]) * 1e-10, raw_scale * 1e-20, 1e-300)
    covariance = (vectors / values) @ vectors.T if identified.all() else None
    return dict(
        information_per_km2=information,
        eigenvalues_per_km2=values,
        eigenvectors_east_north=vectors,
        nuisance_rank=rank,
        position_rank=int(identified.sum()),
        covariance_km2=covariance,
        one_sigma_axes_km=1 / np.sqrt(values) if identified.all() else None,
        conditional_model_diagnostic_only=True,
    )
