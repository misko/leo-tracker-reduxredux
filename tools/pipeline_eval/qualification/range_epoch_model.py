"""Small chronological timing and Doppler diagnostics on fixed satellite arcs."""

from dataclasses import dataclass

import numpy as np

FRAME_HZ = 750
LIGHT_KM_S = 299792.458
FOLD_HZ = 1 / 4.4e-6
GAP_S, MIN_S, MAX_S = 2.5, 10.0, 60.0
EPOCH_UNIT, CFO_UNIT = 2.0, 150.0


def wrap(value, period):
    return (value + period / 2) % period - period / 2


def native_phase(counter, origin, epoch, sample_rate):
    """Use a rational frame period without floating large hardware counters."""
    return ((counter - origin) * FRAME_HZ % sample_rate / FRAME_HZ + epoch) % (
        sample_rate / FRAME_HZ
    )


@dataclass(frozen=True)
class Arc:
    owner: int
    rf_hz: float
    component: str
    time_s: np.ndarray
    phase: np.ndarray
    cfo: np.ndarray
    train: np.ndarray


def split(group):
    """Split on time and gaps before looking at timing or position residuals."""
    chunks, start = [], 0
    for i, row in enumerate(group):
        dt = row["time_s"] - group[i - 1]["time_s"]
        if i and (not 0 < dt <= GAP_S or row["time_s"] - group[start]["time_s"] > MAX_S):
            chunks.append(group[start:i])
            start = i
    chunks.append(group[start:])
    for rows in chunks:
        time = np.array([row["time_s"] for row in rows])
        duration = time[-1] - time[0]
        train = time < time[0] + 2 * duration / 3
        if duration >= MIN_S and train.sum() >= 10 and (~train).sum() >= 6:
            yield Arc(
                rows[0]["v5_owner"],
                rows[0]["rf_hz"],
                rows[0]["component"],
                time,
                np.array([r["phase"] for r in rows]),
                np.array([r["folded_hz"] for r in rows]),
                train,
            )


def circular_center(values, period):
    vector = np.exp((2j * np.pi / period) * wrap(values, period)).mean()
    return np.angle(vector) * period / (2 * np.pi)


def unwrapped_slope(time, phase, period):
    aligned = np.r_[0.0, np.cumsum(wrap(np.diff(phase), period))]
    design = time - time.mean()
    return float(design @ aligned / (design @ design))


def frame_residual(arcs, delays, sample_rate, *, per_arc=False, observed=None):
    """Fit circular owner-phase and one sample-clock rate from training support only."""
    period = sample_rate / FRAME_HZ
    observations = observed if observed is not None else [arc.phase for arc in arcs]
    aligned = [wrap(obs - delay, period) for obs, delay in zip(observations, delays, strict=True)]
    rate_seed = [
        unwrapped_slope(arc.time_s[arc.train], y[arc.train], period)
        for arc, y in zip(arcs, aligned, strict=True)
    ]
    times = np.concatenate([arc.time_s[arc.train] for arc in arcs])
    values = np.concatenate([y[arc.train] for arc, y in zip(arcs, aligned, strict=True)])
    origin = float(np.median(times))
    dt = times - origin
    keys = [i if per_arc else arc.owner for i, arc in enumerate(arcs)]
    index = {key: i for i, key in enumerate(sorted(set(keys)))}
    group = np.concatenate(
        [np.full(arc.train.sum(), index[key]) for key, arc in zip(keys, arcs, strict=True)]
    )
    n = len(index)
    rates = np.array(rate_seed) if per_arc else np.array([np.median(rate_seed)])
    rgroup = group if per_arc else np.zeros_like(group)
    phase = np.array(
        [circular_center((values - dt * rates[rgroup])[group == i], period) for i in range(n)]
    )

    # Fixed robust circular relinearizations. Solve an intercept per grouped
    # transmitter and profile it out of the one rate fit (or per-arc rates).
    for _ in range(6):
        residual = wrap(values - phase[group] - rates[rgroup] * dt, period)
        weight = np.minimum(1.0, EPOCH_UNIT / np.maximum(abs(residual), 1e-12))
        norm = np.bincount(group, weight, minlength=n)
        mean_t = np.bincount(group, weight * dt, minlength=n) / norm
        mean_e = np.bincount(group, weight * residual, minlength=n) / norm
        centered = dt - mean_t[group]
        numerator = np.bincount(rgroup, weight * centered * residual, minlength=len(rates))
        denominator = np.bincount(rgroup, weight * centered**2, minlength=len(rates))
        delta = numerator / denominator
        rates += delta
        phase = wrap(phase + mean_e - mean_t * (delta if per_arc else delta[0]), period)
    pieces = []
    for key, arc, y in zip(keys, arcs, aligned, strict=True):
        i = index[key]
        prediction = phase[i] + rates[i if per_arc else 0] * (arc.time_s - origin)
        pieces.append(wrap(y - prediction, period))
    return pieces, rates.tolist()


def frequency_residual(arcs, predicted):
    results = []
    for arc, expected in zip(arcs, predicted, strict=True):
        difference = arc.cfo - expected
        intercept = circular_center(difference[arc.train], FOLD_HZ)
        results.append(wrap(difference - intercept, FOLD_HZ))
    return results


def held_loss(arcs, residuals):
    held = [piece[~arc.train] for arc, piece in zip(arcs, residuals, strict=True)]
    return dict(
        arc_median_mae=float(np.mean([np.median(abs(e)) for e in held])),
        held_rms=float(np.sqrt(np.mean(np.concatenate(held) ** 2))),
        held_median_absolute=float(np.median(abs(np.concatenate(held)))),
        held_count=sum(len(e) for e in held),
    )


def shuffled_epochs(arcs, seed=3031):
    rng = np.random.default_rng(seed)
    result = []
    for arc in arcs:
        y = arc.phase.copy()
        for keep in (arc.train, ~arc.train):
            y[keep] = rng.permutation(y[keep])
        result.append(y)
    return result
