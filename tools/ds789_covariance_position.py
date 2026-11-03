"""Training-profiled geographic objective with multivariate-t track errors."""

import math

import numpy as np
from ds789_correlated_residual import kernel, multivariate_t


def profile_offsets(residual, precision, prior_variance=1e12):
    """Global offset profile, including the original weak quadratic penalty."""
    residual = np.asarray(residual, dtype=float)
    n = residual.shape[1]
    one = precision @ np.ones(n)
    a = float(one.sum())
    center = residual @ one / a
    centered = residual - center[:, None]
    qmin = np.sum((centered @ precision) * centered, axis=1)
    qmin = np.maximum(qmin, 0)
    b, c = 4 + qmin, prior_variance * (4 + n) * a
    aa = a * center**2
    # The derivative's cubic is strictly increasing if B+C>A/3.
    unique = b + c > aa / 3
    offset = center.copy()
    for k in np.flatnonzero(~unique):
        roots = np.roots([aa[k], -2 * aa[k], aa[k] + b[k] + c, -c])
        candidates = [
            float(z.real * center[k])
            for z in roots
            if abs(z.imag) < 1e-8 and -1e-8 <= z.real <= 1 + 1e-8
        ]
        assert candidates
        offset[k] = min(
            candidates,
            key=lambda v: (
                (4 + n) / 2 * np.log1p((qmin[k] + a * (v - center[k]) ** 2) / 4)
                + v**2 / (2 * prior_variance)
            ),
        )
    for _ in range(5):
        delta = offset - center
        den = b + a * delta**2
        derivative = (4 + n) * a * delta / den + offset / prior_variance
        curvature = (4 + n) * a * (b - a * delta**2) / den**2 + 1 / prior_variance
        assert np.all(curvature > 0)
        offset -= derivative / curvature
    r = residual - offset[:, None]
    projected = r @ precision
    q = np.maximum(np.sum(projected * r, axis=1), 0)
    influence = projected * ((4 + n) / (4 + q))[:, None]
    stationarity = -influence.sum(axis=1) + offset / prior_variance
    assert np.max(abs(stationarity)) < 1e-8
    return offset, q, influence, float(np.max(abs(stationarity)))


class CovariancePosition:
    def __init__(self, documents, config, decay_s, model_factory):
        self.documents = documents
        self.models = [model_factory(d, config) for d in documents]
        self.decay_s = decay_s
        self.cache = {}
        for di, doc in enumerate(documents):
            for track in doc["tracks"]:
                mask = track["mask"]
                cov = kernel(np.asarray(track["times_s"])[mask], decay_s) * 100**2
                chol = np.linalg.cholesky(cov)
                inverse = np.linalg.solve(chol, np.eye(len(cov)))
                self.cache[di, track["track_id"]] = (
                    inverse.T @ inverse,
                    float(2 * np.log(np.diag(chol)).sum()),
                )

    def coordinates(self, x):
        return self.models[0].coordinates(x)

    def evaluate(self, x, gradient=True, held=False):
        x = np.asarray(x, dtype=float)
        score, derivative, rows, max_stationarity = 0.0, np.zeros_like(x), [], 0.0
        for di, (doc, model) in enumerate(zip(self.documents, self.models, strict=True)):
            local = np.array([x[0], x[1], x[di + 2]])
            for track in doc["tracks"]:
                mask = track["mask"]
                prediction, visible = model.prediction(track, local)
                residual = track["y"][None, :] - prediction
                precision, logdet = self.cache[di, track["track_id"]]
                offsets, q, influence, stationarity = profile_offsets(residual[:, mask], precision)
                max_stationarity = max(max_stationarity, stationarity)
                train = multivariate_t(q, logdet, int(mask.sum()), 1) - 0.5 * offsets**2 / 1e12
                train = np.where(visible, train, -np.inf)
                normal = np.logaddexp.reduce(train)
                weights = np.exp(train - normal)
                score += float(normal - math.log(track["catalogue_size"]))
                if gradient:
                    for axis in range(3):
                        step = 1e-4 if axis < 2 else 1e-5
                        plus, minus = local.copy(), local.copy()
                        plus[axis] += step
                        minus[axis] -= step
                        if axis == 2:
                            plus[axis] = min(5.0, plus[axis])
                            minus[axis] = max(-5.0, minus[axis])
                        pp, vp = model.prediction(track, plus)
                        pm, vm = model.prediction(track, minus)
                        assert np.array_equal(visible, vp) and np.array_equal(visible, vm)
                        dp = (pp[:, mask] - pm[:, mask]) / (plus[axis] - minus[axis])
                        index = axis if axis < 2 else di + 2
                        derivative[index] += float(weights @ np.sum(influence * dp, axis=1))
                if held:
                    cov = kernel(track["times_s"], self.decay_s) * 100**2
                    chol = np.linalg.cholesky(cov)
                    whitened = np.linalg.solve(chol, (residual - offsets[:, None]).T)
                    joint = (
                        multivariate_t(
                            (whitened**2).sum(axis=0), 2 * np.log(np.diag(chol)).sum(), len(mask), 1
                        )
                        - 0.5 * offsets**2 / 1e12
                    )
                    joint = np.where(visible, joint, -np.inf)
                    rows.append(
                        {
                            "session_id": doc["session_id"],
                            "track_id": track["track_id"],
                            "training_log_score": float(normal - math.log(track["catalogue_size"])),
                            "held_log_score": float(np.logaddexp.reduce(joint) - normal),
                            "weights": weights.tolist(),
                            "offsets": offsets.tolist(),
                            "held_observations": int((~mask).sum()),
                        }
                    )
        return {
            "score": score,
            "gradient": derivative,
            "offset_stationarity": max_stationarity,
            "rows": rows,
        }

    def value_gradient(self, x):
        result = self.evaluate(x)
        return -result["score"], -result["gradient"]
