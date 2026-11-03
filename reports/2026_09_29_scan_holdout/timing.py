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


def full_scores(model, position, times):
    """Batched scalar-oracle-equivalent complete-scan q020 log likelihood."""
    assert len(model.documents) == 1
    engine = model.models[0]
    rec, up = numerical.site(*engine.coordinates([*position, 0.0]))
    grid = engine.taus
    times = np.asarray(times)
    result = np.zeros(len(times))
    for start in range(0, len(times), 32):
        t = times[start : start + 32]
        hi = np.clip(np.searchsorted(grid, t, side="right"), 1, len(grid) - 1)
        lo = hi - 1
        weight = ((t - grid[lo]) / (grid[hi] - grid[lo]))[None, :, None, None]
        score = np.zeros(len(t))
        for ti, track in enumerate(model.documents[0]["tracks"]):
            position_bank, velocity_bank = (
                track["candidate_position_km"],
                track["candidate_velocity_km_s"],
            )
            pos = position_bank[:, lo] * (1 - weight) + position_bank[:, hi] * weight
            vel = velocity_bank[:, lo] * (1 - weight) + velocity_bank[:, hi] * weight
            unit = pos - rec
            unit /= np.linalg.norm(unit, axis=-1)[..., None]
            prediction = (
                -numerical.REFERENCE_RF_HZ / numerical.LIGHT_KM_S * np.sum(unit * vel, axis=-1)
            )
            visible = np.any((unit @ up)[:, :, track["mask"]] >= 0, axis=2)
            count = visible.sum(axis=0)
            if np.any(count == 0):
                raise ValueError("No visible retained candidate during timing integration")
            residual = track["y"][None, None, :] - prediction
            density, _ = contrast_density(residual.reshape(-1, len(track["y"])))
            density = density.reshape(prediction.shape[:2])
            signal = logsumexp(np.where(visible, density, -np.inf), axis=0) - np.log(count)
            score += np.logaddexp(
                math.log(0.8) + signal, math.log(0.2) + model.background[0, ti][1]
            )
        result[start : start + len(t)] = score
    return result


def marginal_scan(model, position):
    replay_times = np.array([-5.0, -2.375, 0.0, 1.125, 5.0])
    batched = full_scores(model, position, replay_times)
    scalar = []
    for t in replay_times:
        out = model.evaluate([*position, t], gradient=False, held=True)
        scalar.append(out["score"] + sum(r["held_log_score"] for r in out["rows"]))
    error = float(max(abs(batched - scalar)))
    assert error < 1e-7
    values = []
    for order in (16, 32):
        nodes, weights = timing_nodes(order, model.models[0].taus)
        scores = full_scores(model, position, nodes)
        values.append(log_integral(scores, weights))
    difference = abs(values[0] - values[1])
    return dict(
        log_score=values[0],
        audit_log_score=values[1],
        quadrature_difference=difference,
        scalar_replay_error=error,
        qualified=bool(difference <= 0.01),
    )
