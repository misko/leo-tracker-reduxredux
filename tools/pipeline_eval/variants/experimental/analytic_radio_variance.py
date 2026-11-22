"""Refine the released radio variance profile inside its original grid basin."""

from functools import partial
from itertools import pairwise

import numpy as np
from scipy.optimize import brentq

LOWER = 1600.
UPPER = 360000.
GRID = np.r_[0., np.geomspace(1e-6, UPPER / LOWER, 257)]
SMOOTH_POINTS = 9


class RadioProfile:
    def __init__(self, margins, squares):
        self.m, self.y = np.asarray(margins), np.asarray(squares)
        if (self.m.ndim != 1 or self.y.shape != self.m.shape or not len(self.m)
                or np.any(self.m <= 0) or np.any(self.y < 0)):
            raise ValueError("positive margins and nonnegative squared residuals required")
        if not np.isfinite(self.m).all() or not np.isfinite(self.y).all():
            raise ValueError("finite noise observations required")

    def mean_scaled_square(self, ratio):
        return np.mean(self.y / (1 + ratio / self.m))

    def profile(self, ratio, *, dtype=None):
        m, y = self.m, self.y
        if dtype is not None:
            m, y, ratio = m.astype(dtype), y.astype(dtype), dtype(ratio)
        shape = 1 + ratio / m
        maximum = min(UPPER, UPPER / ratio) if ratio else UPPER
        floor = np.clip(np.mean(y / shape), LOWER, maximum)
        variance = floor * shape
        return np.mean(np.log(variance) + y / variance), np.array([floor, floor * ratio])

    def gradient(self, ratio, *, moving_cap):
        shape = 1 + ratio / self.m
        average = np.mean(self.y / shape)
        maximum = UPPER / ratio if moving_cap else UPPER
        floor = np.clip(average, LOWER, maximum)
        log_slope = 1 / (self.m + ratio)
        if moving_cap and average >= maximum:
            # The strength is fixed at UPPER, so log(v)' is negative.
            log_slope *= -self.m / ratio
        # An interior floor has zero profile derivative in its own direction.
        return float(np.mean((1 - self.y / (floor * shape)) * log_slope))


def opposite_sign(left, right):
    return (left < 0 < right) or (right < 0 < left)


def root(function, left, right):
    return brentq(function, left, right, xtol=np.finfo(float).tiny,
                  rtol=4 * np.finfo(float).eps)


def smooth_intervals(profile, left, right):
    # The upper cap is constant to the left of 1 and decreases to its right.
    limits = [left, 1., right] if left < 1 < right else [left, right]
    intervals = []
    for a, b in pairwise(limits):
        moving_cap = a >= 1.
        breaks = [a, b]

        def lower(r):
            return profile.mean_scaled_square(r) - LOWER

        def upper(r, moving_cap=moving_cap):
            return profile.mean_scaled_square(r) * (r if moving_cap else 1.) - UPPER

        # The unconstrained floor decreases monotonically. On the upper
        # moving side the implied unconstrained strength increases.
        for transition in (lower, upper):
            if opposite_sign(transition(a), transition(b)):
                breaks.append(root(transition, a, b))
        breaks.sort()
        intervals.extend((lo, hi, moving_cap) for lo, hi in pairwise(breaks))
    return intervals


def fit_variance(margins, squares):
    profile = RadioProfile(margins, squares)
    best = int(np.argmin([profile.profile(r)[0] for r in GRID]))
    left, right = GRID[max(0, best - 1)], GRID[min(len(GRID) - 1, best + 1)]
    eligible = {left, right}
    for lo, hi, moving_cap in smooth_intervals(profile, left, right):
        eligible.update((lo, hi))

        slope = partial(profile.gradient, moving_cap=moving_cap)
        mesh = np.linspace(lo, hi, SMOOTH_POINTS)
        slopes = [slope(r) for r in mesh]
        eligible.update(r for r, value in zip(mesh, slopes, strict=True) if value == 0)
        for (a, b), (ga, gb) in zip(pairwise(mesh), pairwise(slopes), strict=True):
            if ga < 0 < gb:
                eligible.add(root(slope, a, b))
    winner = min(sorted(eligible), key=lambda r: profile.profile(r, dtype=np.longdouble)[0])
    return profile.profile(winner)[1]
