"""Research elevation geometry using the production linear position interpolator."""

import numpy as np

from leo.analysis.regional_position_score import observer


def predict_elevation(bank, observations, prior, point, shifts_s):
    shifts = np.asarray(shifts_s, dtype=float)
    if shifts.shape != (len(bank.numbers),) or not np.isfinite(shifts).all():
        raise ValueError("one finite shift per satellite required")
    query = observations.times_s[:, None] + shifts[None, :]
    if np.any(query < bank.nodes_s[0]) or np.any(query > bank.nodes_s[-1]):
        raise ValueError("orbit query outside support")
    step = bank.nodes_s[1] - bank.nodes_s[0]
    fraction = (query - bank.nodes_s[0]) / step
    lower = np.minimum(np.floor(fraction).astype(int), len(bank.nodes_s) - 2)
    sat = np.arange(len(bank.numbers))[None, :]
    p0, p1 = bank.position_km[sat, lower], bank.position_km[sat, lower + 1]
    position = p0 + (fraction - lower)[..., None] * (p1 - p0)
    site, up = observer(prior, point)
    delta = position - site
    distance = np.linalg.norm(delta, axis=2)
    if np.any(distance <= 0):
        raise ValueError("satellite coincides with observer")
    direction = delta / distance[..., None]
    sine = np.clip(np.sum(direction * up, axis=2), -1, 1)
    elevation = np.degrees(np.arcsin(sine))
    chart = [
        (
            np.asarray(observer(prior, np.asarray(point) + d))
            - np.asarray(observer(prior, np.asarray(point) - d))
        )
        / 0.002
        for d in np.eye(2) * 0.001
    ]
    site_jac, up_jac = np.asarray(chart)[:, 0], np.asarray(chart)[:, 1]
    tangent = up - sine[..., None] * direction
    spatial_sine = -np.einsum("nka,ia->nki", tangent / distance[..., None], site_jac)
    spatial_sine += np.einsum("nka,ia->nki", direction, up_jac)
    timing_sine = np.sum(tangent * ((p1 - p0) / step), axis=2) / distance
    # Elevation itself has no unique derivative at exact zenith/nadir. The
    # horizon taper is constant there; use zero for its eventual chain rule.
    factor = np.zeros_like(sine)
    nonsingular = abs(sine) < 1
    factor[nonsingular] = 180 / np.pi / np.sqrt(1 - sine[nonsingular] ** 2)
    return elevation, spatial_sine * factor[..., None], timing_sine * factor
