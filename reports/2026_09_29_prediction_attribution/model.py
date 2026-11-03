"""Track-wise replay and an exact posterior/entropy decomposition."""

import math

import ds7_baseline_adapter as numerical
import numpy as np
from scipy.special import logsumexp
from trend_mixture import contrast_density


def track_scores(model, position, times):
    engine = model.models[0]
    rec, up = numerical.site(*engine.coordinates([*position, 0.0]))
    grid = engine.taus
    times = np.asarray(times)
    tracks = model.documents[0]["tracks"]
    result = np.empty((len(times), len(tracks)))
    responsibility = np.empty_like(result)
    for start in range(0, len(times), 32):
        t = times[start : start + 32]
        hi = np.clip(np.searchsorted(grid, t, side="right"), 1, len(grid) - 1)
        lo = hi - 1
        weight = ((t - grid[lo]) / (grid[hi] - grid[lo]))[None, :, None, None]
        for ti, track in enumerate(tracks):
            pb, vb = track["candidate_position_km"], track["candidate_velocity_km_s"]
            pos = pb[:, lo] * (1 - weight) + pb[:, hi] * weight
            vel = vb[:, lo] * (1 - weight) + vb[:, hi] * weight
            unit = pos - rec
            unit /= np.linalg.norm(unit, axis=-1)[..., None]
            prediction = (
                -numerical.REFERENCE_RF_HZ / numerical.LIGHT_KM_S * np.sum(unit * vel, axis=-1)
            )
            visible = np.any((unit @ up)[:, :, track["mask"]] >= 0, axis=2)
            count = visible.sum(axis=0)
            if np.any(count == 0):
                raise ValueError("No visible retained candidate")
            residual = track["y"][None, None, :] - prediction
            density, _ = contrast_density(residual.reshape(-1, len(track["y"])))
            density = density.reshape(prediction.shape[:2])
            signal = (
                math.log(0.8)
                + logsumexp(np.where(visible, density, -np.inf), axis=0)
                - np.log(count)
            )
            total = np.logaddexp(signal, math.log(0.2) + model.background[0, ti][1])
            result[start : start + len(t), ti] = total
            responsibility[start : start + len(t), ti] = np.exp(signal - total)
    return result, responsibility


def decompose(scores, logprior, responsibility):
    scores = np.asarray(scores)
    logprior = np.asarray(logprior)
    assert abs(logsumexp(logprior)) < 1e-10
    logjoint = scores.sum(axis=1) + logprior
    evidence = float(logsumexp(logjoint))
    logposterior = logjoint - evidence
    posterior = np.exp(logposterior)
    expected = posterior @ scores
    kl = float(posterior @ (logposterior - logprior))
    error = abs(float(expected.sum()) - kl - evidence)
    assert error < 1e-7
    return dict(
        log_score=evidence,
        expected_tracks=expected.tolist(),
        kl=kl,
        signal_responsibility=(posterior @ responsibility).tolist(),
        reconstruction_error=error,
    )
