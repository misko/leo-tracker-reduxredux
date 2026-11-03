"""Noncoherent multi-frame pilot frequency with matched held prediction."""

import numpy as np
from scipy.optimize import minimize_scalar

TS = 4.4e-6
GAIN = np.arange(20, 220)
HELD = np.arange(220, 300)


def fit(y, indices):
    values = y[:, indices]

    def loss(f):
        gains = np.mean(values * np.exp(-2j * np.pi * f * indices * TS)[None, :, None], axis=1)
        return -float(np.sum(abs(gains) ** 2))

    grid = np.arange(-1500.0, 1500.1, 25.0)
    scores = np.array([loss(f) for f in grid])
    i = int(np.argmin(scores))
    choices = [(float(scores[i]), float(grid[i]))]
    if 0 < i < len(grid) - 1:
        r = minimize_scalar(loss, bounds=(grid[i - 1], grid[i + 1]), method="bounded")
        assert r.success
        choices.append((float(r.fun), float(r.x)))
    return min(choices)[1]


def errors(y, f):
    gain = np.mean(y[:, GAIN] * np.exp(-2j * np.pi * f * GAIN * TS)[None, :, None], axis=1)
    pred = gain[:, None, :] * np.exp(2j * np.pi * f * HELD * TS)[None, :, None]
    return np.sum(abs(y[:, HELD] - pred) ** 2, axis=(1, 2)) / np.maximum(
        np.sum(abs(y[:, HELD]) ** 2, axis=(1, 2)), 1e-30
    )
