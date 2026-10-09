"""Synthetic-only, conditioned native GLRT diagnostic; no recording inputs."""

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame


def signal(cutoff_s, *, amplitude=1.0, noise_rms=0.0, seed=120):
    """One abrupt physical signal turn-off; receiver noise remains throughout.

    Fixed 2.5 MS/s, 20 ms, lower-edge pilot, zero CFO and epoch. These are
    synthetic configuration choices, not estimated satellite geometry.
    """
    if not 0 <= cutoff_s <= 0.020 or amplitude < 0 or noise_rms < 0:
        raise ValueError("invalid synthetic signal configuration")
    rate = 2_500_000
    n = rate // 50
    template = np.asarray(qin_edge_pilot_frame(rate, "lower"), np.complex128)
    values = np.zeros(n, np.complex128)
    support = np.zeros(n, bool)
    for frame in range(16):
        start = round(frame * rate / 750)
        stop = round(66 * rate * 4.4e-6)
        if start + stop > n:
            break
        count = min(len(template), n - start)
        values[start : start + count] += template[:count]
        support[start + round(2 * rate * 4.4e-6) : start + stop] = True
    visible = np.arange(n) / rate < cutoff_s
    values *= amplitude * visible
    rng = np.random.default_rng(seed)
    values += noise_rms / np.sqrt(2) * (rng.normal(size=n) + 1j * rng.normal(size=n))
    return values, float(np.mean(visible[support]))
