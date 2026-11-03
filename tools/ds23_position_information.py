"""Local linear-Gaussian position information after nuisance elimination.

This is conditional on supplied noise and prior precisions. It is not a
calibrated confidence region for the nonlinear generalized Gamma model.
"""

import numpy as np


def marginal_position_information(position_design, nuisance_design, weights, prior_precision):
    j, u, w, prior = (np.asarray(v, float) for v in (position_design, nuisance_design, weights, prior_precision))
    if (j.ndim != 2 or j.shape[1] != 2 or u.ndim != 2 or len(u) != len(j) or w.shape != (len(j),)
            or prior.shape != (u.shape[1],) or not all(np.isfinite(v).all() for v in (j,u,w,prior))
            or np.any(w <= 0) or np.any(prior <= 0)):
        raise ValueError('matching finite designs, positive weights and nuisance precisions required')
    # Orthogonal projection of the augmented data/prior system avoids
    # cancellation between two large nearly equal Fisher matrices.
    a = np.vstack((u*np.sqrt(w[:,None]), np.diag(np.sqrt(prior))))
    b = np.vstack((j*np.sqrt(w[:,None]), np.zeros((len(prior),2))))
    if len(prior):
        q, _ = np.linalg.qr(a, mode='reduced'); b = b-q@(q.T@b)
    information = b.T@b
    return (information+information.T)/2


def ellipse_scales(information):
    values = np.linalg.eigvalsh(np.asarray(information))
    if values[0] <= 0:
        raise ValueError('positive position information required')
    return dict(major_local_sigma_km=float(1/np.sqrt(values[0])), minor_local_sigma_km=float(1/np.sqrt(values[1])),
                information_eigenvalues=values)
