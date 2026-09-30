"""Zero-decay Student-t4 frequency contrasts, without a fitted constant offset."""

import math

import numpy as np


def contrast_density(residual, scale=100.0):
    """Return anchored-difference log density and its prediction derivative.

    For n observations, D subtracts any one observation from the other n-1.
    D(scale^2 I)D^T = scale^2(I + 11^T). Centering below is an algebraic
    evaluation of that density, not fitting an offset using scored observations.
    The returned influence differentiates with respect to predicted frequency,
    which has the opposite sign to differentiation with respect to residual.
    """
    residual = np.asarray(residual, dtype=float)
    if residual.ndim != 2 or residual.shape[1] < 2:
        raise ValueError(
            "Require candidate-by-observation residuals with at least two observations"
        )
    if not np.isfinite(residual).all() or not np.isfinite(scale) or scale <= 0:
        raise ValueError("Require finite residuals and positive finite scale")
    n = residual.shape[1]
    dimension = n - 1
    differences = residual - residual[:, :1]
    centered = differences - differences.mean(axis=1, keepdims=True)
    q = np.sum(centered**2, axis=1) / scale**2
    logdet = dimension * math.log(scale**2) + math.log(n)
    density = (
        math.lgamma((4 + dimension) / 2)
        - math.lgamma(2)
        - 0.5 * (dimension * math.log(4 * math.pi) + logdet)
        - (4 + dimension) / 2 * np.log1p(q / 4)
    )
    influence = centered / scale**2 * ((4 + dimension) / (4 + q))[:, None]
    return density, influence


class ContrastPosition:
    def __init__(self, documents, config, model_factory):
        self.documents = documents
        self.models = [model_factory(d, config) for d in documents]
        for doc in documents:
            for track in doc["tracks"]:
                mask = np.asarray(track["mask"], dtype=bool)
                if mask.sum() < 2 or mask.all():
                    raise ValueError(
                        "Each track requires at least two training and one held observation"
                    )

    def coordinates(self, x):
        return self.models[0].coordinates(x)

    def evaluate(self, x, gradient=True, held=False):
        x = np.asarray(x, dtype=float)
        if x.shape != (2 + len(self.documents),) or not np.isfinite(x).all():
            raise ValueError("Require shared E/N and one finite timing per recording")
        score, derivative, rows = 0.0, np.zeros_like(x), []
        for di, (doc, model) in enumerate(zip(self.documents, self.models, strict=True)):
            local = np.array([x[0], x[1], x[di + 2]])
            for track in doc["tracks"]:
                mask = track["mask"]
                prediction, visible = model.prediction(track, local)
                residual = track["y"][None, :] - prediction
                train, influence = contrast_density(residual[:, mask])
                train = np.where(visible, train, -np.inf)
                normal = np.logaddexp.reduce(train)
                if not np.isfinite(normal):
                    raise ValueError("No finite visible candidate density")
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
                    joint, _ = contrast_density(residual)
                    joint = np.where(visible, joint, -np.inf)
                    rows.append(
                        {
                            "session_id": doc["session_id"],
                            "track_id": track["track_id"],
                            "training_log_score": float(normal - math.log(track["catalogue_size"])),
                            "held_log_score": float(np.logaddexp.reduce(joint) - normal),
                            "weights": weights.tolist(),
                            "anchor_observation_index": int(np.flatnonzero(mask)[0]),
                            "training_contrast_dimension": int(mask.sum()) - 1,
                            "full_contrast_dimension": len(mask) - 1,
                            "held_observations": int((~mask).sum()),
                        }
                    )
        return {"score": score, "gradient": derivative, "rows": rows}

    def value_gradient(self, x):
        result = self.evaluate(x)
        return -result["score"], -result["gradient"]
