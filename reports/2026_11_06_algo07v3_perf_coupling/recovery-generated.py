def hierarchical_bound(raw, features, sigma, groups, *, prior_groups=None, powers=1.0, noise_nu=4.0, prior_nu=4.0, iterations=256):
    y, u, g = (np.asarray(raw, float), np.asarray(features, float), np.asarray(groups))
    if y.ndim != 1 or not len(y) or u.ndim != 2 or (u.shape[0] != len(y)) or (g.shape != y.shape) or (not np.issubdtype(g.dtype, np.integer)) or np.any(g < 0):
        raise ValueError('matching nonempty observations, modes and integer noise groups required')
    if not np.isfinite(y).all() or not np.isfinite(u).all():
        raise ValueError('finite observations and features required')
    s = np.broadcast_to(np.asarray(sigma, float), y.shape)
    if not np.isfinite(s).all() or np.any(s <= 0) or (not np.isfinite(noise_nu)) or (noise_nu <= 0) or (not np.isfinite(prior_nu)) or (prior_nu <= 2) or (iterations < 1):
        raise ValueError('positive finite noise and budgets; prior degrees >2 required')
    _, g = np.unique(g, return_inverse=True)
    counts, width = (np.bincount(g), u.shape[1])
    power = np.broadcast_to(np.asarray(powers, float), counts.shape)
    if not np.isfinite(power).all() or np.any(power <= 0) or np.any(power > 1):
        raise ValueError('one fixed likelihood power in (0,1] per noise group required')
    prior = np.full(width, -1, dtype=int) if prior_groups is None else np.asarray(prior_groups)
    if prior.shape != (width,) or not np.issubdtype(prior.dtype, np.integer) or np.any(prior < -1):
        raise ValueError('one prior group >=-1 per nuisance coefficient required')
    selected = prior >= 0
    _, inverse = np.unique(prior[selected], return_inverse=True)
    prior = prior.copy()
    prior[selected] = inverse
    dimensions = np.bincount(inverse)
    alpha0, beta0 = (noise_nu / 2, noise_nu / 2)
    alpha = alpha0 + power * counts / 2
    pa0, pb0 = (prior_nu / 2, (prior_nu - 2) / 2)
    pa = pa0 + dimensions / 2
    v0 = pa0 / pb0
    rate, prior_rate = (alpha.copy(), pa / v0)
    blocks = []
    identity = np.eye(width, order='F')
    a, r = (u / s[:, None], y / s)
    for k in range(len(counts)):
        use = g == k
        columns = np.flatnonzero(np.any(a[use] != 0, axis=0))
        local = a[use][:, columns]
        blocks.append((columns, np.ix_(columns, columns), local.T @ local, local.T @ r[use]))
    matrix_indices = np.concatenate([(c[:, None] * width + c).ravel() for c, _, _, _ in blocks])
    matrix_groups = np.concatenate([np.full(m.size, k, dtype=int) for k, (_, _, m, _) in enumerate(blocks)])
    matrices = np.concatenate([m.ravel() for _, _, m, _ in blocks])
    rhs_indices = np.concatenate([c for c, _, _, _ in blocks])
    rhs_groups = np.concatenate([np.full(len(c), k, dtype=int) for k, (c, _, _, _) in enumerate(blocks)])
    right_sides = np.concatenate([b for _, _, _, b in blocks])
    by_width = {}
    for k, (columns, index, matrix, _) in enumerate(blocks):
        by_width.setdefault(len(columns), []).append((k, columns, index, matrix.T))
    variance_blocks, variance_individual = ([], [])
    for block_width, rows in by_width.items():
        if len(rows) > 1 and len(rows) * block_width ** 2 * 8 <= 1024 ** 2:
            variance_blocks.append((np.array([r[0] for r in rows]), np.stack([r[1] for r in rows]), np.ascontiguousarray(np.stack([r[3] for r in rows]))))
        else:
            variance_individual.extend(((r[0], r[2], r[3]) for r in rows))
    variance_blocks = [(group_indices, columns[:, :, None] * width + columns[:, None, :], matrices) for group_indices, columns, matrices in variance_blocks]
    inverse_work = np.empty((width, width), order='F')

    def posterior(weight, precision, covariance):
        gram, rhs = (np.diag(precision), np.zeros(width))
        block_weight = power * weight
        np.add.at(gram.ravel(), matrix_indices, block_weight[matrix_groups] * matrices)
        np.add.at(rhs, rhs_indices, block_weight[rhs_groups] * right_sides)
        root = _cholesky(gram)
        lu, pivots, info = dgetrf(root) if width else (root, None, 0)
        if info != 0:
            raise np.linalg.LinAlgError('DGETRF failed')
        mean = _solve_factor(root.T, np.arange(width, dtype=np.int32), _solve_factor(lu, pivots, rhs)) if width else rhs.copy()
        cov = None
        if covariance:
            if width:
                inverse_work[...] = identity
                inv_root, info = dgetrs(lu, pivots, inverse_work, overwrite_b=1)
                if info:
                    raise np.linalg.LinAlgError(f'DGETRS failed: {info}')
            else:
                inv_root = identity.copy()
            cov = inv_root.T @ inv_root
            return (mean, cov, None)
        logdet = float(2 * np.log(np.diag(root)).sum())
        return (mean, cov, max(0.0, logdet - np.log(precision).sum()))
    history = []

    def transition(rate, prior_rate):
        weight, v = (alpha / rate, pa / prior_rate)
        precision = np.ones(width)
        precision[selected] = v[prior[selected]]
        coefficient, covariance, _ = posterior(weight, precision, True)
        native = (y - u @ coefficient) / s
        variance = np.empty(len(blocks))
        for group_indices, indices, variance_matrices in variance_blocks:
            products = covariance.ravel()[indices] * variance_matrices
            variance[group_indices] = np.sum(products, axis=(1, 2))
        for group_index, covariance_index, variance_matrix in variance_individual:
            variance[group_index] = np.sum(covariance[covariance_index] * variance_matrix)
        energy = np.bincount(g, weights=native ** 2) + np.maximum(0, variance)
        next_rate = beta0 + power * energy / 2
        prior_energy = np.bincount(prior[selected], weights=(coefficient ** 2 + np.diag(covariance))[selected], minlength=len(dimensions))
        next_prior_rate = pb0 + prior_energy / 2
        change = max(float(np.max(abs(np.log(next_rate / rate)))), float(np.max(abs(np.log(next_prior_rate / prior_rate)), initial=0)))
        return (next_rate, next_prior_rate, change)
    return transition
