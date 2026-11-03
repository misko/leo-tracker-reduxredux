"""Normalized fixed-state availability control, with no data/model adapter."""

import math
from dataclasses import dataclass

import numpy as np
from scipy.special import ndtr

ALIAS_HZ = 1.0 / 4.4e-6
TAIL_TOLERANCE = 1e-14
TOTAL_Q = 1.6


@dataclass(frozen=True)
class PointTerms:
    nll: float
    row_nll: np.ndarray
    selected_responsibility: np.ndarray
    unsupported_responsibility: np.ndarray
    clutter_probability: np.ndarray
    selected_mean_gradient: np.ndarray
    unsupported_mean_gradient: np.ndarray
    selected_sigma_gradient: np.ndarray
    unsupported_sigma_gradient: np.ndarray
    selected_visibility_gradient: np.ndarray
    unsupported_visibility_gradient: np.ndarray
    selected_q_gradient: np.ndarray
    base_sigma_gradient: float
    relative_sigma_gradient: float
    selected_q: np.ndarray
    unsupported_q: np.ndarray
    unsupported_sigma_hz: np.ndarray
    best_is_unsupported: np.ndarray
    best_index: np.ndarray
    associated: np.ndarray
    residual_hz: np.ndarray
    diagnostics: dict


def circular(value, alias_hz):
    return (value + alias_hz / 2) % alias_hz - alias_hz / 2


def _image_bounds(radius, sigma, alias):
    ratio = alias / sigma
    t = (radius + 0.5) * ratio
    # Underflow is replaced by a conservative normal-scale bound.
    c = math.exp(max(-0.5 * t * t, math.log(np.finfo(float).tiny)))
    r = math.exp(-ratio * ratio * (radius + 1))
    s0 = c / (1 - r)
    s1 = c * (t / (1 - r) + ratio * r / (1 - r) ** 2)
    s2 = c * (
        t * t / (1 - r)
        + 2 * t * ratio * r / (1 - r) ** 2
        + ratio * ratio * r * (1 + r) / (1 - r) ** 3
    )
    factor = 2 / math.sqrt(2 * math.pi)
    return dict(
        density_times_alias=factor * s0 * alias / sigma,
        mean_derivative_times_alias_squared=factor * s1 * (alias / sigma) ** 2,
        sigma_derivative_times_alias_squared=factor * (s2 + s0) * (alias / sigma) ** 2,
        integrated_mass_error=max(2 * float(ndtr(-t)), np.finfo(float).tiny),
    )


def _uniform_bounds(sigma_ratio):
    # Fourier tails only certify replacing a VERY broad wrapped normal by U.
    # The component evaluates finite Gaussian images for every narrower width.
    x = min(float(sigma_ratio), 10.0)
    a = 2 * math.pi**2 * x * x
    c = math.exp(max(-a, math.log(np.finfo(float).tiny)))
    r = math.exp(-3 * a)
    s0 = c / (1 - r)
    s1 = c * (1 / (1 - r) + r / (1 - r) ** 2)
    s2 = c * (1 / (1 - r) + 2 * r / (1 - r) ** 2 + r * (1 + r) / (1 - r) ** 3)
    return dict(
        density_times_alias=2 * s0,
        mean_derivative_times_alias_squared=4 * math.pi * s1,
        sigma_derivative_times_alias_squared=8 * math.pi**2 * x * s2,
        integrated_mass_error=0.0,
        integrated_absolute_error=2 * s0,
    )


def wrapped_normal(residual_hz, sigma_hz, *, alias_hz=ALIAS_HZ):
    """Wrapped Gaussian and mean/sigma derivatives with numerical tail bounds.

    Derivative 'mean' is with respect to prediction mean, not residual. Images
    are summed directly (principal first) to preserve the narrow legacy kernel.
    Width >=2*alias uses U with an analytic Fourier-tail certificate. Returned
    bounds are absolute errors scaled by alias / alias squared, respectively.
    """
    residual, sigma = np.broadcast_arrays(
        np.asarray(residual_hz, float), np.asarray(sigma_hz, float)
    )
    if not np.isfinite(alias_hz) or alias_hz <= 0 or np.any(~np.isfinite(residual)):
        raise ValueError("Finite circular residual and positive alias width required")
    if np.any(~np.isfinite(sigma)) or np.any(sigma <= 0):
        raise ValueError("Finite positive Gaussian widths required")
    residual = circular(residual, alias_hz)
    value, mean_gradient, sigma_gradient = (np.zeros_like(residual) for _ in range(3))
    broad = sigma >= 2 * alias_hz
    value[broad] = 1 / alias_hz
    reports = []
    if broad.any():
        reports.append(
            dict(method="uniform-bounded", **_uniform_bounds(float(sigma[broad].min() / alias_hz)))
        )
    narrow = ~broad
    if narrow.any():
        maximum_sigma = float(sigma[narrow].max())
        radius = max(1, int(math.ceil(9 * maximum_sigma / alias_hz - 0.5)))
        bound = _image_bounds(radius, maximum_sigma, alias_hz)
        while max(bound.values()) > TAIL_TOLERANCE:
            radius += 1
            if radius > 128:
                raise FloatingPointError("Unable to certify finite-image tails")
            bound = _image_bounds(radius, maximum_sigma, alias_hz)
        reports.append(dict(method="finite-images", radius=radius, **bound))
        r, s = residual[narrow], sigma[narrow]
        phi, dmean, dsigma = (np.zeros_like(r) for _ in range(3))
        for image in [0] + [m for i in range(1, radius + 1) for m in (-i, i)]:
            with np.errstate(over="ignore", under="ignore", invalid="raise"):
                z = (r + image * alias_hz) / s
                gaussian = np.exp(-0.5 * z * z) / (s * np.sqrt(2 * np.pi))
            if np.any(~np.isfinite(gaussian)):
                raise FloatingPointError("Gaussian density overflow")
            active = gaussian > 0
            phi += gaussian
            with np.errstate(over="raise", invalid="raise"):
                dmean[active] += gaussian[active] * z[active] / s[active]
                dsigma[active] += gaussian[active] * (z[active] ** 2 - 1) / s[active]
        value[narrow], mean_gradient[narrow], sigma_gradient[narrow] = phi, dmean, dsigma
    for report in reports:
        if any(v > TAIL_TOLERANCE for k, v in report.items() if k not in ("method", "radius")):
            raise FloatingPointError("Wrapped-normal approximation exceeds declared tail bound")
    return value, mean_gradient, sigma_gradient, reports


def unsupported_peak_ceiling(
    count, *, eta=0.10, total_q=TOTAL_Q, sigma_hz=125.0, clutter_rate=0.5, alias_hz=ALIAS_HZ
):
    """Upper bound on one unsupported signal/clutter ratio, not a probability.

    A wrapped Gaussian's peak decreases with width. Every marginalized width
    is >=sigma_hz, and visibility is <=1. The bound is therefore independent
    of observed CFO, unsupported means, timing slopes and fitted parameters.
    """
    if not isinstance(count, (int, np.integer)) or count < 0:
        raise ValueError("Nonnegative integer population count required")
    if eta not in (0.0, 0.10) or not np.isfinite(clutter_rate) or clutter_rate <= 0:
        raise ValueError("Declared eta and positive clutter rate required")
    if count == 0 or eta == 0:
        return 0.0
    q = eta * total_q / count
    if count < 0 or not 0 < q < 1:
        raise ValueError("Valid population count/mass required")
    phi, _, _, bounds = wrapped_normal(np.array([0.0]), np.array([sigma_hz]), alias_hz=alias_hz)
    error = max((r["density_times_alias"] for r in bounds), default=0.0) / alias_hz
    return float(q / (1 - q) * (phi[0] + error) / (clutter_rate / alias_hz))


def evaluate(
    measured,
    selected_means,
    selected_visibility,
    selected_q,
    unsupported_means,
    unsupported_visibility,
    timing_slope,
    *,
    eta=0.10,
    sigma_hz=125.0,
    sigma_relative_s=2.0,
    clutter_rate=0.5,
    alias_hz=ALIAS_HZ,
):
    """One proper mark PDF, numerically evaluated to the declared tail bound.

    Q=1.6 is fixed. q_selected'=(1-eta)q; q_unsupported'=eta*Q/M.
    M=0 forces effective eta=0. Only eta=0/.10 are declared controls. The q
    gradient treats Q fixed, appropriate to the existing fixed-budget chart.
    No unsupported masses, eta, timing slope, position or visibility is fitted.
    Sigma gradients refer to each component's effective width. Scalar base
    and relative-width derivatives additionally include the hypot chain rule.
    Catalogue IDs are caller-owned: best_index is within the selected or
    unsupported bank according to best_is_unsupported. No reference is used.
    """
    y, mu, w, q, umu, uw, g = map(
        np.asarray,
        (
            measured,
            selected_means,
            selected_visibility,
            selected_q,
            unsupported_means,
            unsupported_visibility,
            timing_slope,
        ),
    )
    if y.ndim != 1 or mu.ndim != 2 or mu.shape[0] != len(y) or mu.shape[1] < 2:
        raise ValueError("Nonempty aligned measured[N], selected means[N,I] required")
    n, k = mu.shape
    if not n or w.shape != mu.shape or q.shape != (k,) or umu.ndim != 2 or umu.shape[0] != n:
        raise ValueError("Aligned selected/unsupported banks required")
    m = umu.shape[1]
    if uw.shape != umu.shape or g.shape != umu.shape:
        raise ValueError("Aligned unsupported means, visibility and timing slopes required")
    if any(np.any(~np.isfinite(a)) for a in (y, mu, w, q, umu, uw, g)):
        raise ValueError("Finite fixed-state inputs required")
    if np.any((w < 0) | (w > 1)) or np.any((uw < 0) | (uw > 1)):
        raise ValueError("Visibility weights must lie in [0,1]")
    if np.any((q <= 0) | (q >= 1)) or abs(float(q.sum()) - TOTAL_Q) > 1e-10:
        raise ValueError("Original selected q must have fixed total 1.6 and interior probabilities")
    if eta not in (0.0, 0.10) or not np.isfinite(sigma_hz) or sigma_hz <= 0:
        raise ValueError("Declared eta0/.10 and positive base width required")
    if (
        not np.isfinite(sigma_relative_s)
        or sigma_relative_s < 0
        or not np.isfinite(clutter_rate)
        or clutter_rate <= 0
    ):
        raise ValueError("Nonnegative relative width and positive clutter rate required")
    effective_eta = eta if m else 0.0
    sq = (1 - effective_eta) * q
    uq = np.full(m, effective_eta * TOTAL_Q / m) if m else np.empty(0)
    with np.errstate(over="raise", invalid="raise"):
        usigma = np.hypot(sigma_hz, sigma_relative_s * g)
        residual = circular(y[:, None] - mu, alias_hz)
        uresidual = circular(y[:, None] - umu, alias_hz)
    phi, dmean, dsigma, bounds = wrapped_normal(
        residual, np.full(mu.shape, sigma_hz), alias_hz=alias_hz
    )
    if sigma_hz / alias_hz <= 0.01:
        # At this width all nonprincipal images underflow, including the seam.
        # Use precisely the deployed kernel's floating-point operation order.
        phi = np.exp(-0.5 * (residual / sigma_hz) ** 2) / (sigma_hz * np.sqrt(2 * np.pi))
        dmean = phi * residual / sigma_hz**2
        dsigma = phi * ((residual / sigma_hz) ** 2 - 1) / sigma_hz
    if effective_eta:
        uphi, udmean, udsigma, ubounds = wrapped_normal(uresidual, usigma, alias_hz=alias_hz)
    else:
        uphi, udmean, udsigma = (np.zeros_like(umu, dtype=float) for _ in range(3))
        ubounds = []
    p, up = w * sq[None, :], uw * uq[None, :]
    odds, uodds = p / (1 - p), up / (1 - up)
    signal, usignal = odds * phi, uodds * uphi
    # Separate sums preserve EXACT legacy operation order at eta0, even M>0.
    total = clutter_rate / alias_hz + signal.sum(axis=1)
    normalizer = clutter_rate + odds.sum(axis=1)
    if effective_eta:
        total = total + usignal.sum(axis=1)
        normalizer = normalizer + uodds.sum(axis=1)
    row_nll = np.log(normalizer) - np.log(total)
    responsibility, uresponsibility = signal / total[:, None], usignal / total[:, None]
    clutter = clutter_rate / alias_hz / total
    dp = (1 / normalizer[:, None] - phi / total[:, None]) / (1 - p) ** 2
    dup = (1 / normalizer[:, None] - uphi / total[:, None]) / (1 - up) ** 2
    mean_gradient = -odds * dmean / total[:, None]
    sigma_gradient = -odds * dsigma / total[:, None]
    if sigma_hz / alias_hz <= 0.01:
        # All nonprincipal images underflow at this width. Match the deployed
        # narrow Shared density's mean-gradient floating operation order too.
        mean_gradient = -responsibility * residual / sigma_hz**2
    umean_gradient = -uodds * udmean / total[:, None]
    usigma_gradient = -uodds * udsigma / total[:, None]
    selected_index = responsibility.argmax(axis=1)
    selected_peak = responsibility[np.arange(n), selected_index]
    unsupported_index = uresponsibility.argmax(axis=1) if m else np.zeros(n, int)
    unsupported_peak = uresponsibility[np.arange(n), unsupported_index] if m else np.zeros(n)
    is_unsupported = unsupported_peak > selected_peak
    best = np.where(is_unsupported, unsupported_index, selected_index)
    best_residual = residual[np.arange(n), selected_index].copy()
    if m:
        best_residual[is_unsupported] = uresidual[
            np.arange(n)[is_unsupported], best[is_unsupported]
        ]
    ceiling = unsupported_peak_ceiling(
        m, eta=effective_eta, sigma_hz=sigma_hz, clutter_rate=clutter_rate, alias_hz=alias_hz
    )
    return PointTerms(
        float(row_nll.sum()),
        row_nll,
        responsibility,
        uresponsibility,
        clutter,
        mean_gradient,
        umean_gradient,
        sigma_gradient,
        usigma_gradient,
        dp * sq[None, :],
        dup * uq[None, :],
        (1 - effective_eta) * (dp * w).sum(axis=0),
        float(sigma_gradient.sum() + np.sum(usigma_gradient * sigma_hz / usigma)),
        float(np.sum(usigma_gradient * (sigma_relative_s * g / usigma) * g)),
        sq,
        uq,
        usigma,
        is_unsupported,
        best,
        np.maximum(selected_peak, unsupported_peak) > clutter,
        best_residual,
        dict(
            requested_eta=eta,
            effective_eta=effective_eta,
            total_q=float(sq.sum() + uq.sum()),
            selected_tail_bounds=bounds,
            unsupported_tail_bounds=ubounds,
            unsupported_signal_to_clutter_upper_bound=ceiling,
            unsupported_association_possible=bool(ceiling > 1),
            classifier="Largest individual signal posterior > clutter; no identity truth",
            scope="Fixed-state point availability control; not a global-tau or recovery model",
        ),
    )
