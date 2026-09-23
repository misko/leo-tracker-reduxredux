"""Held-frame diagnostics for forced dual-receiver pilot measurements."""

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor


def circular_summary(phase, weights):
    if len(phase) == 0 or np.sum(weights) <= 0:
        return {"count": len(phase), "weighted_R": None, "unweighted_R": None, "phase_rad": None}
    value = np.average(np.exp(1j * phase), weights=weights)
    return {
        "count": len(phase),
        "weighted_R": float(abs(value)),
        "unweighted_R": float(abs(np.mean(np.exp(1j * phase)))),
        "phase_rad": float(np.angle(value)),
    }


def source_window(c0, c1, times, train, include, center):
    fit_mask, held = train & include, ~train & include
    if fit_mask.sum() < 3 or held.sum() < 3:
        return {"failure": "insufficient_train_or_held_frames"}
    product = c1 * np.conj(c0)
    weights = np.sqrt(abs(c0) * abs(c1))
    if np.sum(weights[fit_mask]) <= 0 or np.sum(weights[held]) <= 0:
        return {"failure": "zero_pilot_power"}
    frequency, _, _ = fit_linear_phasor(
        product[fit_mask], times[fit_mask], np.maximum(weights[fit_mask], 1e-30), center
    )
    rotation = np.exp(-2j * np.pi * frequency * (times[held] - center))
    stats = circular_summary(np.angle(product[held] * rotation), weights[held])
    denominator = np.sqrt(np.sum(abs(c0[held]) ** 2) * np.sum(abs(c1[held]) ** 2))
    stats.update(
        {
            "failure": None,
            "train_frames": int(fit_mask.sum()),
            "rate_hz": frequency,
            "normalized_complex_coherence": float(
                abs(np.sum(product[held] * rotation)) / max(denominator, 1e-30)
            ),
        }
    )
    return stats


def source_metrics(c0, c1, controls, wrong, times, train):
    full = source_window(c0, c1, times, train, np.ones(len(times), dtype=bool), 0.06)
    ratios = []
    for rx, coeff in enumerate((c0, c1)):
        power = float(np.sum(abs(coeff[~train]) ** 2))
        ratios.append(
            {
                "rx": rx,
                "exact_over_rolled": power
                / max(float(np.sum(abs(controls[rx][~train]) ** 2)), 1e-30),
                "exact_over_wrong_timing": power
                / max(float(np.sum(abs(wrong[rx][~train]) ** 2)), 1e-30),
            }
        )
    blocks = [
        source_window(
            c0, c1, times, train, (times >= k * 0.02) & (times < (k + 1) * 0.02), (k + 0.5) * 0.02
        )
        for k in range(6)
    ]
    values = [b["weighted_R"] for b in blocks if b.get("failure") is None]
    support = all(r["exact_over_rolled"] > 2 and r["exact_over_wrong_timing"] > 2 for r in ratios)
    median = float(np.median(values)) if values else None
    return {
        "full_120ms": full,
        "blocks_20ms": blocks,
        "valid_20ms_blocks": len(values),
        "receiver_controls": ratios,
        "pilot_supported_both_rx": support,
        "median_20ms_R": median,
        "screened_short_phase": bool(
            support and len(values) >= 4 and median is not None and median >= 0.8
        ),
    }


def pair_metrics(left, right):
    ta, tb = left["times"], right["times"]
    nearest = np.abs(ta[:, None] - tb[None, :]).argmin(axis=1)
    keep = abs(ta - tb[nearest]) < 0.5 / 750
    ia, ib = np.flatnonzero(keep), nearest[keep]
    if len(np.unique(ib)) != len(ib):
        raise ValueError("nearest-frame correspondence is not one-to-one")
    both_held = ~left["train"][ia] & ~right["train"][ib]
    ia, ib = ia[both_held], ib[both_held]
    pa, pb = left["product"][ia], right["product"][ib]
    wa, wb = left["weights"][ia], right["weights"][ib]
    stats = circular_summary(np.angle(pb * np.conj(pa)), np.sqrt(wa * wb))
    # No source-specific product-rate subtraction, and no fit on the paired DD.
    shift = len(ib) // 2
    wrong = circular_summary(
        np.angle(np.roll(pb, shift) * np.conj(pa)), np.sqrt(wa * np.roll(wb, shift))
    )
    support = (
        left["metrics"]["pilot_supported_both_rx"] and right["metrics"]["pilot_supported_both_rx"]
    )
    stats.update(
        {
            "failure": None if len(ia) >= 3 else "insufficient_held_pairs",
            "wrong_time_control": wrong,
            "both_sources_pilot_supported": support,
            "max_pair_gap_us": float(np.max(abs(ta[ia] - tb[ib])) * 1e6) if len(ia) else None,
            "screened_DD": bool(
                len(ia) >= 3
                and support
                and stats["weighted_R"] is not None
                and stats["weighted_R"] >= 0.8
            ),
        }
    )
    return stats


def common_training_starts(frame_specs, sample_count, frame_length, window=512):
    """Raw calibration windows contained in every anchor's training frames."""
    allowed = np.ones(sample_count, dtype=bool)
    for starts, train in frame_specs:
        mask = np.zeros(sample_count, dtype=bool)
        for start in starts[train]:
            mask[start + 8 : start + frame_length - 8] = True
        allowed &= mask
    prefix = np.r_[0, np.cumsum(~allowed)]
    possible = np.arange(0, sample_count - window + 1, window)
    valid = possible[prefix[possible + window] == prefix[possible]]
    if len(valid) > 64:
        valid = valid[np.linspace(0, len(valid) - 1, 64).round().astype(int)]
    return valid


def common_raw_offset(iq, starts, fs, window=512):
    if len(starts) < 3:
        raise ValueError("insufficient_common_training_windows")
    data = iq[starts[:, None] + np.arange(window)[None, :]].astype(np.complex128)
    data -= data.mean(axis=1, keepdims=True)
    product = data[:, :, 1] * np.conj(data[:, :, 0])
    spectrum = np.fft.fft(product * np.hanning(window)[None, :], n=32768, axis=1)
    power = np.mean(abs(spectrum) ** 2, axis=0)
    peak = int(np.argmax(power))
    y = np.log(np.maximum(power[[(peak - 1) % len(power), peak, (peak + 1) % len(power)]], 1e-30))
    curvature = y[0] - 2 * y[1] + y[2]
    fraction = 0 if curvature == 0 else np.clip(0.5 * (y[0] - y[2]) / curvature, -0.5, 0.5)
    return float(np.fft.fftfreq(len(power), 1 / fs)[peak] + fraction * fs / len(power))
