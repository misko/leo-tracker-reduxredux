"""Optimistic diagnostic for a safe tap-prefix bound on original coarse GLRT scores."""

import numpy as np

TRACE_LOCI = 128
TAP_BOUNDARIES = (11, 22, 33, 40)
DIRECT_ALLOWANCE = 2e-5


def upper_bounds(samples, ref, weight):
    iq_energy = np.sum(np.abs(samples) ** 2, axis=-1)
    norm = np.sqrt(iq_energy)
    rows = []
    for prefix in (*TAP_BOUNDARIES, len(ref)):
        used = samples[..., :prefix] @ weight[:, :prefix].T
        remain = np.linalg.norm(samples[..., prefix:], axis=-1) * np.linalg.norm(ref[prefix:])
        upper = np.divide(
            np.abs(used) + remain[..., None],
            norm[..., None],
            out=np.zeros_like(used.real),
            where=norm[..., None] > 0,
        )
        rows.append(np.minimum(1.0, upper))
    return np.stack(rows)


def diagnostic(values, template, rate, frequencies, symbols, epochs, cutoff):
    aperture = 44
    local = np.arange(aperture)
    phases = np.arange(TRACE_LOCI) * epochs // TRACE_LOCI
    frames = np.rint(np.arange(16) * rate / 750).astype(int)
    rotation = np.exp(-2j * np.pi / rate * np.asarray(frequencies)[:, None] * local)
    total = np.zeros((len(TAP_BOUNDARIES) + 1, TRACE_LOCI, len(frequencies)))
    support = np.zeros(TRACE_LOCI, dtype=int)
    for symbol in symbols:
        start = symbol * aperture
        ref = np.asarray(template[start : start + aperture], dtype=complex).conj()
        ref /= np.linalg.norm(ref)
        positions = frames[:, None] + start + phases
        valid = positions + aperture <= len(values)
        indices = np.minimum(positions[..., None] + local, len(values) - 1)
        samples = values[indices]
        bounds = upper_bounds(samples, ref, rotation * ref)
        total += np.sum(bounds * valid[None, ..., None], axis=1)
        support += np.sum(valid, axis=0)
    total /= support[None, :, None]
    if np.any(total[:-1] + DIRECT_ALLOWANCE < total[-1]):
        raise ValueError("Computed tap-prefix envelope did not enclose the exact score")
    return dict(
        threshold=cutoff,
        cells=int(total[-1].size),
        prunable_by_prefix={
            str(tap): int(np.count_nonzero(bound + DIRECT_ALLOWANCE < cutoff))
            for tap, bound in zip((*TAP_BOUNDARIES, aperture), total, strict=True)
        },
    )
