import itertools
import math

import numpy as np


def choose(information, hessians, gradients, count, batch_size=8192):
    information = np.asarray(information)
    hessians, gradients = np.asarray(hessians), np.asarray(gradients)
    n = len(information)
    assert information.shape == hessians.shape == (n, 2, 2)
    assert gradients.shape == (n, 2) and 0 < count <= n
    assert all(np.isfinite(a).all() for a in (information, hessians, gradients))
    ridge = float(np.trace(information.sum(axis=0)) / 2 * 1e-9)
    assert ridge > 0
    combinations = itertools.combinations(range(n), count)
    best, examined, positive = None, 0, 0
    while chunk := list(itertools.islice(combinations, batch_size)):
        indices = np.array(chunk)
        info = information[indices].sum(axis=1) + np.eye(2) * ridge
        h = hessians[indices].sum(axis=1)
        g = gradients[indices].sum(axis=1)
        det = h[:, 0, 0] * h[:, 1, 1] - h[:, 0, 1] ** 2
        valid = (h[:, 0, 0] > 0) & (det > 0)
        positive += int(valid.sum())
        examined += len(chunk)
        penalty = np.full(len(chunk), np.inf)
        penalty[valid] = (
            h[valid, 1, 1] * g[valid, 0] ** 2
            - 2 * h[valid, 0, 1] * g[valid, 0] * g[valid, 1]
            + h[valid, 0, 0] * g[valid, 1] ** 2
        ) / det[valid]
        signs, logdet = np.linalg.slogdet(info)
        assert np.all(signs > 0)
        objective = logdet - penalty
        k = int(np.argmax(objective))
        if np.isfinite(objective[k]) and (best is None or objective[k] > best["objective"]):
            best = dict(
                indices=indices[k].tolist(),
                objective=float(objective[k]),
                log_determinant=float(logdet[k]),
                penalty=float(penalty[k]),
            )
    assert examined == math.comb(n, count)
    if best is None:
        raise ValueError("No subset with positive definite observed curvature")
    return dict(best, examined=examined, positive_curvature_subsets=positive, ridge=ridge)
