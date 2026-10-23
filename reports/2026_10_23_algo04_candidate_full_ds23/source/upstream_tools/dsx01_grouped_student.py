"""Same Gaussian/Gamma bound using grouped sufficient statistics.

The latent precision is constant within each original fragment. Reusing that
fact avoids repeatedly whitening every observation to update its covariance.
This changes numerical evaluation cost, not the probabilistic model.
"""

import numpy as np


def student_joint_bound(raw, features, sigma, groups, *, nu=4.0, iterations=24):
    y, u, g = np.asarray(raw, float), np.asarray(features, float), np.asarray(groups)
    if (
        y.ndim != 1
        or not len(y)
        or u.ndim != 2
        or u.shape[0] != len(y)
        or g.shape != y.shape
        or not np.issubdtype(g.dtype, np.integer)
        or np.any(g < 0)
    ):
        raise ValueError("matching nonempty observations, modes and integer noise groups required")
    s = np.broadcast_to(np.asarray(sigma, float), y.shape)
    if (
        not np.isfinite(y).all()
        or not np.isfinite(u).all()
        or not np.isfinite(s).all()
        or np.any(s <= 0)
        or not np.isfinite(nu)
        or nu <= 0
        or iterations < 1
    ):
        raise ValueError("finite inputs, positive noise/degrees and iteration budget required")
    _, g = np.unique(g, return_inverse=True)
    count, width = np.bincount(g), u.shape[1]
    alpha, b0 = (nu + count) / 2, nu / 2
    a, r = u / s[:, None], y / s
    blocks = []
    for k in range(len(count)):
        mask = g == k
        columns = np.flatnonzero(np.any(a[mask] != 0, axis=0))
        local = a[mask][:, columns]
        blocks.append((columns, local.T @ local, local.T @ r[mask]))

    def posterior(weight, *, covariance):
        gram, rhs = np.eye(width), np.zeros(width)
        for w, (cols, matrix, b) in zip(weight, blocks, strict=True):
            gram[np.ix_(cols, cols)] += w * matrix
            rhs[cols] += w * b
        root = np.linalg.cholesky(gram)
        coefficient = np.linalg.solve(root.T, np.linalg.solve(root, rhs))
        inverse = None
        if covariance:
            inverse_root = np.linalg.solve(root, np.eye(width))
            inverse = inverse_root.T @ inverse_root
        return coefficient, inverse, float(2 * np.log(np.diag(root)).sum())

    rate, history = alpha.copy(), []
    for _ in range(iterations):
        weight = alpha / rate
        coefficient, covariance, _ = posterior(weight, covariance=True)
        residual = (y - u @ coefficient) / s
        variance = np.array(
            [np.sum(covariance[np.ix_(cols, cols)] * matrix.T) for cols, matrix, _ in blocks]
        )
        energy = np.bincount(g, weights=residual**2) + np.maximum(0.0, variance)
        updated = (nu + energy) / 2
        change = float(np.max(abs(np.log(updated / rate))))
        rate = updated
        history.append(change)
        if change < 1e-5:
            break
    weight = alpha / rate
    coefficient, _, volume = posterior(weight, covariance=False)
    native = y - u @ coefficient
    innovation = native / s * np.sqrt(weight[g])
    ratio = rate / b0
    gamma = np.maximum(0.0, 2 * alpha * (np.log(ratio) + 1 / ratio - 1))
    return dict(
        residual=np.r_[innovation, coefficient, np.sqrt(max(0.0, volume)), np.sqrt(gamma)],
        coefficient=coefficient,
        quadratic=float(innovation @ innovation + coefficient @ coefficient),
        logvolume=max(0.0, volume),
        conditional_residual_hz=native,
        noise_precision=weight,
        gamma_cost=float(gamma.sum()),
        precision_iterations=len(history),
        final_log_precision_change=history[-1],
    )
