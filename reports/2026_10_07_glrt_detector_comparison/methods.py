"""Bounded correlator-domain detector prototypes; no production dependencies.

Rows are independent frames, columns the same 64 successive pilot symbols.
All coherent methods search one common FFT CFO grid and allow a separate complex
amplitude per frame. Scores are statistics, never probabilities. ``score_bank``
pools frames; ``score_individual_bank`` treats each row as a separate trial.
``score_trial_bank`` pools frames within each trial in a [trials,frames,64] batch.

Gaussian assumptions: raw correlations r=<pilot,IQ>, template energies E,
z=r/sqrt(E), white circular Gaussian noise in z, signal a*sqrt(E)*exp(j*w*t).
This assumes independent symbol noise and a common within-frame channel. Omitting
E asserts equal unit template energies. The normalized matched-subspace GLRT is
projected energy / total energy (monotone in the unknown-variance likelihood
ratio). It is a correlator-domain test, not the full raw-IQ likelihood: discarded
orthogonal IQ energy is unavailable. The adaptive version substitutes an
independently estimated covariance in these z coordinates. A common covariance
for exact/control assumes their normalized null covariance is the same.

Segmented GLRT allows separate amplitudes in the two 32-symbol halves, at a
common CFO. Its larger signal subspace requires its own null calibration.
Lag1 is the conventional magnitude-normalized differential statistic; its
phase CFO estimate is quantized to the same grid, rather than a coherent search.
Methods with a ``_margin`` suffix use exact minus control as their score.
Gaussian/adaptive margins are diagnostic ablations of control subtraction;
the corresponding natural exact statistics remain the primary comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np


@dataclass
class Whitener:
    """Covariance in column-vector convention R=E[z z^H], trained independently."""

    covariance: np.ndarray
    precision: np.ndarray
    shrinkage: float
    training_rows: int
    _steering_energy: dict = field(default_factory=dict, repr=False)


def _matrix(values: np.ndarray, name: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim != 2 or result.shape[1] != 64:
        raise ValueError(f"{name} must have shape [rows,64]")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be finite")
    return result


def fit_whitener(training: np.ndarray, *, shrinkage: float = 0.25) -> Whitener:
    """Fit full covariance, with fixed trace-target shrinkage and known zero mean.

    Training must be independent of evaluated observations and contain normalized
    noise correlations z. No fitting to held-out test rows occurs here.
    """
    rows = _matrix(training, "training")
    if len(rows) < 2:
        raise ValueError("training needs at least two independent noise rows")
    if not np.isfinite(shrinkage) or not 0 < shrinkage <= 1:
        raise ValueError("shrinkage must lie in (0,1]")
    # Each row stores z.T, hence X.T @ X.conj(), not X.conj().T @ X.
    covariance = rows.T @ rows.conj() / len(rows)
    scale = float(np.trace(covariance).real / 64)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("training must have finite positive energy")
    covariance = (1 - shrinkage) * covariance + shrinkage * scale * np.eye(64)
    covariance = (covariance + covariance.conj().T) / 2
    eigenvalues, basis = np.linalg.eigh(covariance)
    precision = (basis / eigenvalues[None, :]) @ basis.conj().T
    covariance.setflags(write=False)
    precision.setflags(write=False)
    return Whitener(covariance, precision, float(shrinkage), len(rows))


@lru_cache(maxsize=8)
def _grid(symbol_step_s: float, fft_size: int) -> np.ndarray:
    result = np.fft.fftfreq(fft_size, d=symbol_step_s)
    result.setflags(write=False)
    return result


def _energies(value: np.ndarray | None, name: str) -> np.ndarray:
    result = np.ones(64) if value is None else np.asarray(value, dtype=float)
    if result.shape != (64,) or not np.all(np.isfinite(result)) or np.any(result <= 0):
        raise ValueError(f"{name} must be a finite positive [64] vector")
    return result


def _peak(
    power: np.ndarray, denominator: np.ndarray, grid: np.ndarray, individual: bool, grouping=None
):
    if grouping is not None:
        power = power.reshape(*grouping, len(grid)).sum(axis=1)
        denominator = denominator.reshape(grouping).sum(axis=1)
    elif not individual:
        power = power.sum(axis=0, keepdims=True)
        denominator = np.array([denominator.sum()])
    peaks = np.argmax(power, axis=1)
    score = np.divide(
        power[np.arange(len(power)), peaks],
        denominator,
        out=np.zeros(len(power)),
        where=denominator > 0,
    )
    cfo = np.where(denominator > 0, grid[peaks], 0.0)
    return score, cfo


def _one_bank(values, energy, grid, fft_size, whitener, individual, grouping=None):
    raw_power = np.abs(np.fft.fft(values, n=fft_size, axis=1)) ** 2
    ceiling = np.sum(np.abs(values), axis=1) ** 2
    normalized = values / np.sqrt(energy)
    received_energy = np.sum(np.abs(normalized) ** 2, axis=1)
    result = {
        "current_glrt64_margin": _peak(raw_power, ceiling, grid, individual, grouping),
        "gaussian_glrt64": _peak(
            raw_power / energy.sum(), received_energy, grid, individual, grouping
        ),
    }
    segment_power = sum(
        np.abs(np.fft.fft(values[:, start : start + 32], n=fft_size, axis=1)) ** 2
        / energy[start : start + 32].sum()
        for start in (0, 32)
    )
    result["segmented_glrt32"] = _peak(segment_power, received_energy, grid, individual, grouping)
    products = normalized[:, 1:] * normalized[:, :-1].conj()
    total = products.sum(axis=1)
    weight = np.abs(products).sum(axis=1)
    if grouping is not None:
        total = total.reshape(grouping).sum(axis=1)
        weight = weight.reshape(grouping).sum(axis=1)
    elif not individual:
        total = np.array([total.sum()])
        weight = np.array([weight.sum()])
    differential = np.divide(np.abs(total), weight, out=np.zeros(len(total)), where=weight > 0)
    # The unit one-symbol phasor has the same frequency period as the bank.
    phases = np.exp(-2j * np.pi * np.arange(fft_size) / fft_size)
    cfo = grid[np.argmax((total[:, None] * phases).real, axis=1)]
    result["differential_lag1"] = differential, np.where(weight > 0, cfo, 0.0)
    if whitener is not None:
        precision = np.asarray(whitener.precision)
        if precision.shape != (64, 64) or not np.all(np.isfinite(precision)):
            raise ValueError("whitener precision must be a finite [64,64] matrix")
        projected = normalized @ precision.T
        whitened_energy = np.sum(normalized.conj() * projected, axis=1).real
        key = fft_size, energy.tobytes()
        if key not in whitener._steering_energy:
            # The grid phase is independent of symbol step on an FFT bank.
            steering = np.exp(
                2j * np.pi * np.arange(fft_size)[:, None] * np.arange(64)[None, :] / fft_size
            ) * np.sqrt(energy)
            denominator = np.sum(steering.conj() * (steering @ precision.T), axis=1).real
            if np.any(denominator <= 0):
                raise ValueError("whitener must be positive definite")
            whitener._steering_energy[key] = denominator
        amplitude = np.fft.fft(projected * np.sqrt(energy), n=fft_size, axis=1)
        power = np.abs(amplitude) ** 2 / whitener._steering_energy[key]
        result["adaptive_nmf64"] = _peak(power, whitened_energy, grid, individual, grouping)
    return result


def _bank(
    exact,
    control,
    *,
    symbol_step_s,
    fft_size,
    whitener,
    exact_template_energy,
    control_template_energy,
    individual,
    grouping=None,
):
    exact = _matrix(exact, "exact")
    control = _matrix(control, "control")
    if exact.shape != control.shape:
        raise ValueError("exact and control must share shape")
    if not np.isfinite(symbol_step_s) or symbol_step_s <= 0:
        raise ValueError("symbol_step_s must be finite and positive")
    if isinstance(fft_size, bool) or not isinstance(fft_size, int) or fft_size < 64:
        raise ValueError("fft_size must be an integer >=64")
    grid = _grid(float(symbol_step_s), fft_size)
    # FFT accepts empty frame sets, and pooled spectra then yield zero scores.
    exact_scores = _one_bank(
        exact,
        _energies(exact_template_energy, "exact_template_energy"),
        grid,
        fft_size,
        whitener,
        individual,
        grouping,
    )
    control_scores = _one_bank(
        control,
        _energies(control_template_energy, "control_template_energy"),
        grid,
        fft_size,
        whitener,
        individual,
        grouping,
    )
    result = {}
    for method, (exact_score, cfo) in exact_scores.items():
        control_score, control_cfo = control_scores[method]
        score = exact_score - control_score if method.endswith("_margin") else exact_score
        item = dict(
            score=score,
            cfo_hz=cfo,
            exact_score=exact_score,
            control_score=control_score,
            control_cfo_hz=control_cfo,
        )
        result[method] = (
            item if individual else {key: float(value[0]) for key, value in item.items()}
        )
    for method in ("gaussian_glrt64", "adaptive_nmf64"):
        if method in result:
            result[method + "_margin"] = dict(result[method])
            result[method + "_margin"]["score"] = (
                result[method]["exact_score"] - result[method]["control_score"]
            )
    return result


def score_bank(
    exact,
    control,
    *,
    symbol_step_s=4.4e-6,
    fft_size=512,
    whitener=None,
    exact_template_energy=None,
    control_template_energy=None,
):
    """Return scalar statistics pooling rows as frames of one observation."""
    return _bank(
        exact,
        control,
        symbol_step_s=symbol_step_s,
        fft_size=fft_size,
        whitener=whitener,
        exact_template_energy=exact_template_energy,
        control_template_energy=control_template_energy,
        individual=False,
    )


def score_individual_bank(
    exact,
    control,
    *,
    symbol_step_s=4.4e-6,
    fft_size=512,
    whitener=None,
    exact_template_energy=None,
    control_template_energy=None,
):
    """Return array statistics, treating each row as an independent trial."""
    return _bank(
        exact,
        control,
        symbol_step_s=symbol_step_s,
        fft_size=fft_size,
        whitener=whitener,
        exact_template_energy=exact_template_energy,
        control_template_energy=control_template_energy,
        individual=True,
    )


def score_trial_bank(
    exact,
    control,
    *,
    symbol_step_s=4.4e-6,
    fft_size=512,
    whitener=None,
    exact_template_energy=None,
    control_template_energy=None,
):
    """Return per-trial arrays pooling independent frame amplitudes at common CFO.

    Inputs share shape [trials,frames,64]. This is numerically equivalent to
    stacking ``score_bank(exact[i],control[i])`` over trials, while FFT and full
    covariance operations are batched. Callers can bound memory by chunking trials.
    """
    exact = np.asarray(exact, dtype=np.complex128)
    control = np.asarray(control, dtype=np.complex128)
    if exact.ndim != 3 or exact.shape[-1] != 64 or exact.shape != control.shape:
        raise ValueError("exact and control must share shape [trials,frames,64]")
    grouping = exact.shape[:2]
    return _bank(
        exact.reshape(-1, 64),
        control.reshape(-1, 64),
        symbol_step_s=symbol_step_s,
        fft_size=fft_size,
        whitener=whitener,
        exact_template_energy=exact_template_energy,
        control_template_energy=control_template_energy,
        individual=True,
        grouping=grouping,
    )


# Alternate plural spelling retained for the synthetic runner's initial API plan.
score_trials_bank = score_trial_bank
