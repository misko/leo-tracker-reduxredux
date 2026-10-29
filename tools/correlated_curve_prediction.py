"""Gaussian covariance diagnostics with explicit cross-channel dependence."""

import numpy as np
from scipy.linalg import cho_solve, solve_triangular


def shared_kernel(times, groups, amplitude_hz, timescale_s):
    t, g = np.asarray(times, float), np.asarray(groups)
    if t.ndim != 1 or g.shape != t.shape or not np.isfinite(t).all():
        raise ValueError('matching finite times and groups required')
    if not np.isfinite([amplitude_hz, timescale_s]).all() or amplitude_hz < 0 or timescale_s <= 0:
        raise ValueError('nonnegative amplitude and positive timescale required')
    return amplitude_hz**2 * np.exp(-abs(t[:, None]-t[None, :])/timescale_s) * (g[:, None] == g[None, :])


def gaussian(raw, covariance):
    y, cov = np.asarray(raw, float), np.asarray(covariance, float)
    if y.ndim != 1 or cov.shape != (len(y), len(y)) or not np.isfinite(y).all() or not np.isfinite(cov).all():
        raise ValueError('matching finite Gaussian observations and covariance required')
    if not np.allclose(cov, cov.T, atol=1e-9, rtol=1e-12):
        raise ValueError('symmetric covariance required')
    root = np.linalg.cholesky(cov)
    white = solve_triangular(root, y, lower=True)
    volume = float(2*np.log(np.diag(root)).sum())
    return dict(whitened=white, quadratic=float(white@white), logdet=volume,
                objective=float(white@white+volume+len(y)*np.log(2*np.pi)))


def conditional(raw, covariance, training):
    y, cov, train = np.asarray(raw, float), np.asarray(covariance, float), np.asarray(training, bool)
    if train.shape != y.shape or not train.any() or train.all():
        raise ValueError('nonempty training and withheld observations required')
    root = np.linalg.cholesky(cov[np.ix_(train, train)])
    cross = cov[np.ix_(~train, train)]
    prediction = cross @ cho_solve((root, True), y[train])
    posterior = cov[np.ix_(~train, ~train)] - cross @ cho_solve((root, True), cross.T)
    posterior = (posterior + posterior.T)/2
    result = gaussian(y[~train]-prediction, posterior)
    result.update(prediction_hz=prediction, residual_hz=y[~train]-prediction,
                  prediction_sigma_hz=np.sqrt(np.diag(posterior)))
    return result


def randomized_blocks(times, seed=20261029, block_s=12.):
    t = np.asarray(times)
    groups = np.floor(t/block_s).astype(int)
    available = np.unique(groups)
    if len(available) < 3: raise ValueError('at least three time blocks required')
    withheld = np.sort(np.random.default_rng(seed).choice(available, max(1, int(np.ceil(len(available)*.25))), replace=False))
    return ~np.isin(groups, withheld), dict(seed=seed, block_s=block_s, point_block_ids=groups,
                                          withheld_blocks=withheld)
