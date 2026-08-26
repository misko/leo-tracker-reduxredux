"""Held-out odd-Qin complex frame evidence.

This narrow module preserves the byte identity of the historically hash-bound
all/split-Qin implementation in :mod:`leo.analysis.qam.pilot`.  Although the
caller supplies a guarded full frame, only zero-based odd Qin symbols are read,
demodulated, or scored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from leo.analysis.qam.pilot import (
    PilotFrameCfoConfig,
    PilotFrameComplexFold,
    _fit_phase_slope_frame,
    _freeze,
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
class PilotFrameComplexOddObservation:
    """One held-out odd-Qin fold with no even-Qin statistic."""

    status: NumericalStatus
    reason: str
    frame_start_sample: int
    reference_sample: float
    odd: PilotFrameComplexFold | None
    qin_symbol_indices: str = "zero-based-odd-1-through-299"
    known_symbols_only: bool = True
    candidate_only: bool = True
    carrier_phase_period_rad: float = math.pi
    absolute_carrier_phase_resolved: bool = False
    frame_timing_is_receiver_relative: bool = True


def estimate_edge_pilot_frame_complex_odd(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    frame_start_sample: int,
    acquisition_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    config: PilotFrameCfoConfig | None = None,
) -> PilotFrameComplexOddObservation:
    """Return a target response formed from odd Qin symbols only."""

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

    symbol_times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_offset_s = float(np.mean(symbol_times_s))
    reference_sample = float(frame_start + reference_offset_s * sample_rate_hz)
    pilots = _demodulate_odd_qin(
        values,
        sample_rate_hz,
        selected_edge,
        acquisition_absolute_cfo_hz,
    )
    if not np.all(np.isfinite(pilots)):
        raise ValueError("odd-Qin samples must be finite")
    if float(np.sum(np.abs(pilots) ** 2)) <= np.finfo(float).tiny:
        return PilotFrameComplexOddObservation(
            status=NumericalStatus.NO_RESULT,
            reason="zero_pilot_energy",
            frame_start_sample=frame_start,
            reference_sample=reference_sample,
            odd=None,
        )
    expected = qin_edge_pilot_symbols(selected_edge)[1::2]
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL)[1::2]
    centered_times_s = symbol_times_s - reference_offset_s
    fit = _fit_phase_slope_frame(
        pilots * np.conj(expected),
        pilots * np.conj(control),
        centered_times_s[1::2],
        maximum_residual_cfo_hz=settings.residual_half_width_hz,
    )

    local_reference_sample = 1.0 + reference_offset_s * sample_rate_hz
    phase_cycles = math.remainder(
        acquisition_absolute_cfo_hz * local_reference_sample / sample_rate_hz,
        1.0,
    )
    capture_gauge = np.exp(2j * np.pi * phase_cycles)
    boundary_tolerance_hz = max(0.05, 1e-6 * settings.residual_half_width_hz)
    boundary = bool(
        abs(abs(fit.residual_cfo_hz) - settings.residual_half_width_hz) <= boundary_tolerance_hz
    )
    odd = PilotFrameComplexFold(
        residual_cfo_hz=float(fit.residual_cfo_hz),
        absolute_cfo_hz=float(acquisition_absolute_cfo_hz + fit.residual_cfo_hz),
        frequency_uncertainty_hz=float(fit.frequency_uncertainty_hz),
        exact_coherence=float(fit.exact_coherence),
        control_coherence=float(fit.control_coherence),
        coherence_margin=float(fit.exact_coherence - fit.control_coherence),
        phase_residual_rms_rad=float(fit.phase_residual_rms_rad),
        search_boundary=boundary,
        channel_vector=_freeze(fit.channel_vector * capture_gauge),
    )
    return PilotFrameComplexOddObservation(
        status=NumericalStatus.COMPLETE,
        reason="complete",
        frame_start_sample=frame_start,
        reference_sample=reference_sample,
        odd=odd,
    )


def _demodulate_odd_qin(
    samples: np.ndarray,
    sample_rate_hz: float,
    edge: StarlinkEdge,
    absolute_cfo_hz: float,
) -> np.ndarray:
    """Demodulate exactly the zero-based odd Qin positions."""

    result = np.empty((150, 8), dtype=np.complex128)
    for positions, relative, solves in _known_pilot_layout(sample_rate_hz, edge):
        selected = positions % 2 == 1
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
