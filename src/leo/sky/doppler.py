"""Predicted Doppler shift and its polynomial form.

Pure numerical code.  The polynomial is expressed as derivatives of the shift at
a reference instant so that it lines up with the degree-1/2/3 CFO trajectories
the Standard pipeline already fits to observed signals.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from leo.contracts.sky import DopplerPolynomialV1

# CODATA speed of light in vacuum, kilometres per second.
SPEED_OF_LIGHT_KM_S = 299_792.458


def doppler_shift_hz(
    downlink_frequency_hz: float, range_rate_km_s: NDArray[np.float64] | float
) -> NDArray[np.float64]:
    """Return the received-minus-transmitted shift for a receding-positive rate.

    From ``f_rx = f_tx * (1 - range_rate / c)`` the shift is
    ``-f_tx * range_rate / c``: positive while the object approaches, negative
    while it recedes.  The classical first-order form is used deliberately; the
    relativistic correction at orbital speeds is parts in 1e10, far below the
    error contributed by element-set age.
    """

    if not np.isfinite(downlink_frequency_hz) or downlink_frequency_hz <= 0.0:
        raise ValueError("downlink frequency must be finite and positive")
    rate = np.asarray(range_rate_km_s, dtype=np.float64)
    return -downlink_frequency_hz * rate / SPEED_OF_LIGHT_KM_S


def fit_doppler_polynomial(
    offsets_s: NDArray[np.float64],
    shift_hz: NDArray[np.float64],
    *,
    downlink_frequency_hz: float,
    reference_utc_ns: int,
    degree: int = 3,
) -> DopplerPolynomialV1:
    """Fit the shift over a window and return its derivatives at the reference.

    ``offsets_s`` are seconds relative to ``reference_utc_ns`` and must contain
    the reference itself.  The requested degree is reduced when there are too
    few knots to determine it, so a short window yields an honest lower-order
    fit rather than an overdetermined one.
    """

    if not 1 <= degree <= 3:
        raise ValueError("Doppler polynomial degree must be 1, 2 or 3")
    offsets = np.asarray(offsets_s, dtype=np.float64)
    shift = np.asarray(shift_hz, dtype=np.float64)
    if offsets.shape != shift.shape or offsets.ndim != 1:
        raise ValueError("Doppler samples must be one-dimensional and equal length")
    if not np.isfinite(offsets).all() or not np.isfinite(shift).all():
        raise ValueError("Doppler samples must be finite")

    effective_degree = min(degree, offsets.size - 1)
    if effective_degree < 1:
        raise ValueError("a Doppler polynomial needs at least two samples")

    # Ascending-power coefficients of shift(t) about the reference instant.
    coefficients = np.polynomial.polynomial.polyfit(offsets, shift, effective_degree)
    modelled = np.polynomial.polynomial.polyval(offsets, coefficients)
    residual_rms = float(np.sqrt(np.mean((shift - modelled) ** 2)))
    padded = np.zeros(4, dtype=np.float64)
    padded[: coefficients.size] = coefficients

    # Convert ascending-power coefficients into derivatives at the reference:
    # a Taylor term c_n * t**n contributes n! * c_n to the n-th derivative.
    return DopplerPolynomialV1(
        degree=effective_degree,  # type: ignore[arg-type]
        reference_utc_ns=reference_utc_ns,
        downlink_frequency_hz=downlink_frequency_hz,
        frequency_at_reference_hz=float(padded[0]),
        slope_hz_s=float(padded[1]),
        acceleration_hz_s2=float(2.0 * padded[2]),
        jerk_hz_s3=float(6.0 * padded[3]),
        residual_rms_hz=residual_rms,
    )


def evaluate_doppler_polynomial(
    polynomial: DopplerPolynomialV1, offsets_s: NDArray[np.float64] | float
) -> NDArray[np.float64]:
    """Evaluate a fitted polynomial at offsets from its reference instant."""

    offsets = np.asarray(offsets_s, dtype=np.float64)
    return (
        polynomial.frequency_at_reference_hz
        + polynomial.slope_hz_s * offsets
        + polynomial.acceleration_hz_s2 * offsets**2 / 2.0
        + polynomial.jerk_hz_s3 * offsets**3 / 6.0
    )
