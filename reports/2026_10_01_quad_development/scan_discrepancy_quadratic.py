"""Exact scan random-effects algebra for an explicitly local quadratic surrogate."""
import numpy as np


def solve_discrepancy(information, gradients, sigma_km):
    h = np.asarray(information, dtype=float)
    g = np.asarray(gradients, dtype=float)
    if h.ndim != 3 or h.shape[1:] != (2, 2) or len(h) == 0 or g.shape != (len(h), 2):
        raise ValueError('Expected one 2D information matrix and gradient per scan')
    if not np.all(np.isfinite(h)) or not np.all(np.isfinite(g)) or not np.isfinite(sigma_km) or sigma_km < 0:
        raise ValueError('Nonfinite inputs or invalid discrepancy scale')
    if not np.allclose(h,h.transpose(0,2,1),rtol=0,atol=1e-10) or np.any(np.linalg.eigvalsh(h)<=0):
        raise ValueError('Information must be symmetric positive definite')
    v = np.linalg.inv(h)
    local_minima = -np.linalg.solve(h, g[...,None])[...,0]
    w = np.linalg.inv(v+sigma_km**2*np.eye(2))
    shared_information = w.sum(axis=0)
    center = np.linalg.solve(shared_information,np.einsum('nij,nj->i',w,local_minima))
    offsets = sigma_km**2*np.einsum('nij,nj->ni',w,local_minima-center)
    return dict(center=center, offsets=offsets, information=shared_information,
                local_minima=local_minima)
