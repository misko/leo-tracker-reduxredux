"""Response-blind even-Qin frame-CFO evidence.

This narrow module keeps cohort-construction evidence separate from the
historically hash-bound all/split-Qin estimator implementation in
``leo.analysis.qam.pilot``.  The caller still supplies a guarded full frame,
but only zero-based even Qin symbols are demodulated or scored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from leo.analysis.qam.pilot import (
    PilotFrameCfoConfig,
    _fit_phase_slope_frame,
    _known_pilot_layout,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_symbols,
)
from leo.contracts.states import StarlinkEdge


@dataclass(frozen=True, slots=True)
class PilotFrameCfoEvenEvidence:
    """Response-blind CFO evidence from the even Qin symbols of one frame."""

    status: NumericalStatus
    training_supported: bool
    training_rejection_reasons: tuple[str, ...]
    frame_start_sample: int
    reference_sample: float
    residual_cfo_hz: float | None
    absolute_cfo_hz: float | None
    frequency_uncertainty_hz: float | None
    exact_coherence: float | None
    control_coherence: float | None
    coherence_margin: float | None
    search_boundary: bool
    known_symbols_only: bool = True
    candidate_only: bool = True
    odd_symbols_evaluated: bool = False


def estimate_edge_pilot_frame_cfo_even_evidence(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    frame_start_sample: int,
    acquisition_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    config: PilotFrameCfoConfig | None = None,
) -> PilotFrameCfoEvenEvidence:
    """Estimate one frame without demodulating or evaluating odd Qin symbols.

    Upstream source, alias, and epoch conditioning are outside this local API
    and may have used all-Qin evidence.
    """

    values = np.asarray(samples, dtype=np.complex128)
    settings = config or PilotFrameCfoConfig()
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    minimum_rate_hz = 8 * 234_375.0
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz:.0f} Hz")
    if not isinstance(frame_start_sample, (int, np.integer)):
        raise ValueError("frame start must be an integer sample")
    if not math.isfinite(acquisition_absolute_cfo_hz):
        raise ValueError("acquisition absolute CFO must be finite")
    frame_start = int(frame_start_sample)
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if frame_start < 1:
        raise ValueError("absolute frame start must leave a preceding recording sample")
    if values.size != frame_content + 2:
        raise ValueError("samples must be exactly one frame with one-sample guards")

    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    reference_sample = float(frame_start + reference_offset_s * sample_rate_hz)
    pilots = _demodulate_even_qin(
        values,
        sample_rate_hz,
        selected_edge,
        acquisition_absolute_cfo_hz,
    )
    if not np.all(np.isfinite(pilots)):
        raise ValueError("even-Qin samples must be finite")
    if float(np.sum(np.abs(pilots) ** 2)) <= np.finfo(float).tiny:
        return _empty_frame_cfo_even(frame_start, reference_sample)

    expected = qin_edge_pilot_symbols(selected_edge)[::2]
    control = qin_edge_pilot_symbols(
        selected_edge,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )[::2]
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    fit = _fit_phase_slope_frame(
        pilots * np.conj(expected),
        pilots * np.conj(control),
        times_s[::2],
        maximum_residual_cfo_hz=settings.residual_half_width_hz,
    )
    boundary_tolerance_hz = max(0.05, 1e-6 * settings.residual_half_width_hz)
    boundary = bool(
        abs(abs(fit.residual_cfo_hz) - settings.residual_half_width_hz) <= boundary_tolerance_hz
    )
    margin = float(fit.exact_coherence - fit.control_coherence)
    rejections = []
    if fit.exact_coherence < settings.minimum_exact_coherence:
        rejections.append("even_exact_coherence_below_minimum")
    if margin < settings.minimum_coherence_margin:
        rejections.append("even_coherence_margin_below_minimum")
    if boundary:
        rejections.append("even_search_boundary")
    return PilotFrameCfoEvenEvidence(
        status=NumericalStatus.COMPLETE,
        training_supported=not rejections,
        training_rejection_reasons=tuple(rejections),
        frame_start_sample=frame_start,
        reference_sample=reference_sample,
        residual_cfo_hz=float(fit.residual_cfo_hz),
        absolute_cfo_hz=float(acquisition_absolute_cfo_hz + fit.residual_cfo_hz),
        frequency_uncertainty_hz=float(fit.frequency_uncertainty_hz),
        exact_coherence=float(fit.exact_coherence),
        control_coherence=float(fit.control_coherence),
        coherence_margin=margin,
        search_boundary=boundary,
    )


def _demodulate_even_qin(
    samples: np.ndarray,
    sample_rate_hz: float,
    edge: StarlinkEdge,
    absolute_cfo_hz: float,
) -> np.ndarray:
    """Demodulate exactly the zero-based even Qin positions."""

    result = np.empty((150, 8), dtype=np.complex128)
    for positions, relative, solves in _known_pilot_layout(sample_rate_hz, edge):
        selected = positions % 2 == 0
        selected_positions = positions[selected]
        absolute = 1 + relative[selected]
        values = np.asarray(samples[absolute], dtype=np.complex128)
        values *= np.exp(-2j * np.pi * absolute_cfo_hz * absolute / sample_rate_hz)
        result[selected_positions // 2] = np.einsum(
            "sfc,sc->sf",
            solves[selected],
            values,
            optimize=False,
        )
    return result


def _empty_frame_cfo_even(
    frame_start_sample: int,
    reference_sample: float,
) -> PilotFrameCfoEvenEvidence:
    return PilotFrameCfoEvenEvidence(
        status=NumericalStatus.NO_RESULT,
        training_supported=False,
        training_rejection_reasons=("zero_pilot_energy",),
        frame_start_sample=int(frame_start_sample),
        reference_sample=float(reference_sample),
        residual_cfo_hz=None,
        absolute_cfo_hz=None,
        frequency_uncertainty_hz=None,
        exact_coherence=None,
        control_coherence=None,
        coherence_margin=None,
        search_boundary=False,
    )
