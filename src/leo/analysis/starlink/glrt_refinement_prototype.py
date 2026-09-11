"""Offline experiments in continuous GLRT frequency and timing refinement.

No production caller or persisted contract uses this module. Correlations and
normalization are shared with the reviewed GLRT implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np

from leo.analysis.starlink.fractional_epoch import fractional_log_peak
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodScore,
    _coherent_ceiling,
    _conditioned_correlation_workspace,
    _score,
    _uniform_glrt_geometry,
)
from leo.contracts.states import StarlinkEdge


@dataclass(frozen=True)
class FrequencyPeak:
    score: float
    frequency_hz: float
    coarse_frequency_hz: float
    coarse_score: float
    runner_up_gap: float
    evaluations: int


def continuous_peak(values, symbol_step_s, *, coarse_size=512, tolerance_hz=0.25):
    """Refine the three strongest distinct FFT maxima using the exact DTFT.

    Search unwrapped intervals, including at the FFT seam. The autocorrelation
    polynomial is the sum of per-frame powers, not a single-tone approximation.
    """
    values = np.asarray(values, dtype=np.complex128)
    if values.ndim != 2 or values.shape[1] < 2:
        raise ValueError("expected frame by symbol matrix with at least two symbols")
    if not np.all(np.isfinite(values)) or not np.isfinite(symbol_step_s) or symbol_step_s <= 0:
        raise ValueError("correlations and symbol interval must be finite")
    count = values.shape[1]
    if coarse_size < 2 * count - 1 or not 0 < tolerance_hz < 1 / symbol_step_s / coarse_size:
        raise ValueError("unsupported coarse size or frequency tolerance")
    short_size = 1 << (2 * count - 2).bit_length()
    transformed = np.fft.fft(values, n=short_size, axis=1)
    autocorrelation = np.fft.ifft(np.sum(abs(transformed) ** 2, axis=0))
    packed = np.zeros(coarse_size, dtype=complex)
    packed[:count] = autocorrelation[:count]
    packed[-(count - 1) :] = autocorrelation[-(count - 1) :]
    ceiling = _coherent_ceiling(values)
    if ceiling <= 0:
        return FrequencyPeak(0.0, 0.0, 0.0, 0.0, 0.0, 0)
    spectrum = np.fft.fft(packed).real / ceiling
    grid = np.fft.fftfreq(coarse_size, d=symbol_step_s)
    maxima = np.flatnonzero(
        (spectrum >= np.roll(spectrum, 1)) & (spectrum >= np.roll(spectrum, -1))
    )
    maxima = sorted(maxima, key=lambda i: (-spectrum[i], i))[:3]
    lags = np.arange(1, count) * symbol_step_s
    coefficients = autocorrelation[1:count] / ceiling
    constant = autocorrelation[0].real / ceiling
    evaluations = 0

    def objective(frequency):
        nonlocal evaluations
        evaluations += 1
        return float(
            constant + 2 * np.real(np.sum(coefficients * np.exp(-2j * np.pi * frequency * lags)))
        )

    spacing = 1 / symbol_step_s / coarse_size
    ratio = (np.sqrt(5) - 1) / 2
    candidates = []
    for index in maxima:
        left, right = grid[index] - spacing, grid[index] + spacing
        x1, x2 = right - ratio * (right - left), left + ratio * (right - left)
        y1, y2 = objective(x1), objective(x2)
        for _ in range(40):
            if right - left <= tolerance_hz:
                break
            if y1 < y2:
                left, x1, y1 = x1, x2, y2
                x2 = left + ratio * (right - left)
                y2 = objective(x2)
            else:
                right, x2, y2 = x2, x1, y1
                x1 = right - ratio * (right - left)
                y1 = objective(x1)
        score, frequency = max((y1, x1), (y2, x2), (float(spectrum[index]), float(grid[index])))
        candidates.append((score, frequency, int(index)))
    candidates.sort(reverse=True)
    score, frequency, index = candidates[0]
    period = 1 / symbol_step_s
    frequency = (frequency + period / 2) % period - period / 2
    gap = score - candidates[1][0] if len(candidates) > 1 else 0.0
    return FrequencyPeak(
        score, frequency, float(grid[index]), float(spectrum[index]), gap, evaluations
    )


def continuous_glrt_score(samples, fs, *, anchor, offset, conditioning_cfo_hz, edge):
    symbols = np.arange(2, 66)
    workspace = _conditioned_correlation_workspace(
        np.asarray(samples, dtype=complex),
        fs,
        anchor,
        conditioning_cfo_hz,
        selected_symbols=symbols,
        fractional_epoch_offset_samples=offset,
        edge=StarlinkEdge(edge),
    )
    exact, control = workspace.select(symbols), workspace.select(symbols, control=True)
    if not exact.values.size:
        return _score(PilotMethod.GLRT64, 0, 0, 0, conditioning_cfo_hz), {}
    if not _uniform_glrt_geometry(exact, size=512):
        raise ValueError("prototype requires uniform symbol geometry")
    a = continuous_peak(exact.values, exact.symbol_step_s)
    b = continuous_peak(control.values, control.symbol_step_s)
    return _score(PilotMethod.GLRT64, a.score, b.score, a.frequency_hz, conditioning_cfo_hz), {
        "exact": asdict(a),
        "control": asdict(b),
    }


def joint_refine(samples, fs, *, anchor, offset, conditioning_cfo_hz, edge, initial_score):
    """Two bounded coordinate passes; accept only nondecreasing exact scores.

    The timing radius is physical (800 ns from the original integer anchor).
    A CFO update may move at most 2 kHz on the existing symbol-alias branch.
    Both exact and control spectra receive the same full frequency refinement.
    """
    current = initial_score
    history = []
    period_hz = 1 / 4.4e-6
    accepted = 0

    def evaluate(trial_offset, trial_conditioning):
        score, _ = continuous_glrt_score(
            samples,
            fs,
            anchor=anchor,
            offset=trial_offset,
            conditioning_cfo_hz=trial_conditioning,
            edge=edge,
        )
        delta = (
            score.tracking_cfo_hz - current.tracking_cfo_hz + period_hz / 2
        ) % period_hz - period_hz / 2
        tracking = current.tracking_cfo_hz + delta
        score = replace(
            score, tracking_cfo_hz=tracking, residual_cfo_hz=tracking - trial_conditioning
        )
        if abs(delta) > 2000:
            return None
        return score

    for step_ns in (200.0, 100.0):
        before = current.exact_score
        proposal_conditioning = current.tracking_cfo_hz
        proposal = evaluate(offset, proposal_conditioning)
        cfo_accepted = proposal is not None and proposal.exact_score > current.exact_score
        if cfo_accepted:
            current, conditioning_cfo_hz = proposal, proposal_conditioning
            accepted += 1
        step = step_ns * 1e-9 * fs
        offsets = [offset - step, offset, offset + step]
        scores: list[PilotMethodScore | None] = [
            evaluate(x, conditioning_cfo_hz) if abs(x / fs) <= 800e-9 else None for x in offsets
        ]
        candidates = [(current.exact_score, offset, current)]
        candidates.extend(
            (s.exact_score, x, s) for x, s in zip(offsets, scores, strict=True) if s is not None
        )
        if all(s is not None for s in scores):
            fraction, _ = fractional_log_peak(tuple(s.exact_score for s in scores), (-1, 0, 1))
            if fraction is not None:
                trial = offset + fraction * step
                scored = evaluate(trial, conditioning_cfo_hz)
                if scored is not None:
                    candidates.append((scored.exact_score, trial, scored))
        _, offset, current = max(candidates, key=lambda item: item[0])
        history.append(
            {
                "before_score": before,
                "after_score": current.exact_score,
                "cfo_update_accepted": cfo_accepted,
                "offset_samples": offset,
                "tracking_cfo_hz": current.tracking_cfo_hz,
                "conditioning_cfo_hz": conditioning_cfo_hz,
            }
        )
    return (
        offset,
        current,
        {
            "history": history,
            "accepted_cfo_updates": accepted,
            "timing_boundary": abs(offset / fs) >= 799e-9,
        },
    )
