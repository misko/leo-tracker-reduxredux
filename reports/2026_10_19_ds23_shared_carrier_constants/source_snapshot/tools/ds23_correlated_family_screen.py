"""Common-phase catalogue screening with an arbitrary Gaussian fragment covariance."""

import numpy as np
from leo.analysis.research.retained_track_likelihood import PERIOD


def screen(curves, phase_widths, covariance):
    widths, covariance = np.asarray(phase_widths, float), np.asarray(covariance, float)
    if widths.ndim != 1 or not len(widths) or not np.isfinite(widths).all() or np.any(widths <= 0) or not curves:
        raise ValueError('positive finite phase widths and nonempty family required')
    m, count = len(curves), len(widths)
    if covariance.shape != (m, m) or not np.isfinite(covariance).all() or not np.allclose(covariance, covariance.T):
        raise ValueError('matching finite symmetric fragment covariance required')
    root = np.linalg.cholesky(covariance)
    gram = np.broadcast_to(np.eye(m+1), (count, m+1, m+1)).copy()
    rhs, raw, visible, aliases = np.zeros((count, m+1)), np.zeros(count), np.ones(count, bool), []
    for k, curve in enumerate(curves):
        y, f, d, noise = [np.asarray(curve[key], float) for key in ('observed', 'predicted', 'derivative', 'sigma')]
        if y.ndim != 1 or not len(y) or f.shape != (count, len(y)) or d.shape != f.shape or noise.shape != y.shape or np.any(noise <= 0):
            raise ValueError('matching per-point observations/noise and candidate predictions required')
        if not all(np.isfinite(a).all() for a in (y, f, d, noise)):
            raise ValueError('finite candidate inputs required')
        power = float(curve['power'])
        if not 0 < power <= 1:
            raise ValueError('fixed likelihood power in (0,1] required')
        w = power / noise**2
        alias = np.rint((f @ w - y @ w) / sum(w) / PERIOD).astype(int)
        r, u = y + alias[:, None]*PERIOD - f, d*widths[:, None]
        gram[:, 0, 0] += np.sum(w*u*u, axis=1)
        cross = (u @ w)[:, None]*root[k]
        gram[:, 0, 1:] += cross
        gram[:, 1:, 0] += cross
        gram[:, 1:, 1:] += sum(w)*np.outer(root[k], root[k])
        rhs[:, 0] += np.sum(w*u*r, axis=1)
        rhs[:, 1:] += (r @ w)[:, None]*root[k]
        raw += np.sum(w*r*r, axis=1)
        visibility = np.asarray(curve['visible'], bool)
        if visibility.shape != (count,):
            raise ValueError('visibility required for each candidate')
        visible &= visibility
        aliases.append(alias)
    factor = np.linalg.cholesky(gram)
    coefficient = np.linalg.solve(factor.swapaxes(-1, -2), np.linalg.solve(factor, rhs[..., None]))[..., 0]
    cost = raw - np.sum(rhs*coefficient, axis=1) + 2*np.log(np.diagonal(factor, axis1=-2, axis2=-1)).sum(axis=1)
    cost[~visible] = np.inf
    biases = coefficient[:, 1:] @ root.T
    return dict(cost=cost, phase_correction_s=coefficient[:, 0]*widths,
        aliases=aliases, bias_hz=[biases[:, k] for k in range(m)])
