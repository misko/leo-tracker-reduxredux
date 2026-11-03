"""Bounded source-cell finite-difference inventory; no optimizer."""

import numpy as np

STEPS = (1e-5, 1e-6, 1e-7)


def choose(step_is_valid):
    """Choose before scoring: central else same-source-cell second-order side."""
    for h in STEPS:
        if step_is_valid(-h) and step_is_valid(h):
            return dict(kind="central", h=h, offsets=[-h, h])
        for sign in (1.0, -1.0):
            if step_is_valid(sign * h) and step_is_valid(2 * sign * h):
                return dict(
                    kind="one-sided-source-cell", h=sign * h, offsets=[sign * h, 2 * sign * h]
                )
    raise ValueError("No feasible stable source-cell stencil; direction not omitted")


def finite_difference(f0, values, stencil):
    h = stencil["h"]
    if stencil["kind"] == "central":
        return (values[1] - values[0]) / (2 * h)
    return (-3 * f0 + 4 * values[0] - values[1]) / (2 * h)


def tolerance(f0, analytic, stencil):
    """Fixed scaled-gradient gate plus explicit scalar-J floating-point floor."""
    ulp = float(abs(np.spacing(float(f0))))
    return max(1e-3, 1e-5 * abs(float(analytic)), 32 * ulp / abs(stencil["h"]))
