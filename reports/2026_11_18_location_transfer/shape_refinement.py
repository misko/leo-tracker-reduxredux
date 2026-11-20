"""Refine the strongest coarse cell using the same Doppler score as the grid peak."""

import numpy as np


def refine(start, step, limit, score):
    best = np.asarray(start, dtype=float)
    best_score = float(score(best[None, :])[0])
    for divisor in (4., 16.):
        shifts = np.arange(-2,3) * step / divisor
        offsets = np.stack(np.meshgrid(shifts, shifts), axis=-1).reshape(-1, 2)
        points = np.unique(np.clip(best+offsets, -limit, limit), axis=0)
        values = score(points)
        i = int(np.argmax(values))
        if values[i] > best_score:
            best, best_score = points[i], float(values[i])
    return best


def doppler_peak(network, field, rows):
    def score(xy):
        design = np.column_stack((np.ones(len(xy)), -xy))
        losses = [network.scores(marginal, design).min(axis=0) for marginal, *_ in rows]
        return (1./(1. + np.asarray(losses)/4.)).mean(axis=0)
    start = network.GRID[np.argmax(field)]
    return refine(start, 2.*network.LIMIT/6., network.LIMIT, score)
