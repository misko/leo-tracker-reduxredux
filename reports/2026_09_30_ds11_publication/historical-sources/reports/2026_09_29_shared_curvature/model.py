import math
import sys
from functools import cache
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_09_29_unassociated_trend"))
from trend_mixture import TrendMixturePosition, contrast_density  # noqa: E402


@cache
def quadrature(sigma, order):
    x, w = np.polynomial.legendre.leggauss(order)
    slopes = 6 * sigma * x
    weights = w * np.exp(-0.5 * (6 * x) ** 2)
    weights /= weights.sum()
    return slopes, np.log(weights)


def marginal(logvalues, gradients, logweights):
    """Integrate a product of conditional track mixtures under a common latent."""
    joint = np.sum(logvalues, axis=0) + logweights
    score = logsumexp(joint)
    return float(score), np.exp(joint - score) @ np.sum(gradients, axis=0)


def curvature_basis(times, mask):
    times = np.asarray(times)
    mask = np.asarray(mask, bool)
    centered = times - times[mask].mean()
    design = np.column_stack([np.ones(len(times)), centered])
    quadratic = centered * centered
    beta = np.linalg.lstsq(design[mask], quadratic[mask], rcond=None)[0]
    return quadratic - design @ beta


class SharedCurvature:
    def __init__(self, docs, config, factory, membership, sigma, order=128):
        self.base = TrendMixturePosition(docs, config, factory, 0.2)
        self.documents, self.models = docs, self.base.models
        self.membership, self.sigma, self.order = membership, sigma, order
        self.basis = {
            (di, ti): curvature_basis(track["times_s"], track["mask"])
            for di, doc in enumerate(docs)
            for ti, track in enumerate(doc["tracks"])
        }

    def evaluate(self, x, gradient=True, held=False):
        x = np.asarray(x)
        slopes, logweights = quadrature(self.sigma, self.order)
        groups = {}
        for di, (doc, engine) in enumerate(zip(self.documents, self.models, strict=True)):
            local = x[[0, 1, di + 2]]
            for ti, track in enumerate(doc["tracks"]):
                prediction, visible = engine.prediction(track, local)
                count = int(visible.sum())
                if not count:
                    raise ValueError("No visible retained candidate")
                residual = track["y"][None, :] - prediction
                mask = track["mask"]
                membership = self.membership.get((di, ti))
                if membership:
                    number, slot = membership
                    assert visible[slot]
                    groupkey = (di, number)
                else:
                    slot = None
                    groupkey = ("single", di, ti)
                dp = []
                if gradient:
                    for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
                        p, m = local.copy(), local.copy()
                        p[axis] += step
                        m[axis] -= step
                        if axis == 2:
                            p[axis] = min(5, p[axis])
                            m[axis] = max(-5, m[axis])
                        pp, vp = engine.prediction(track, p)
                        pm, vm = engine.prediction(track, m)
                        assert np.array_equal(vp, visible) and np.array_equal(vm, visible)
                        dp.append((pp - pm) / (p[axis] - m[axis]))

                def density(
                    selected,
                    background,
                    need_gradient,
                    residual=residual,
                    visible=visible,
                    count=count,
                    prediction=prediction,
                    dp=dp,
                    slot=slot,
                    track=track,
                    basis=self.basis[di, ti],
                ):
                    likelihood, influence = contrast_density(residual[:, selected])
                    logcomponents = np.where(visible, likelihood + math.log(0.8 / count), -np.inf)
                    components_gradient = np.zeros((len(prediction), 3))
                    if need_gradient:
                        for axis in range(3):
                            components_gradient[:, axis] = np.sum(
                                influence * dp[axis][:, selected], axis=1
                            )
                    if slot is None:
                        normal = np.logaddexp(logsumexp(logcomponents), math.log(0.2) + background)
                        g = np.exp(logcomponents - normal) @ components_gradient
                        return np.full(len(slopes), normal), np.tile(g, (len(slopes), 1))
                    logcomponents[slot] = -np.inf
                    other = np.logaddexp(logsumexp(logcomponents), math.log(0.2) + background)
                    other_g = np.exp(logcomponents - other) @ components_gradient
                    times = basis[selected]
                    shifted = residual[slot, selected][None, :] - slopes[:, None] * times
                    logshift, influence = contrast_density(shifted)
                    logshift += math.log(0.8 / count)
                    normal = np.logaddexp(other, logshift)
                    signal_g = np.zeros((len(slopes), 3))
                    if need_gradient:
                        for axis in range(3):
                            signal_g[:, axis] = influence @ dp[axis][slot, selected]
                    g = np.exp(other - normal)[:, None] * other_g
                    g += np.exp(logshift - normal)[:, None] * signal_g
                    return normal, g

                train, g = density(mask, self.base.background[di, ti][0], gradient)
                full = (
                    density(np.ones(len(mask), bool), self.base.background[di, ti][1], False)[0]
                    if held
                    else train
                )
                expanded = np.zeros((len(slopes), len(x)))
                expanded[:, [0, 1, di + 2]] = g
                groups.setdefault(groupkey, []).append((train, expanded, full))
        total, derivative, held_score = 0.0, np.zeros_like(x), 0.0
        for members in groups.values():
            score, g = marginal([r[0] for r in members], [r[1] for r in members], logweights)
            total += score
            derivative += g
            if held:
                joint = logsumexp(np.sum([r[2] for r in members], axis=0) + logweights)
                held_score += joint - score
        return dict(score=total, gradient=derivative, held_score=float(held_score))
