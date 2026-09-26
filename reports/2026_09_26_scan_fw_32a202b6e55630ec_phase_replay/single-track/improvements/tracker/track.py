"""Causal differential-phase trackers and held-tone scoring.

The input is the simultaneous per-tone product RX1 * conj(RX0), after only the
coarse per-dwell GLRT frequency branch has been removed.  No held-out phase is
used to establish a phase intercept or choose an unwrap branch.
"""
from dataclasses import dataclass
import numpy as np

TAU = 2.0 * np.pi
TRAIN_TONES = np.array([0, 2, 4, 6])
HELD_TONES = np.array([1, 3, 5, 7])


def wrap(x):
    return (np.asarray(x) + np.pi) % TAU - np.pi


def circular_rmse(error):
    error = wrap(np.asarray(error, dtype=float))
    return float(np.sqrt(np.nanmean(error * error)))


def combine_tones(products, weights, tones=TRAIN_TONES):
    """Weighted complex mean; zero/invalid weights contribute no evidence."""
    z = np.asarray(products)[:, tones]
    w = np.asarray(weights, dtype=float)[:, tones]
    good = np.isfinite(z.real) & np.isfinite(z.imag) & np.isfinite(w) & (w > 0)
    unit = np.divide(z, abs(z), out=np.zeros_like(z), where=abs(z) > 0)
    numerator = np.sum(np.where(good, unit * w, 0), axis=1)
    denominator = np.sum(np.where(good, w, 0), axis=1)
    out = np.full(len(z), np.nan + 1j * np.nan)
    ok = denominator > 0
    out[ok] = numerator[ok] / denominator[ok]
    return out, denominator


def cautious_unwrap(time_s, phase, *, gap_s=0.003, max_innovation_rad=2.1):
    """Unwrap locally, leaving gaps/slips as separate unsupported segments."""
    t = np.asarray(time_s, dtype=float)
    p = np.asarray(phase, dtype=float)
    unwrapped = np.full(len(t), np.nan)
    segment = np.full(len(t), -1, dtype=int)
    seg = -1
    previous = None
    slope = 0.0
    for i in range(len(t)):
        if not np.isfinite(p[i]):
            previous = None
            continue
        new = previous is None or t[i] <= t[previous] or t[i] - t[previous] > gap_s
        if new:
            seg += 1
            unwrapped[i] = p[i]
            segment[i] = seg
            previous = i
            slope = 0.0
            continue
        dt = t[i] - t[previous]
        prediction = unwrapped[previous] + slope * dt
        candidate = p[i] + TAU * np.round((prediction - p[i]) / TAU)
        innovation = candidate - prediction
        if abs(innovation) > max_innovation_rad:
            seg += 1
            unwrapped[i] = p[i]
            segment[i] = seg
            previous = i
            slope = 0.0
            continue
        old_slope = (candidate - unwrapped[previous]) / dt
        slope = 0.7 * slope + 0.3 * old_slope
        unwrapped[i] = candidate
        segment[i] = seg
        previous = i
    return unwrapped, segment


@dataclass(frozen=True)
class Fit:
    order: int
    reference_s: float
    coefficients: np.ndarray
    scale_rad: float
    used: np.ndarray

    def predict(self, time_s):
        x = np.asarray(time_s) - self.reference_s
        return sum(c * x**k for k, c in enumerate(self.coefficients))


def robust_polynomial_fit(time_s, phase, weight, order, *, iterations=6):
    """Huber IRLS fit to one already-supported unwrap segment."""
    t = np.asarray(time_s, float)
    y = np.asarray(phase, float)
    w = np.asarray(weight, float)
    used = np.isfinite(t) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    if used.sum() < order + 2:
        raise ValueError(f"need at least {order + 2} supported observations")
    ref = float(np.average(t[used], weights=w[used]))
    x = t - ref
    design = np.column_stack([x**k for k in range(order + 1)])
    effective = w.copy()
    scale = np.nan
    for _ in range(iterations):
        a = design[used] * np.sqrt(effective[used, None])
        b = y[used] * np.sqrt(effective[used])
        coef = np.linalg.lstsq(a, b, rcond=None)[0]
        residual = y - design @ coef
        mad = np.median(np.abs(residual[used] - np.median(residual[used])))
        scale = max(1.4826 * mad, np.deg2rad(0.25))
        huber = np.minimum(1.0, 1.5 * scale / np.maximum(abs(residual), 1e-15))
        effective = w * huber
    return Fit(order, ref, coef, float(scale), used)


def early_models(time_s, products, weights, *, training_s=0.020, train_mask=None, gap_s=0.003):
    """Fit constant-frequency and frequency-rate models to early even tones."""
    z, evidence = combine_tones(products, weights)
    phase, segment = cautious_unwrap(time_s, np.angle(z), gap_s=gap_s)
    eligible = np.asarray(time_s) < training_s if train_mask is None else np.asarray(train_mask, bool)
    train = eligible & np.isfinite(phase)
    if not np.any(train):
        raise ValueError("no supported observations in early training interval")
    # Never bridge an ambiguity: use only the last contiguous training segment.
    selected_segment = segment[np.flatnonzero(train)[-1]]
    train &= segment == selected_segment
    masked_phase = np.where(train, phase, np.nan)
    masked_weight = np.where(train, evidence, 0.0)
    return {
        "glrt_only_constant_phase": robust_polynomial_fit(time_s, masked_phase, masked_weight, 0),
        "constant_frequency": robust_polynomial_fit(time_s, masked_phase, masked_weight, 1),
        "smooth_frequency_rate": robust_polynomial_fit(time_s, masked_phase, masked_weight, 2),
    }


def rolling_predictions(time_s, products, weights, *, history=24, gap_s=0.003):
    """One-step causal robust linear predictions from past even-tone frames."""
    t = np.asarray(time_s, float)
    z, evidence = combine_tones(products, weights)
    predicted = np.full(len(t), np.nan)
    uncertainty = np.full(len(t), np.nan)
    segment = np.full(len(t), -1, dtype=int)
    accepted_t, accepted_phase, accepted_weight = [], [], []
    seg = -1
    for i in range(len(t)):
        gap = bool(accepted_t and (t[i] <= accepted_t[-1] or t[i] - accepted_t[-1] > gap_s))
        if gap:
            accepted_t, accepted_phase, accepted_weight = [], [], []
        fit = None
        if len(accepted_t) >= 3:
            fit = robust_polynomial_fit(np.asarray(accepted_t[-history:]), np.asarray(accepted_phase[-history:]),
                                        np.asarray(accepted_weight[-history:]), 1)
            predicted[i] = fit.predict(t[i])
            span = max(np.ptp(accepted_t[-history:]), np.finfo(float).eps)
            uncertainty[i] = fit.scale_rad * (1.0 + (t[i] - accepted_t[-1]) / span)
        if not np.isfinite(z[i]):
            continue
        observed = float(np.angle(z[i]))
        if not accepted_t:
            seg += 1
            unwrapped = observed
        else:
            reference = predicted[i] if np.isfinite(predicted[i]) else accepted_phase[-1]
            unwrapped = observed + TAU * np.round((reference - observed) / TAU)
            if np.isfinite(predicted[i]) and abs(unwrapped - predicted[i]) > 2.1:
                # The forecast remains as failure-inclusive evidence for this
                # frame. Reset only affects subsequent predictions.
                seg += 1
                accepted_t, accepted_phase, accepted_weight = [], [], []
                unwrapped = observed
        accepted_t.append(float(t[i])); accepted_phase.append(float(unwrapped)); accepted_weight.append(float(evidence[i]))
        segment[i] = seg
    return predicted, uncertainty, segment


def causal_baselines(time_s, products, weights, *, gap_s=0.003):
    """Minimal one-step baselines using one or two prior even-tone phases."""
    t = np.asarray(time_s, float)
    z, _ = combine_tones(products, weights)
    phase = np.angle(z)
    previous = np.full(len(t), np.nan)
    increment = np.full(len(t), np.nan)
    segment = np.zeros(len(t), dtype=int)
    seg = 0
    for i in range(1, len(t)):
        if not np.isfinite(phase[i - 1]) or t[i] <= t[i - 1] or t[i] - t[i - 1] > gap_s:
            seg += 1
            segment[i] = seg
            continue
        previous[i] = phase[i - 1]
        if i >= 2 and segment[i - 1] == segment[i - 2] and np.isfinite(phase[i - 2]):
            increment[i] = phase[i - 1] + wrap(phase[i - 1] - phase[i - 2])
        segment[i] = seg
    uncertainty = np.full(len(t), np.nan)
    return {"previous_phase": previous, "two_frame_increment": increment}, uncertainty, segment


def held_tone_errors(predicted_phase, products, weights):
    """Return independent odd-tone residuals without fitting their intercepts."""
    z = np.asarray(products)[:, HELD_TONES]
    w = np.asarray(weights)[:, HELD_TONES]
    valid = np.isfinite(z.real) & np.isfinite(z.imag) & np.isfinite(w) & (w > 0)
    errors = wrap(np.angle(z) - np.asarray(predicted_phase)[:, None])
    return np.where(valid, errors, np.nan), valid
