"""Research segment GLRTs and phase-kernel detectors on shared pilot correlations.

Inputs are raw complex correlations r=<pilot,IQ>. With positive pilot energies E,
z=r/sqrt(E) has unit white-noise variance and steering sqrt(E)*exp(j*omega*t).
Omitting E asserts unit template energies. Segment GLRTs project z onto one
complex amplitude per nonoverlapping segment per frame, at a common CFO. They
use every symbol and return projected energy / total z energy. Gaussian noise
and an unknown common variance are correlator-domain assumptions, not a full-IQ
likelihood. Different segment lengths require separate null calibration.

Phase kernels use K_ij=exp(-abs(i-j)/L) and the quadratic statistic
sum_frames r^H D_f K D_f^H r / (sum(E) * sum_frames ||z||^2), where D_f has
exp(j*omega*t) on its diagonal. The energy-weighted kernel has unit trace;
L->infinity exactly reproduces coherent Gaussian scoring. Finite L suppresses
long phase lags without segment boundaries. This is a PSD quadratic detector,
not an exact GLRT or probability. Perfect coherent signals need not score one
at finite L. All CFO choices use the same complete FFT frequency bank.

Natural scores maximize exact profiles; ``_margin`` diagnostics subtract the
independently maximized control statistic. CFO always belongs to the exact peak.
Covariance training, null calibration, and multi-length unions belong to runners.
"""

from __future__ import annotations

import numpy as np

SEGMENT_LENGTHS = (8, 16, 32, 64)
COHERENCE_LENGTHS = (8, 16, 32)
SYMBOL_COUNTS = (64, 128, 256)


def _energy(value, count, name):
    result = np.ones(count) if value is None else np.asarray(value, dtype=float)
    if result.shape != (count,) or not np.all(np.isfinite(result)) or np.any(result <= 0):
        raise ValueError(f"{name} must be a positive finite [{count}] vector")
    return result


def _validate(exact, control, symbol_step_s, fft_size):
    exact = np.asarray(exact, dtype=np.complex128)
    control = np.asarray(control, dtype=np.complex128)
    if exact.ndim != 3 or exact.shape[-1] not in SYMBOL_COUNTS or exact.shape != control.shape:
        raise ValueError("exact/control must share shape [trials,frames,N], N=64/128/256")
    if not np.all(np.isfinite(exact)) or not np.all(np.isfinite(control)):
        raise ValueError("correlations must be finite")
    if not np.isfinite(symbol_step_s) or symbol_step_s <= 0:
        raise ValueError("symbol_step_s must be finite and positive")
    if (
        isinstance(fft_size, bool)
        or not isinstance(fft_size, int)
        or fft_size < 2 * exact.shape[-1]
    ):
        raise ValueError("fft_size must be an integer >=2*N for aperiodic correlations")
    return exact, control


def _pack(correlation, support, fft_size):
    """Place positive and negative aperiodic lags in a longer circular transform."""
    result = np.zeros((len(correlation), fft_size), dtype=np.complex128)
    result[:, :support] = correlation[:, :support]
    result[:, -(support - 1) :] = correlation[:, -(support - 1) :]
    return result


def _phase_kernel_profile(correlation, count, length, fft_size):
    packed = _pack(correlation, count, fft_size)
    weights = np.exp(-np.arange(count) / length)
    packed[:, :count] *= weights
    packed[:, -(count - 1) :] *= weights[1:][::-1]
    return np.fft.fft(packed, axis=-1).real


def _one_bank(values, energy, grid, fft_size, return_profiles):
    trials, frames, count = values.shape
    transformed = np.fft.fft(values, n=fft_size, axis=-1)
    power = (np.abs(transformed) ** 2).sum(axis=1)
    correlation = np.fft.ifft(power, axis=-1)
    total_energy = (np.abs(values) ** 2 / energy).sum(axis=(1, 2))
    ceiling = (np.abs(values).sum(axis=-1) ** 2).sum(axis=1)

    def peak(profile, denominator):
        index = np.argmax(profile, axis=1)
        score = np.divide(
            profile[np.arange(trials), index],
            denominator,
            out=np.zeros(trials),
            where=denominator > 0,
        )
        item = dict(score=score, cfo_hz=np.where(denominator > 0, grid[index], 0.0))
        if return_profiles:
            item["profile"] = np.divide(
                profile,
                denominator[:, None],
                out=np.zeros_like(profile),
                where=denominator[:, None] > 0,
            )
        return item

    result = {
        "gaussian_coherent": peak(power / energy.sum(), total_energy),
        "current_coherent_margin": peak(power, ceiling),
    }
    for length in SEGMENT_LENGTHS:
        segments = count // length
        blocks = values.reshape(trials, frames, segments, length)
        segment_energy = energy.reshape(segments, length).sum(axis=1)
        short = np.fft.fft(blocks, n=2 * length, axis=-1)
        pooled = (np.abs(short) ** 2 / segment_energy[None, None, :, None]).sum(axis=(1, 2))
        segment_correlation = np.fft.ifft(pooled, axis=-1)
        profile = np.fft.fft(_pack(segment_correlation, length, fft_size), axis=-1).real
        result[f"segment{length}"] = peak(profile, total_energy)
    for length in COHERENCE_LENGTHS:
        profile = _phase_kernel_profile(correlation, count, length, fft_size) / energy.sum()
        result[f"phase_kernel{length}"] = peak(profile, total_energy)
    return result


def score_trials(
    exact,
    control,
    *,
    symbol_step_s=4.4e-6,
    fft_size=512,
    exact_template_energy=None,
    control_template_energy=None,
    return_profiles=False,
):
    """Score independent [trials,frames,N] trials, pooling powers within each trial.

    Returns per-trial arrays score,cfo_hz,exact_score,control_score,control_cfo_hz.
    Optional exact_profile/control_profile are independently normalized [T,fft]
    spectra; margins are differences of maxima, not maxima of profile differences.
    Callers may chunk trials to bound memory. Inputs are never modified.
    """
    exact, control = _validate(exact, control, symbol_step_s, fft_size)
    count = exact.shape[-1]
    grid = np.fft.fftfreq(fft_size, d=symbol_step_s)
    exact_bank = _one_bank(
        exact,
        _energy(exact_template_energy, count, "exact_template_energy"),
        grid,
        fft_size,
        return_profiles,
    )
    control_bank = _one_bank(
        control,
        _energy(control_template_energy, count, "control_template_energy"),
        grid,
        fft_size,
        return_profiles,
    )
    result = {}
    for method, exact_item in exact_bank.items():
        control_item = control_bank[method]
        exact_score, control_score = exact_item["score"], control_item["score"]
        item = dict(
            score=exact_score,
            cfo_hz=exact_item["cfo_hz"],
            exact_score=exact_score,
            control_score=control_score,
            control_cfo_hz=control_item["cfo_hz"],
        )
        if return_profiles:
            item.update(
                exact_profile=exact_item["profile"], control_profile=control_item["profile"]
            )
        if method.endswith("_margin"):
            item["score"] = exact_score - control_score
            result[method] = item
        else:
            result[method] = item
            result[method + "_margin"] = dict(item, score=exact_score - control_score)
    return result


def score_bank(exact, control, **kwargs):
    """Scalar wrapper for one [frames,N] observation; optional profiles stay arrays."""
    exact, control = np.asarray(exact), np.asarray(control)
    if exact.ndim != 2 or control.ndim != 2:
        raise ValueError("score_bank requires [frames,N] exact/control matrices")
    result = score_trials(exact[None], control[None], **kwargs)
    return {
        method: {
            key: value[0] if key.endswith("_profile") else float(value[0])
            for key, value in item.items()
        }
        for method, item in result.items()
    }


score_trial_bank = score_trials


def score_at_frequency(
    exact,
    control,
    cfo_hz,
    *,
    symbol_step_s=4.4e-6,
    fft_size=512,
    exact_template_energy=None,
    control_template_energy=None,
):
    """Evaluate exact/control at one supplied residual CFO, without reselection.

    For held-out confirmation, callers must freeze timing, CFO, and method using
    the earlier observation. Both channels are scored at this same frequency;
    margin scores here are fixed-frequency differences, not differences of maxima.
    """
    exact, control = np.asarray(exact), np.asarray(control)
    if exact.ndim != 2 or control.ndim != 2 or exact.shape != control.shape:
        raise ValueError("fixed-frequency scoring requires shared [frames,N] shape")
    if not np.isfinite(cfo_hz):
        raise ValueError("fixed CFO must be finite")
    rotation = np.exp(-2j * np.pi * cfo_hz * np.arange(exact.shape[-1]) * symbol_step_s)
    profiles = score_bank(
        exact * rotation,
        control * rotation,
        symbol_step_s=symbol_step_s,
        fft_size=fft_size,
        exact_template_energy=exact_template_energy,
        control_template_energy=control_template_energy,
        return_profiles=True,
    )
    result = {}
    for method, item in profiles.items():
        exact_score, control_score = (
            float(item["exact_profile"][0]),
            float(item["control_profile"][0]),
        )
        result[method] = dict(
            score=exact_score - control_score if method.endswith("_margin") else exact_score,
            exact_score=exact_score,
            control_score=control_score,
            cfo_hz=float(cfo_hz),
            control_cfo_hz=float(cfo_hz),
        )
    return result
