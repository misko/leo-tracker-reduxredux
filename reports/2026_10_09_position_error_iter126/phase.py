"""Pure constant-rate relative-phase frame prototype, not production physics."""

import numpy as np

from leo.sky.frames import EARTH_ROTATION_RATE_RAD_S


def rotate(vector, angle):
    vector = np.asarray(vector, dtype=float)
    c, s = np.cos(angle), np.sin(angle)
    return np.stack(
        (
            c * vector[..., 0] - s * vector[..., 1],
            s * vector[..., 0] + c * vector[..., 1],
            vector[..., 2],
        ),
        axis=-1,
    )


def transformed(state, secant, relative_s):
    """State may be position or velocity; its own independent secant required."""
    state = np.asarray(state, dtype=float)
    secant = np.asarray(secant, dtype=float)
    angle = EARTH_ROTATION_RATE_RAD_S * relative_s
    value = rotate(state, angle)
    common = rotate(secant, angle)
    cross = EARTH_ROTATION_RATE_RAD_S * np.stack(
        (-state[..., 1], state[..., 0], np.zeros_like(state[..., 2])), axis=-1
    )
    return value, common, rotate(secant + cross, angle)


def radial(position, velocity, site, site_jacobian):
    delta = np.asarray(position) - np.asarray(site)
    distance = np.linalg.norm(delta, axis=-1)
    direction = delta / distance[..., None]
    rate = np.sum(direction * velocity, axis=-1)
    spatial = (
        -(np.asarray(velocity) - rate[..., None] * direction)
        / distance[..., None]
        @ np.asarray(site_jacobian).T
    )
    return rate, spatial
