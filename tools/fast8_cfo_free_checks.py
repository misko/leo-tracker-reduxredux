"""CFO-free experimental pilot and repetition scores, with no GLRT inputs.

The template is sampled over exactly three nominal frames (4 ms). Folding
over that period preserves the noninteger samples/frame at 2.5 MS/s. A timing
search remains; no frequency hypotheses or GLRT-derived timing are used.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _values(iq: np.ndarray) -> np.ndarray:
    x = np.asarray(iq, dtype=np.complex128)
    if x.shape != (50000,) or not np.isfinite(x).all():
        raise ValueError("prototype requires finite 20 ms IQ at 2.5 MS/s")
    return x


@dataclass(frozen=True)
class DifferentialBank:
    """Precomputed exact/control replicas and valid-support normalization."""

    transforms: np.ndarray
    energies: np.ndarray
    lags: tuple[int, ...]
    period: int


def prepare_bank(
    exact: np.ndarray, control: np.ndarray, lags: tuple[int, ...]
) -> DifferentialBank:
    if exact.shape != (10000,) or control.shape != exact.shape:
        raise ValueError("templates must span three frames / 10000 samples")
    if not lags or any(d not in (0, 1, 2, 4) for d in lags):
        raise ValueError("unsupported differential lag")
    replicas = []
    energies = []
    for d in lags:
        count = 50000 - d
        weights = np.full(10000, 5.0)
        weights[:d] -= 1
        wf = np.fft.fft(weights)
        pair = []
        pair_energy = []
        for template in (exact, control):
            ref = template * np.roll(template, d).conj()
            ref = ref - ref.mean()
            rf = np.fft.fft(ref)
            # Weighted mean/energy depend on alignment when the first d input
            # products are absent. Use identical valid support in every score.
            weighted_sum = np.fft.ifft(wf * rf.conj())
            weighted_energy = np.fft.ifft(wf * np.fft.fft(abs(ref)**2).conj()).real
            centered_energy = weighted_energy - abs(weighted_sum)**2 / count
            pair.append(rf)
            pair_energy.append(np.maximum(centered_energy, 0))
        replicas.append(pair)
        energies.append(pair_energy)
    return DifferentialBank(np.asarray(replicas), np.asarray(energies), lags, 10000)


def template_features(iq: np.ndarray, bank: DifferentialBank) -> dict[str, float]:
    """Fold all 20 ms and correlate differential replicas by one FFT per lag.

Magnitude removes the constant CFO phase factor independently for each lag.
Combine lag magnitudes at a common timing hypothesis; evaluate the control at
the exact-template winner. Never independently maximize the control template.
"""
    x = _values(iq)
    maps = []
    for index, d in enumerate(bank.lags):
        z = x[d:] * (x[:-d] if d else x).conj()
        z -= z.mean()
        z_energy = float(np.vdot(z, z).real)
        supported = np.zeros(x.size, dtype=complex)
        supported[d:] = z
        folded = supported.reshape(-1, bank.period).sum(axis=0)
        numerators = abs(np.fft.ifft(
            np.fft.fft(folded)[None, :] * bank.transforms[index].conj(), axis=1
        ))
        denominator = np.sqrt(z_energy * bank.energies[index])
        maps.append(np.divide(
            numerators, denominator, out=np.zeros_like(numerators), where=denominator > 0
        ))
    score = np.mean(maps, axis=0)
    epoch = int(np.argmax(score[0]))
    exact = float(score[0, epoch])
    control = float(score[1, epoch])
    return {"margin": exact-control, "exact": exact, "control": control,
            "epoch_sample": epoch}


def coherent_repeat_features(iq: np.ndarray) -> dict[str, float]:
    """Three direct full-support correlations: exact 4 ms and two controls."""
    x = _values(iq)

    def coherence(lag):
        a, b = x[:-lag], x[lag:]
        energy = float(np.vdot(a, a).real * np.vdot(b, b).real)
        return float(abs(np.vdot(a, b))**2 / energy) if energy > 0 else 0.0

    exact = coherence(10000)
    control = .5 * (coherence(9963)+coherence(10037))
    return {"repeat_long_excess": exact-control, "repeat_long_exact": exact,
            "repeat_long_control": control}


def multi_repeat_features(iq: np.ndarray) -> dict[str, float]:
    """Full-window autocorrelation at 1, 2 and 3 nominal frame intervals.

Interpolate complex correlation at fractional lags with a 33-tap Kaiser-sinc
kernel, rather than rounding a frame to 3333 samples. This interpolation is an
approximation and is checked against bandlimited synthetic signals. Nearby
clock hypotheses cover +/-0.25 sample; off-frame controls reject steady tones.
"""
    x = _values(iq)
    fft_size = 1 << (2*x.size-1).bit_length()
    xf = np.fft.fft(x, fft_size)
    ac = np.fft.ifft(abs(xf)**2)[:x.size]
    prefix = np.r_[0., np.cumsum(abs(x)**2)]
    ks = np.arange(x.size)
    energy = prefix[x.size-ks] * (prefix[-1]-prefix[ks])
    normalized = np.divide(ac, np.sqrt(energy), out=np.zeros_like(ac), where=energy > 0)

    def coherence(delay):
        center = int(np.floor(delay))
        indexes = center + np.arange(-16, 17)
        weights = np.sinc(delay-indexes) * np.kaiser(33, 8)
        weights /= weights.sum()
        return float(abs(np.dot(weights, normalized[indexes]))**2)

    differences = []
    result = {}
    for frame in (1, 2, 3):
        lag = frame*2500000/750
        target = max(coherence(lag+d) for d in (-.25, 0., .25))
        # Match the target's small delay search in both controls. Otherwise
        # interpolation ripple alone can give a tone a positive excess.
        control = .5 * sum(
            max(coherence(lag+offset+d) for d in (-.25, 0., .25))
            for offset in (-37, 37)
        )
        differences.append(target-control)
        result[f'repeat_frame{frame}_excess'] = target-control
    result['repeat_multi_excess'] = float(np.mean(differences))
    return result
