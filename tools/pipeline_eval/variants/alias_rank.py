"""Rank discrete differential-pilot CFO aliases with short coherent code blocks."""

from functools import lru_cache

import numpy as np

from . import differential_pilot as dp
from . import folded_cfo
from .wide_regional import replace

PERIOD = folded_cfo.PERIOD
LIMIT = 800_000
BLOCKS = np.array([34, 70, 106, 142, 166, 202, 238, 274])
TAPS = (
    (BLOCKS[:, None, None] + np.arange(4)[None, :, None]) * dp.LAG + np.arange(4, 40, 2)
).reshape(len(BLOCKS), -1)
OFFSETS = np.arange(-36_000, 36_001, 12_000)
ENTRY = "leo_native_glrt_analyze_alias_rank_v1"
HEADER = folded_cfo.HEADER
coarse, presence = folded_cfo.coarse, folded_cfo.presence


@lru_cache(maxsize=2)
def reference(edge):
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL

    waves = [dp.phase_templates(edge, roll)[0][:, TAPS] for roll in (0, CONTROL_SYMBOL_ROLL)]
    kernels = np.asarray(waves).conj()
    kernels /= np.linalg.norm(kernels, axis=-1, keepdims=True)
    similarity = np.sum(kernels[0] * kernels[1].conj(), axis=-1)
    return kernels, 2 * (1 - abs(similarity) ** 2)


def frequency_grid(folded_hz):
    if not -PERIOD / 2 <= folded_hz <= PERIOD / 2:
        raise ValueError("folded carrier must be inside the principal phase interval")
    aliases, frequencies = [], []
    for k in range(-4, 5):
        center = folded_hz + k * PERIOD
        if abs(center) <= LIMIT + OFFSETS[-1]:
            aliases.append(center)
            frequencies.append(np.clip(center + OFFSETS, -LIMIT, LIMIT))
    return np.asarray(aliases), np.asarray(frequencies)


def assess(samples, lane, edge, epoch, folded_hz):
    """Return ordered absolute aliases and disjoint-block score evidence at fixed timing."""
    if not (
        samples.shape == (dp.SAMPLES, 2, 2)
        and samples.dtype == np.dtype("<i2")
        and lane in (0, 1)
        and 0 <= epoch < dp.FRAME
    ):
        raise ValueError("coherent alias search needs a dual-CI16 visit and a nominated epoch")
    if folded_hz is None:
        return None
    aliases, frequency = frequency_grid(folded_hz)
    ref, variance = reference(edge)
    residues, starts = np.asarray(dp.STARTS).T
    index = epoch + starts[:, None, None] + TAPS
    valid = (index[..., 0] >= 0) & (index[..., -1] < dp.SAMPLES)
    raw = samples[np.clip(index, 0, dp.SAMPLES - 1), lane]
    x = raw[..., 0].astype(np.complex64)
    x.imag = raw[..., 1]
    energy = np.mean(abs(x) ** 2, axis=-1)
    valid &= energy > 0
    if not valid.any():
        return None
    denom = np.where(valid, 1 / np.maximum(energy, 1), 0)

    # For block-relative sample lags, the discarded initial phase is common to the whole dot.
    degrees = -2j * np.pi / dp.RATE
    tones = np.exp(degrees * (TAPS[0] - TAPS[0, 0])[:, None] * frequency.ravel()).astype(
        np.complex64
    )
    projections = (x[None, ...] * ref[:, residues]) @ tones
    exact, roll = abs(projections) ** 2
    delta = (exact - roll) * denom[:, :, None]
    variances = (variance[residues] * valid).reshape(len(starts), 2, -1).sum(axis=(0, 2))
    halves = delta.reshape(len(starts), 2, 4, -1).sum(axis=(0, 2))
    halves /= np.sqrt(np.maximum(variances[:, None], 1))
    z = (halves[0] + halves[1]) / np.sqrt(2.0)
    maxima = np.argmax(z.reshape(frequency.shape), axis=1)
    best = np.arange(len(aliases)) * len(OFFSETS) + maxima
    ranks = np.argsort(-z[best], kind="stable")
    best_per_half = [int(np.argmax(h)) // len(OFFSETS) for h in halves]
    j = best[ranks[0]]
    eligible = z[j] >= 6 and np.min(halves[:, j]) > 3 and set(best_per_half).issubset(ranks[:2])
    return dict(
        options=[
            dict(
                alias_hz=float(aliases[k]),
                cfo_hz=float(frequency.ravel()[best[k]]),
                pooled=float(z[best[k]]),
                halves=[float(v) for v in halves[:, best[k]]],
            )
            for k in ranks
        ],
        valid_blocks=int(valid.sum()),
        aperture_samples=int(valid.sum()) * TAPS.shape[1],
        coherent_hypotheses=int(frequency.size),
        confirmed=bool(eligible),
    )


def restrict(result, *, require_evidence=True):
    if result is None or require_evidence and not result["confirmed"]:
        return None
    options = [c["cfo_hz"] for c in result["options"][:2]]
    return sum(
        1 << f for f in range(21) if any(abs(-LIMIT + f * 80_000 - h) <= 80_000 for h in options)
    )


def native(source):
    source = folded_cfo.native(source).replace(folded_cfo.ENTRY, ENTRY)
    source = replace(
        source,
        "fabs(folded[rx])<=10000000.0/88.0 && wide",
        "folded[rx]>=1.0 && folded[rx]<(1u<<WIDE_REGIONAL_BINS) && wide",
    )
    return replace(
        source,
        "unsigned mask=folded_cfo_mask(search_workspace,folded[rx]);",
        "unsigned mask=(unsigned)folded[rx];",
    )


class NativeMask(folded_cfo.BandCall):
    """Reuse the measured ABI layout with an explicit 21-bit coarse support mask."""

    def __init__(self, context):
        library = context._library
        setattr(library, folded_cfo.ENTRY, getattr(library, ENTRY))
        super().__init__(context)
