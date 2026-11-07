def two_family_phase_evidence(observed, means, base_covariance, modes, log_priors, visible, *, max_pairs=32768, optimize_contractions=True):
    """Integrate independent orbit modes and phases, retaining cross-family covariance.

    The base covariance contains measurement/track noise and a single shared
    calibration covariance. No fitted calibration mean is changed. Work arrays
    are chunked; the log phase table is retained for exact marginalization.
    Contraction order is explicit: the pinned ALGO03 worker uses optimized
    contractions, while the pinned ALGO04 worker uses direct contractions.
    """
    if any((len(v) != 2 for v in (observed, means, modes, log_priors, visible))) or max_pairs < 1:
        raise ValueError('exactly two families and a positive chunk budget required')
    with _observe_statement('22: y'):
        y = [np.asarray(v, float) for v in observed]
    with _observe_statement('23: m'):
        m = [np.asarray(v, float) for v in means]
    with _observe_statement('24: u'):
        u = [np.asarray(v, float) for v in modes]
    with _observe_statement('25: lp'):
        lp = [np.asarray(v, float) for v in log_priors]
    with _observe_statement('26: valid'):
        valid = [np.asarray(v, bool) for v in visible]
    with _observe_statement('27: b'):
        b = np.asarray(base_covariance, float)
    for k in range(2):
        if y[k].ndim != 1 or not len(y[k]) or m[k].ndim != 2 or (m[k].shape[1:] != y[k].shape) or (not len(m[k])):
            raise ValueError('matching nonempty observation and phase geometry required')
        if u[k].ndim != 3 or u[k].shape[:2] != m[k].shape or (not u[k].shape[2]) or (lp[k].shape != (len(m[k]),)) or (valid[k].shape != lp[k].shape):
            raise ValueError('matching orbit modes and phase priors required')
        if not all((np.isfinite(v).all() for v in (y[k], m[k], u[k]))) or not np.isfinite(lp[k]).any() or np.isnan(lp[k]).any() or np.isposinf(lp[k]).any():
            raise ValueError('finite geometry and a finite phase prior required')
    with _observe_statement('52: (n1, n2)'):
        n1, n2 = map(len, y)
    with _observe_statement('53: n'):
        n = n1 + n2
    if b.shape != (n, n) or not np.isfinite(b).all() or (not np.allclose(b, b.T, rtol=1e-10, atol=1e-08)):
        raise ValueError('matching symmetric base covariance required')
    with _observe_statement('60: root'):
        root = np.linalg.cholesky((b + b.T) / 2)
    with _observe_statement('61: precision'):
        precision = cho_solve((root, True), np.eye(n))
    with _observe_statement('62: (p11, p12, p22)'):
        p11, p12, p22 = (precision[:n1, :n1], precision[:n1, n1:], precision[n1:, n1:])
    with _observe_statement('63: (r1, r2)'):
        r1, r2 = (y[0] - m[0], y[1] - m[1])
    with _observe_statement('64: (u1, u2)'):
        u1, u2 = u
    with _observe_statement('65: (d1, d2)'):
        d1, d2 = (u1.shape[2], u2.shape[2])
    with _observe_statement('66: a1'):
        a1 = np.einsum('kna,nm->kam', u1, p11)
    with _observe_statement('67: a2'):
        a2 = np.einsum('kna,nm->kam', u2, p22)
    with _observe_statement('68: cross'):
        cross = np.einsum('kna,nm->kam', u1, p12)
    with _observe_statement('69: g1'):
        g1 = np.eye(d1) + np.einsum('kan,knb->kab', a1, u1)
    with _observe_statement('70: g2'):
        g2 = np.eye(d2) + np.einsum('kan,knb->kab', a2, u2)
    with _observe_statement('71: h1'):
        h1 = np.einsum('kan,kn->ka', a1, r1)
    with _observe_statement('72: h2'):
        h2 = np.einsum('kan,kn->ka', a2, r2)
    with _observe_statement('73: q1'):
        q1 = np.einsum('kn,nm,km->k', r1, p11, r1)
    with _observe_statement('74: q2'):
        q2 = np.einsum('kn,nm,km->k', r2, p22, r2)
    with _observe_statement('75: projected'):
        projected = r1 @ p12
    with _observe_statement('76: counts'):
        counts = [len(v) for v in m]
    with _observe_statement('77: prior'):
        prior = [v - logsumexp(v) for v in lp]
    with _observe_statement('78: log_joint'):
        log_joint = np.full(counts, -np.inf)
    with _observe_statement('79: best'):
        best = -np.inf
    with _observe_statement('80: best_coeff'):
        best_coeff = np.zeros(d1 + d2)
    with _observe_statement('81: constant'):
        constant = 2 * np.log(np.diag(root)).sum() + n * np.log(2 * np.pi)
    with _observe_statement('82: rows_per_chunk'):
        rows_per_chunk = max(1, max_pairs // counts[1])
    for start in range(0, counts[0], rows_per_chunk):
        with _observe_statement('84: end'):
            end = min(start + rows_per_chunk, counts[0])
        with _observe_statement('85: shape'):
            shape = (end - start, counts[1])
        with _observe_statement('86: gram'):
            gram = np.empty((*shape, d1 + d2, d1 + d2))
        with _observe_statement('87: gram[:, :, :d1, :d1]'):
            gram[:, :, :d1, :d1] = g1[start:end, None]
        with _observe_statement('88: gram[:, :, d1:, d1:]'):
            gram[:, :, d1:, d1:] = g2[None]
        with _observe_statement('89: off'):
            off = np.einsum('ian,jnb->ijab', cross[start:end], u2, optimize=optimize_contractions)
        with _observe_statement('90: gram[:, :, :d1, d1:]'):
            gram[:, :, :d1, d1:] = off
        with _observe_statement('91: gram[:, :, d1:, :d1]'):
            gram[:, :, d1:, :d1] = off.swapaxes(-1, -2)
        with _observe_statement('92: rhs'):
            rhs = np.concatenate((h1[start:end, None] + np.einsum('ian,jn->ija', cross[start:end], r2, optimize=optimize_contractions), h2[None] + np.einsum('jna,in->ija', u2, projected[start:end], optimize=optimize_contractions)), axis=-1)
        with _observe_statement('103: (coefficient, sign, logdet)'):
            coefficient, sign, logdet = solve_and_slogdet(gram, rhs)
        with _observe_statement('104: raw'):
            raw = q1[start:end, None] + q2[None] + 2 * projected[start:end] @ r2.T
        if not np.all(sign > 0):
            raise ValueError('orbital precision is not positive definite')
        with _observe_statement('107: log_density'):
            log_density = -0.5 * (raw - np.sum(rhs * coefficient, axis=-1) + logdet + constant)
        with _observe_statement('108: joint'):
            joint = log_density + prior[0][start:end, None] + prior[1][None]
        with _observe_statement('109: joint'):
            joint = np.where(valid[0][start:end, None] & valid[1][None], joint, -np.inf)
        with _observe_statement('110: log_joint[start:end]'):
            log_joint[start:end] = joint
        with _observe_statement('111: flat'):
            flat = int(np.argmax(joint))
        with _observe_statement('112: score'):
            score = joint.flat[flat]
        if score > best:
            with _observe_statement('114: best'):
                best = score
            with _observe_statement('115: best_coeff'):
                best_coeff = coefficient.reshape(-1, d1 + d2)[flat].copy()
    with _observe_statement('116: evidence'):
        evidence = float(logsumexp(log_joint))
    with _observe_statement('117: weights'):
        weights = np.exp(log_joint - evidence) if np.isfinite(evidence) else np.zeros(counts)
    with _observe_statement('118: k'):
        k = np.unravel_index(int(np.argmax(log_joint)), tuple(counts))
    return dict(negative_twice_log_density=-2 * evidence, phase_marginals=[weights.sum(axis=1), weights.sum(axis=0)], joint_map_indices=list(map(int, k)), orbital_map_mean=[best_coeff[:d1], best_coeff[d1:]], visible_prior_mass=float(np.exp(prior[0][valid[0]]).sum() * np.exp(prior[1][valid[1]]).sum()), phase_pair_count=int(np.prod(counts)), receiver_covariance_integrated_once=True)
