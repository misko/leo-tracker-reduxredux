"""Low-rank orbital uncertainty with explicit marginal covariance volume.

This module does not choose satellite identities or uncertainty scales. A
causal prediction disagreement is not, by itself, calibrated covariance.
"""

import numpy as np

from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km


def project_constant_features(raw, features, inverse, *, bias_sigma=1000.0):
    """Apply the Gaussian-constant Schur square root to data and shared modes.

    The augmented coordinates have n+1 rows but represent n observations.
    Their norm equals the marginalized quadratic, including the bias prior.
    """
    y, u, w = (np.asarray(a, float) for a in (raw, features, inverse))
    if y.ndim != 1 or u.ndim != 2 or u.shape[0] != len(y) or w.shape != (len(y), len(y)):
        raise ValueError("matching observation, mode and whitening dimensions required")
    if (
        not all(np.isfinite(a).all() for a in (y, u, w))
        or not np.isfinite(bias_sigma)
        or bias_sigma <= 0
    ):
        raise ValueError("finite inputs and positive Gaussian bias scale required")
    z, wu = w @ y, w @ u
    one = w @ np.ones(len(y))
    denominator = one @ one + 1 / bias_sigma**2
    bias = one @ z / denominator
    mode_bias = one @ wu / denominator
    r = np.r_[z - bias * one, bias / bias_sigma]
    modes = np.vstack((wu - one[:, None] * mode_bias, mode_bias[None, :] / bias_sigma))
    return r, modes, float(np.log1p(bias_sigma**2 * (one @ one)))


def low_rank_marginal(
    residual, modes, observations, *, degrees_of_freedom=None, base_logvolume=0.0
):
    """Whiten I+UU' and include its log-determinant; rank-sized linear algebra.

    Returns a Gaussian or multivariate Student-t objective up to constants
    independent of the parameters, plus conditional-mean mode coefficients.
    Student-t conditioning has the same coefficient mean as the Gaussian;
    its uncertainty scale is different and is not returned as confidence.
    """
    r, u = np.asarray(residual, float), np.asarray(modes, float)
    if r.ndim != 1 or u.ndim != 2 or u.shape[0] != len(r) or observations <= 0:
        raise ValueError("matching residual/modes and positive observation count required")
    if (
        not np.isfinite(r).all()
        or not np.isfinite(u).all()
        or not np.isfinite(base_logvolume)
        or base_logvolume < 0
    ):
        raise ValueError("finite inputs and nonnegative covariance volume required")
    gram = u.T @ u
    values, vectors = np.linalg.eigh(gram)
    values = np.maximum(0, values)
    rhs = u.T @ r
    root = np.sqrt(1 + values)
    factor = -1 / (root * (1 + root))
    white = r + u @ (vectors @ (factor * (vectors.T @ rhs)))
    quadratic = float(white @ white)
    coefficient = np.linalg.solve(np.eye(len(gram)) + gram, rhs)
    volume = float(base_logvolume + np.log1p(values).sum())
    if degrees_of_freedom is not None:
        nu = degrees_of_freedom
        if not np.isfinite(nu) or nu <= 0:
            raise ValueError("positive finite Student degrees of freedom required")
        energy = (nu + observations) * np.log1p(quadratic / nu)
        scale = (
            np.sqrt(energy / quadratic) if quadratic > 1e-16 else np.sqrt((nu + observations) / nu)
        )
        white = white * scale
    return dict(
        residual=np.r_[white, np.sqrt(volume)],
        coefficient=coefficient,
        quadratic=quadratic,
        logvolume=volume,
        posterior_gaussian_covariance=np.linalg.inv(np.eye(len(gram)) + gram),
    )


def paired_frequency_modes(
    bank, mode_bank, times, labels, phases, latitude, longitude, *, altitude_m=0.0
):
    """First-order CFO modes with the same orbital phase and Earth rotation.

    mode_bank flattens (satellite, mode) in its satellite dimension. Modes are
    ECEF position and velocity deviations, including their physical time rate.
    """
    position, velocity = paired_phase_states(bank, times, labels, phases)
    satellites = len(np.asarray(phases))
    count = np.asarray(mode_bank["position_km"]).shape[0] // satellites
    if count < 1 or count * satellites != np.asarray(mode_bank["position_km"]).shape[0]:
        raise ValueError("equal positive mode count per satellite required")
    expanded = (np.asarray(labels)[:, None] * count + np.arange(count)).ravel()
    dp, dv = paired_phase_states(
        mode_bank, np.repeat(times, count), expanded, np.repeat(phases, count)
    )
    dp, dv = dp.reshape(-1, count, 3), dv.reshape(-1, count, 3)
    line = position - geodetic_to_ecef_km(latitude, longitude, altitude_m)
    distance = np.linalg.norm(line, axis=1)
    direction = line / distance[:, None]
    rate = np.sum(direction * velocity, axis=1)
    position_gradient = (velocity - rate[:, None] * direction) / distance[:, None]
    derivative = np.einsum("nd,nkd->nk", position_gradient, dp) + np.einsum(
        "nd,nkd->nk", direction, dv
    )
    return -11.5e9 / 299792.458 * derivative
