"""Scalar log-integral envelopes only; no adaptive integrator or recording ports."""
import math

import numpy as np
from scipy.special import logsumexp, wrightomega


def curvature_bounds(direction, rho, sigma, precision):
    """Return H,U with -H <= L'' <= U on smooth winding intervals.

    rho is total visible Gaussian peak density divided by positive clutter.
    wrightomega(log(rho)-1.5) evaluates W(rho*exp(-1.5)) without forming rho*exp.
    """
    d, rho = np.asarray(direction, float), np.asarray(rho, float)
    if (d.ndim != 1 or rho.shape != d.shape or not np.isfinite(d).all()
            or not np.isfinite(rho).all() or np.any(rho < 0)
            or not math.isfinite(sigma) or sigma <= 0
            or not math.isfinite(precision) or precision <= 0):
        raise ValueError('finite directions, nonnegative rho and positive scales required')
    weight = (d / sigma)**2
    omega = np.zeros_like(rho)
    positive = rho > 0
    omega[positive] = wrightomega(np.log(rho[positive]) - 1.5)
    # A row with no signal is constant; do not charge its direction to H.
    h = precision + float(weight[positive].sum())
    u = -precision + float(2 * (weight * omega).sum())
    if not math.isfinite(h) or not math.isfinite(u):
        raise ValueError('curvature bound overflow')
    return h, u


def seam_log_bound(direction, rho, sigma, period, half_width):
    """Conservative log sum of upward jumps across one complete cell.

    No winding inventory is assumed. Each component crosses at most
    floor(2*h*|d|/P)+1 seams; total row peak/clutter ratio bounds all components.
    Return -inf only when every row has exactly zero direction or signal.
    Keep tiny mathematical jumps in logarithmic form rather than underflowing.
    """
    curvature_bounds(direction, rho, sigma, 1.)  # Shared domain validation.
    if not math.isfinite(period) or period <= 0 or not math.isfinite(half_width) or half_width <= 0:
        raise ValueError('positive finite period and half width required')
    d, rho = np.asarray(direction, float), np.asarray(rho, float)
    keep = (d != 0) & (rho > 0)
    if not np.any(keep):
        return -math.inf
    distances = 2 * half_width * abs(d[keep]) / period
    try:
        attenuation = (period / sigma)**2 / 8
    except OverflowError as error:
        raise ValueError('seam attenuation overflow') from error
    if not np.isfinite(distances).all() or not math.isfinite(attenuation):
        raise ValueError('seam bound overflow; do not silently omit jumps')
    counts = np.floor(distances) + 1
    logs = np.log(abs(d[keep])) + math.log(period) + np.log(rho[keep])
    logs += np.log(counts) - 2*math.log(sigma) - attenuation
    answer = float(logsumexp(logs))
    if not math.isfinite(answer):
        raise ValueError('nonfinite nonzero seam bound')
    return answer


def log_affine_integral(value, gradient, half_width):
    """log integral exp(value+gradient*x), x in [-h,h], stable at g=0."""
    if not all(math.isfinite(x) for x in (value, gradient, half_width)) or half_width <= 0:
        raise ValueError('finite affine coefficients and positive half width required')
    x = abs(gradient) * half_width
    if not math.isfinite(x):
        raise ValueError('affine exponent range overflow')
    if x < 1e-4:
        correction = x*x/6 - x**4/180 + x**6/2835
    elif x < 20:
        correction = math.log(math.sinh(x)/x)
    else:
        correction = x - math.log(2) - math.log(x) + math.log1p(-math.exp(-2*x))
    result = value + math.log(2) + math.log(half_width) + correction
    if not math.isfinite(result):
        raise ValueError('affine integral overflow')
    return result


def cell_envelope(value, gradient, half_width, h_bound, u_bound, *, seam_log_total):
    """Integrate affine exponential and bound quadratic/seam remainders.

    seam_log_total is mandatory: -inf asserts an independently established
    zero-jump bound (e.g. a proven seam-free cell). A finite tiny jump is retained
    in the receipt and receives outward rounding even if exp(logJ)*h underflows.
    These are conservative floating-point envelopes, not formal interval proofs.
    """
    if (not math.isfinite(h_bound) or h_bound < 0 or not math.isfinite(u_bound)
            or u_bound < -h_bound or math.isnan(seam_log_total) or seam_log_total == math.inf):
        raise ValueError('invalid curvature/seam bounds')
    affine = log_affine_integral(value, gradient, half_width)
    try:
        lower_remainder = .5*h_bound*half_width**2
        upper_remainder = .5*max(u_bound, 0)*half_width**2
    except OverflowError as error:
        raise ValueError('quadratic remainder overflow') from error
    log_jump_remainder = seam_log_total + math.log(half_width)
    try:
        jump = 0. if seam_log_total == -math.inf else math.exp(log_jump_remainder)
    except OverflowError as error:
        raise ValueError('seam remainder overflow') from error
    lower, upper = affine-lower_remainder, affine+upper_remainder+jump
    if not all(math.isfinite(x) for x in (lower, upper, lower_remainder, upper_remainder)):
        raise ValueError('envelope overflow')
    # Rounding guard, explicitly not a proof bounding all libm/input errors.
    slack = 32*np.finfo(float).eps * max(1., abs(affine), lower_remainder, upper_remainder, jump)
    return dict(log_lower=float(np.nextafter(lower-slack, -math.inf)),
                log_upper=float(np.nextafter(upper+slack, math.inf)),
                log_affine=affine, h_bound=h_bound, u_bound=u_bound,
                seam_log_total=seam_log_total, seam_log_remainder=log_jump_remainder,
                seam_remainder_underflow=bool(math.isfinite(seam_log_total) and jump == 0),
                floating_point_scope='Conservative numerical envelope; not formally certified interval arithmetic')
