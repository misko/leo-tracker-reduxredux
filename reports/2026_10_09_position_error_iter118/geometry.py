"""Source-only geometric horizon primitive; no orbit loader or selected width."""

import numpy as np


def horizon_margin(position, position_rate, site, up, site_jacobian, up_jacobian):
    """Return sin(elevation), spatial derivative /km, and orbit-shift derivative /s.

    position_rate must be the derivative of the interpolated position, not the
    separately interpolated physical velocity. Spatial Jacobians have shape (2,3).
    Arrays may have arbitrary leading dimensions. The up vector is ellipsoid-normal.
    """
    position, rate, site, up, dr, du = map(
        lambda x: np.asarray(x, dtype=float),
        (position, position_rate, site, up, site_jacobian, up_jacobian),
    )
    if (
        position.shape != rate.shape
        or position.shape[-1:] != (3,)
        or site.shape != (3,)
        or up.shape != (3,)
        or dr.shape != (2, 3)
        or du.shape != (2, 3)
        or not all(np.isfinite(x).all() for x in (position, rate, site, up, dr, du))
        or not np.isclose(np.linalg.norm(up), 1, rtol=0, atol=1e-12)
    ):
        raise ValueError("finite geometry and unit normal required")
    delta = position - site
    distance = np.linalg.norm(delta, axis=-1)
    if np.any(distance == 0):
        raise ValueError("satellite coincides with observer")
    direction = delta / distance[..., None]
    margin = direction @ up
    tangent = (up - margin[..., None] * direction) / distance[..., None]
    spatial = -tangent @ dr.T + direction @ du.T
    timing = np.sum(tangent * rate, axis=-1)
    return margin, spatial, timing


def positive_horizon_gate(margin, width_sine):
    """C1 compact gate: exactly zero below horizon, one above supplied width.

    Width is caller-provided physical-model input, never inferred here. This is a
    candidate detectability law, not a TLE uncertainty distribution.
    """
    if not np.isfinite(width_sine) or not 0 < width_sine <= 1:
        raise ValueError("positive finite sine-elevation width required")
    margin = np.asarray(margin, dtype=float)
    if not np.isfinite(margin).all():
        raise ValueError("finite margins required")
    x = np.clip(margin / width_sine, 0, 1)
    return x * x * (3 - 2 * x), 6 * x * (1 - x) / width_sine
