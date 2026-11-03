"""Normalized Gaussian/Gamma bounds with grouped noise and orbital priors.

Optional powers define a generalized posterior, not a normalized sampling
likelihood. Normal-Gamma prior groups have Student marginals with unit
variance; coefficients with group -1 retain their unit Gaussian prior.
"""

from math import lgamma

import numpy as np

gammaln = np.vectorize(lgamma, otypes=[float])


def hierarchical_bound(
    raw,
    features,
    sigma,
    groups,
    *,
    prior_groups=None,
    powers=1.0,
    noise_nu=4.0,
    prior_nu=4.0,
    iterations=256,
):
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
    if not np.isfinite(y).all() or not np.isfinite(u).all():
        raise ValueError("finite observations and features required")
    s = np.broadcast_to(np.asarray(sigma, float), y.shape)
    if (
        not np.isfinite(s).all()
        or np.any(s <= 0)
        or not np.isfinite(noise_nu)
        or noise_nu <= 0
        or not np.isfinite(prior_nu)
        or prior_nu <= 2
        or iterations < 1
    ):
        raise ValueError("positive finite noise and budgets; prior degrees >2 required")
    _, g = np.unique(g, return_inverse=True)
    counts, width = np.bincount(g), u.shape[1]
    power = np.broadcast_to(np.asarray(powers, float), counts.shape)
    if not np.isfinite(power).all() or np.any(power <= 0) or np.any(power > 1):
        raise ValueError("one fixed likelihood power in (0,1] per noise group required")
    prior = np.full(width, -1, dtype=int) if prior_groups is None else np.asarray(prior_groups)
    if prior.shape != (width,) or not np.issubdtype(prior.dtype, np.integer) or np.any(prior < -1):
        raise ValueError("one prior group >=-1 per nuisance coefficient required")
    selected = prior >= 0
    _, inverse = np.unique(prior[selected], return_inverse=True)
    prior = prior.copy()
    prior[selected] = inverse
    dimensions = np.bincount(inverse)
    alpha0, beta0 = noise_nu / 2, noise_nu / 2
    alpha = alpha0 + power * counts / 2
    pa0, pb0 = prior_nu / 2, (prior_nu - 2) / 2
    pa = pa0 + dimensions / 2
    v0 = pa0 / pb0
    rate, prior_rate = alpha.copy(), pa / v0
    blocks = []
    a, r = u / s[:, None], y / s
    for k in range(len(counts)):
        use = g == k
        columns = np.flatnonzero(np.any(a[use] != 0, axis=0))
        local = a[use][:, columns]
        blocks.append((columns, local.T @ local, local.T @ r[use]))

    def posterior(weight, precision, covariance):
        gram, rhs = np.diag(precision), np.zeros(width)
        for w, (cols, matrix, b) in zip(power * weight, blocks, strict=True):
            gram[np.ix_(cols, cols)] += w * matrix
            rhs[cols] += w * b
        root = np.linalg.cholesky(gram)
        mean = np.linalg.solve(root.T, np.linalg.solve(root, rhs))
        cov = None
        if covariance:
            inv_root = np.linalg.solve(root, np.eye(width))
            cov = inv_root.T @ inv_root
        logdet = float(2 * np.log(np.diag(root)).sum())
        return mean, cov, max(0.0, logdet - np.log(precision).sum())

    history = []
    for _ in range(iterations):
        weight, v = alpha / rate, pa / prior_rate
        precision = np.ones(width)
        precision[selected] = v[prior[selected]]
        coefficient, covariance, _ = posterior(weight, precision, True)
        native = (y - u @ coefficient) / s
        variance = np.array(
            [np.sum(covariance[np.ix_(cols, cols)] * matrix.T) for cols, matrix, _ in blocks]
        )
        energy = np.bincount(g, weights=native**2) + np.maximum(0, variance)
        next_rate = beta0 + power * energy / 2
        prior_energy = np.bincount(
            prior[selected],
            weights=(coefficient**2 + np.diag(covariance))[selected],
            minlength=len(dimensions),
        )
        next_prior_rate = pb0 + prior_energy / 2
        change = max(
            float(np.max(abs(np.log(next_rate / rate)))),
            float(np.max(abs(np.log(next_prior_rate / prior_rate)), initial=0)),
        )
        rate, prior_rate = next_rate, next_prior_rate
        history.append(change)
        if change < 1e-5:
            break
    weight, v = alpha / rate, pa / prior_rate
    precision = np.ones(width)
    precision[selected] = v[prior[selected]]
    coefficient, _, volume = posterior(weight, precision, False)
    native = y - u @ coefficient
    innovation = native / s * np.sqrt((power * weight)[g])
    ratio = rate / beta0
    noise_gamma = np.maximum(0, 2 * alpha * (np.log(ratio) + 1 / ratio - 1))
    prior_gamma = np.maximum(0, 2 * pa0 * (np.log(v0 / v) + v / v0 - 1))
    # The following fixed constants restore the actual -2 ELBO. For power<1
    # this is the generalized evidence, not a probability density of the data.
    noise_constant = 2 * gammaln(alpha0) - 2 * gammaln(alpha) + power * counts * np.log(beta0)
    prior_constant = (
        2 * gammaln(pa0)
        - 2 * gammaln(pa)
        + dimensions * np.log(pa0)
        + 2 * pa * np.log(pa / pa0)
        - dimensions
    )
    normalization = float(
        np.sum(power[g] * (np.log(2 * np.pi) + 2 * np.log(s)))
        + noise_constant.sum()
        + prior_constant.sum()
    )
    residual = np.r_[
        innovation,
        coefficient * np.sqrt(precision),
        np.sqrt(volume),
        np.sqrt(noise_gamma),
        np.sqrt(prior_gamma),
    ]
    return dict(
        residual=residual,
        coefficient=coefficient,
        quadratic=float(innovation @ innovation + np.sum(precision * coefficient**2)),
        logvolume=volume,
        conditional_residual_hz=native,
        noise_precision=weight,
        coefficient_prior_precision=precision,
        prior_group_precision=v,
        noise_gamma_cost=float(noise_gamma.sum()),
        prior_gamma_cost=float(prior_gamma.sum()),
        gamma_cost=float(noise_gamma.sum() + prior_gamma.sum()),
        normalization_constant=normalization,
        negative_twice_elbo=float(residual @ residual + normalization),
        effective_observations=float(power @ counts),
        precision_iterations=len(history),
        final_log_precision_change=history[-1],
    )
