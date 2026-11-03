"""Local group-deletion diagnostics for a fixed IRLS quadratic.

The normal matrix includes the prior; group contributions exclude it. Removing
a group retains the original nuisance prior. These steps freeze associations,
Jacobians and robust weights and are not nonlinear refits or calibrated errors.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DeletionStep:
    step: np.ndarray | None
    reason: str


def group_deletion_steps(information, rhs, group_information, group_rhs):
    """Solve each remaining quadratic, recording loss of identifiability."""
    h, g, hs, gs = (np.asarray(a, dtype=float) for a in
                    (information, rhs, group_information, group_rhs))
    if (g.ndim != 1 or g.size == 0 or h.shape != (g.size, g.size)
            or hs.ndim != 3 or hs.shape[1:] != h.shape or gs.shape != hs.shape[:2]
            or any(not np.all(np.isfinite(a)) for a in (h, g, hs, gs))
            or not np.allclose(h, h.T, rtol=1e-12, atol=1e-12)
            or not np.allclose(hs, hs.swapaxes(1, 2), rtol=1e-12, atol=1e-12)):
        raise ValueError('invalid group quadratic dimensions or values')
    np.linalg.cholesky(h)
    results = []
    for part, score in zip(hs, gs, strict=True):
        remaining = h-part
        diagonal = np.diag(remaining)
        if np.any(diagonal <= 0):
            results.append(DeletionStep(None, 'not_positive_definite'))
            continue
        scale = 1/np.sqrt(diagonal)
        balanced = scale[:, None]*remaining*scale[None, :]
        balanced = .5*(balanced+balanced.T)
        try:
            chol = np.linalg.cholesky(balanced)
            step = scale*np.linalg.solve(chol.T, np.linalg.solve(chol, scale*(g-score)))
        except np.linalg.LinAlgError:
            results.append(DeletionStep(None, 'not_positive_definite'))
        else:
            results.append(DeletionStep(step, 'ok'))
    return tuple(results)
