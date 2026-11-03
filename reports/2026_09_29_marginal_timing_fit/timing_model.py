import math

import ds7_baseline_adapter as numerical
import numpy as np
from scipy.special import logsumexp
from trend_mixture import contrast_density


def timing_nodes(order, grid):
    nodes, weights = np.polynomial.legendre.leggauss(order)
    left, right = np.asarray(grid[:-1]), np.asarray(grid[1:])
    values = (left[:, None] + right[:, None]) / 2 + (right - left)[:, None] * nodes / 2
    mass = (right - left)[:, None] * weights / 2 / (grid[-1] - grid[0])
    return values.ravel(), np.log(mass.ravel())


def log_integral(scores, logweights):
    return float(logsumexp(np.asarray(scores) + logweights))


def training_scores(model, position, times):
    """Training likelihood and analytic E/N derivative at each shared scan time."""
    assert len(model.documents) == 1
    engine = model.models[0]
    rec, up = numerical.site(*engine.coordinates([*position, 0.0]))
    rec_derivatives = []
    for axis in range(2):
        p, m = np.array(position, dtype=float), np.array(position, dtype=float)
        p[axis] += 1e-4
        m[axis] -= 1e-4
        rp, _ = numerical.site(*engine.coordinates([*p, 0.0]))
        rm, _ = numerical.site(*engine.coordinates([*m, 0.0]))
        rec_derivatives.append((rp - rm) / 2e-4)
    rec_derivatives = np.array(rec_derivatives)
    grid = engine.taus
    times = np.asarray(times)
    result = np.zeros(len(times))
    gradient = np.zeros((len(times), 2))
    for start in range(0, len(times), 32):
        t = times[start : start + 32]
        hi = np.clip(np.searchsorted(grid, t, side="right"), 1, len(grid) - 1)
        lo = hi - 1
        weight = ((t - grid[lo]) / (grid[hi] - grid[lo]))[None, :, None, None]
        score = np.zeros(len(t))
        derivative = np.zeros((len(t), 2))
        for ti, track in enumerate(model.documents[0]["tracks"]):
            position_bank, velocity_bank = (
                track["candidate_position_km"],
                track["candidate_velocity_km_s"],
            )
            pos = position_bank[:, lo] * (1 - weight) + position_bank[:, hi] * weight
            vel = velocity_bank[:, lo] * (1 - weight) + velocity_bank[:, hi] * weight
            unit = pos - rec
            ranges = np.linalg.norm(unit, axis=-1)
            unit /= ranges[..., None]
            prediction = (
                -numerical.REFERENCE_RF_HZ / numerical.LIGHT_KM_S * np.sum(unit * vel, axis=-1)
            )
            visible = np.any((unit @ up)[:, :, track["mask"]] >= 0, axis=2)
            count = visible.sum(axis=0)
            if np.any(count == 0):
                raise ValueError("No visible retained candidate during timing integration")
            mask = track["mask"]
            residual = track["y"][None, None, mask] - prediction[:, :, mask]
            density, influence = contrast_density(residual.reshape(-1, int(mask.sum())))
            density = density.reshape(prediction.shape[:2])
            influence = influence.reshape(residual.shape)
            signal = logsumexp(np.where(visible, density, -np.inf), axis=0) - np.log(count)
            normal = np.logaddexp(
                math.log(0.8) + signal, math.log(0.2) + model.background[0, ti][0]
            )
            score += normal
            probabilities = np.exp(
                np.where(visible, density, -np.inf) + math.log(0.8) - np.log(count) - normal
            )
            transverse = vel - unit * np.sum(unit * vel, axis=-1)[..., None]
            for axis in range(2):
                dp = (
                    numerical.REFERENCE_RF_HZ
                    / numerical.LIGHT_KM_S
                    * (transverse @ rec_derivatives[axis])
                    / ranges
                )
                component = np.sum(influence * dp[:, :, mask], axis=2)
                derivative[:, axis] += np.sum(probabilities * component, axis=0)
        result[start : start + len(t)] = score
        gradient[start : start + len(t)] = derivative
    return result, gradient


def marginal(model, position, order):
    nodes, weights = timing_nodes(order, model.models[0].taus)
    scores, gradients = training_scores(model, position, nodes)
    score = log_integral(scores, weights)
    gradient = np.exp(scores + weights - score) @ gradients
    return score, gradient
