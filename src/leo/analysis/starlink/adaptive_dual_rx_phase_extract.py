"""Extract local dual-receiver phase from one adaptive visit.

This module deliberately stops at a local, wrapped receiver observable.  It
does not associate emitters, choose a CFO alias, or infer antenna geometry.
Those decisions need independent inputs downstream.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.adaptive_dual_rx_phase import (
    circular_phase_standard_error_deg,
    coherent_pilot_frames,
    correlate_pilot_symbols,
    fit_linear_phasor,
    pilot_symbol_reference_offsets_s,
    receiver_relative_frequency_hz,
    restore_receiver_relative_phase,
)
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)
from leo.contracts.states import StarlinkEdge


@dataclass(frozen=True, slots=True)
class ReceiverPhaseSeed:
    """Phase-blind GLRT seed for one receiver.

    ``reference_sample`` is the local visit coordinate at which the acquired
    CFO has zero phase.  It may include the persisted fractional epoch offset.
    """

    acquired_cfo_hz: float
    reference_sample: float


@dataclass(frozen=True, slots=True)
class ReceiverFrameSeries:
    receiver_id: int
    frame_starts: tuple[int, ...]
    frame_phasors: tuple[complex, ...]
    control_phasors: tuple[complex, ...]
    within_frame_residual_cfo_hz: float
    exact_to_control_power_ratio: float


@dataclass(frozen=True, slots=True)
class FrameFrequencyBranchLift:
    """Conditional evidence used to lift a receiver-product frequency branch."""

    principal_product_residual_cfo_hz: float
    within_frame_receiver_residual_difference_hz: float
    selected_frame_alias_index: int
    lifted_product_residual_cfo_hz: float
    authority_disagreement_hz: float
    branch_selection_gap_hz: float


@dataclass(frozen=True, slots=True)
class DualReceiverPhaseObservation:
    center_sample: float
    wrapped_phase_rad: float
    relative_frequency_hz: float
    relative_frequency_standard_error_hz: float
    resultant_length: float
    phase_standard_error_deg: float
    independent_frame_count: int
    receivers: tuple[ReceiverFrameSeries, ReceiverFrameSeries]
    frame_frequency_branch_lift: FrameFrequencyBranchLift | None = None


@dataclass(frozen=True, slots=True)
class ReceiverOffsetAuthorityApplication:
    """An observation rebound to an independent RX1-minus-RX0 CFO authority."""

    receiver_offset_authority_hz: float
    common_reference_sample: float
    original_seeds: tuple[ReceiverPhaseSeed, ReceiverPhaseSeed]
    applied_seeds: tuple[ReceiverPhaseSeed, ReceiverPhaseSeed]
    observation: DualReceiverPhaseObservation


def shared_frame_starts(
    sample_count: int,
    sample_rate_hz: float,
    frame_epoch_sample: int,
    *,
    frame_radius: int = 9,
) -> npt.NDArray[np.int64]:
    """Return one bounded frame lattice used unchanged by both receivers."""
    if (
        type(sample_count) is not int
        or sample_count <= 0
        or not math.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0
        or type(frame_epoch_sample) is not int
        or type(frame_radius) is not int
        or frame_radius < 1
    ):
        raise ValueError("invalid adaptive phase frame geometry")
    frame_length = round(sample_rate_hz / FRAME_RATE_HZ)
    if frame_length <= 0:
        raise ValueError("sample rate produces an invalid frame length")
    starts = np.asarray(
        [
            frame_epoch_sample + round(offset * sample_rate_hz / FRAME_RATE_HZ)
            for offset in range(-frame_radius, frame_radius + 1)
        ],
        dtype=np.int64,
    )
    return starts[(starts >= 0) & (starts + frame_length <= sample_count)]


def extract_dual_receiver_phase(
    iq: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    edge: StarlinkEdge | str,
    frame_epoch_sample: int,
    seeds: tuple[ReceiverPhaseSeed, ReceiverPhaseSeed],
    *,
    frame_radius: int = 9,
    symbol_indices: npt.NDArray[np.integer] | None = None,
    lift_frame_frequency_branch: bool = False,
) -> DualReceiverPhaseObservation:
    """Extract a wrapped local RX1-minus-RX0 pilot phase.

    Candidate selection must happen before this call and without phase.  A
    single frame lattice indexes both IQ columns, preserving simultaneous
    digitizer sampling.  Acquired CFO phase is restored exactly once at the
    common output epoch.
    """
    values = np.asarray(iq)
    if values.ndim != 2 or values.shape[1] != 2 or not np.iscomplexobj(values):
        raise ValueError("adaptive phase IQ must have two complex receiver columns")
    if len(seeds) != 2 or any(
        not math.isfinite(seed.acquired_cfo_hz) or not math.isfinite(seed.reference_sample)
        for seed in seeds
    ):
        raise ValueError("adaptive phase seeds must be finite and dual receiver")
    selected_edge = StarlinkEdge(edge)
    exact = np.asarray(qin_edge_pilot_frame(sample_rate_hz, selected_edge), np.complex128)
    control = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL),
        np.complex128,
    )
    symbols = (
        np.arange(2, 66, dtype=int)
        if symbol_indices is None
        else np.asarray(symbol_indices, dtype=int)
    )
    if symbols.ndim != 1 or len(symbols) < 8 or np.any(np.diff(symbols) <= 0):
        raise ValueError("pilot symbols must be ordered and contain at least eight entries")
    symbol_steps = np.diff(symbols)
    if lift_frame_frequency_branch and np.any(symbol_steps != symbol_steps[0]):
        raise ValueError("branch-lifted pilot symbols must have one uniform stride")
    coarse_frequency_interval_s = (
        int(symbol_steps[0]) * OFDM_SYMBOL_DURATION_S if lift_frame_frequency_branch else None
    )
    starts = shared_frame_starts(
        len(values), sample_rate_hz, frame_epoch_sample, frame_radius=frame_radius
    )
    if len(starts) < 3:
        raise ValueError("fewer than three complete shared frames")
    offsets_s = pilot_symbol_reference_offsets_s(
        sample_rate_hz, OFDM_SYMBOL_DURATION_S, symbols, exact
    )

    series: list[ReceiverFrameSeries] = []
    for receiver, seed in enumerate(seeds):
        exact_correlations = correlate_pilot_symbols(
            values,
            starts,
            exact,
            seed.acquired_cfo_hz,
            seed.reference_sample,
            receiver,
            symbols,
            sample_rate_hz,
            OFDM_SYMBOL_DURATION_S,
        )
        control_correlations = correlate_pilot_symbols(
            values,
            starts,
            control,
            seed.acquired_cfo_hz,
            seed.reference_sample,
            receiver,
            symbols,
            sample_rate_hz,
            OFDM_SYMBOL_DURATION_S,
        )
        frames, controls, residual_hz, ratio = coherent_pilot_frames(
            exact_correlations,
            control_correlations,
            offsets_s,
            OFDM_SYMBOL_DURATION_S,
            coarse_frequency_sample_interval_s=coarse_frequency_interval_s,
        )
        series.append(
            ReceiverFrameSeries(
                receiver_id=receiver,
                frame_starts=tuple(map(int, starts)),
                frame_phasors=tuple(map(complex, frames)),
                control_phasors=tuple(map(complex, controls)),
                within_frame_residual_cfo_hz=residual_hz,
                exact_to_control_power_ratio=ratio,
            )
        )

    receiver_product = np.asarray(series[1].frame_phasors) * np.conj(
        np.asarray(series[0].frame_phasors)
    )
    weights = np.sqrt(
        np.maximum(np.abs(series[0].frame_phasors), np.finfo(float).tiny)
        * np.maximum(np.abs(series[1].frame_phasors), np.finfo(float).tiny)
    )
    center_sample = float(np.average(starts, weights=weights))
    principal_hz, corrected_phase_rad, resultant = fit_linear_phasor(
        receiver_product,
        starts / sample_rate_hz,
        weights,
        center_sample / sample_rate_hz,
    )
    fitted_hz = principal_hz
    branch_lift = None
    if lift_frame_frequency_branch:
        authority_hz = (
            series[1].within_frame_residual_cfo_hz - series[0].within_frame_residual_cfo_hz
        )
        alias_index = round((authority_hz - principal_hz) / FRAME_RATE_HZ)
        alias_center_hz = principal_hz + alias_index * FRAME_RATE_HZ
        fitted_hz, corrected_phase_rad, resultant = fit_linear_phasor(
            receiver_product,
            starts / sample_rate_hz,
            weights,
            center_sample / sample_rate_hz,
            minimum_frequency_hz=alias_center_hz - FRAME_RATE_HZ / 2,
            maximum_frequency_hz=alias_center_hz + FRAME_RATE_HZ / 2,
        )
        branch_lift = FrameFrequencyBranchLift(
            principal_product_residual_cfo_hz=principal_hz,
            within_frame_receiver_residual_difference_hz=authority_hz,
            selected_frame_alias_index=alias_index,
            lifted_product_residual_cfo_hz=fitted_hz,
            authority_disagreement_hz=authority_hz - fitted_hz,
            branch_selection_gap_hz=FRAME_RATE_HZ - 2 * abs(authority_hz - alias_center_hz),
        )
    frame_times_s = starts / sample_rate_hz
    centered_s = frame_times_s - center_sample / sample_rate_hz
    unit_product = receiver_product / np.maximum(abs(receiver_product), np.finfo(float).tiny)
    residual_rad = np.angle(
        unit_product * np.exp(-1j * (corrected_phase_rad + 2 * np.pi * fitted_hz * centered_s))
    )
    weighted_residual_variance = float(np.average(residual_rad**2, weights=weights))
    frequency_information = float(np.sum(weights * centered_s**2))
    frequency_standard_error_hz = math.sqrt(
        weighted_residual_variance * float(np.sum(weights)) / max(frequency_information, 1e-30)
    ) / (2 * np.pi * math.sqrt(max(len(starts) - 2, 1)))
    phase_rad = restore_receiver_relative_phase(
        corrected_phase_rad,
        (seeds[0].acquired_cfo_hz, seeds[1].acquired_cfo_hz),
        center_sample,
        (seeds[0].reference_sample, seeds[1].reference_sample),
        sample_rate_hz,
    )
    return DualReceiverPhaseObservation(
        center_sample=center_sample,
        wrapped_phase_rad=phase_rad,
        relative_frequency_hz=receiver_relative_frequency_hz(
            (seeds[0].acquired_cfo_hz, seeds[1].acquired_cfo_hz), fitted_hz
        ),
        relative_frequency_standard_error_hz=frequency_standard_error_hz,
        resultant_length=resultant,
        phase_standard_error_deg=circular_phase_standard_error_deg(resultant, len(starts)),
        independent_frame_count=len(starts),
        receivers=(series[0], series[1]),
        frame_frequency_branch_lift=branch_lift,
    )


def extract_dual_receiver_phase_branch_lifted(
    iq: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    edge: StarlinkEdge | str,
    frame_epoch_sample: int,
    seeds: tuple[ReceiverPhaseSeed, ReceiverPhaseSeed],
    *,
    frame_radius: int = 9,
    symbol_indices: npt.NDArray[np.integer] | None = None,
) -> DualReceiverPhaseObservation:
    """Extract phase with a conditional lift of the 750 Hz frequency branch.

    The individual receiver residuals are estimated from the pilot symbols
    within each frame.  Their difference chooses the integer 750 Hz branch of
    the receiver-product slope before phase is evaluated or propagated.  The
    published V2 extractor keeps its historical unresolved behavior through
    :func:`extract_dual_receiver_phase`; new analyses must opt into this
    additive estimator explicitly.  Callers must retain the authority
    disagreement and competing-branch gap; this local evidence does not
    resolve the separate pilot-symbol CFO ambiguity.
    """

    return extract_dual_receiver_phase(
        iq,
        sample_rate_hz,
        edge,
        frame_epoch_sample,
        seeds,
        frame_radius=frame_radius,
        symbol_indices=symbol_indices,
        lift_frame_frequency_branch=True,
    )


def extract_dual_receiver_phase_with_offset_authority(
    iq: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    edge: StarlinkEdge | str,
    frame_epoch_sample: int,
    seeds: tuple[ReceiverPhaseSeed, ReceiverPhaseSeed],
    receiver_offset_authority_hz: float,
    *,
    common_reference_sample: float | None = None,
    frame_radius: int = 9,
    symbol_indices: npt.NDArray[np.integer] | None = None,
) -> ReceiverOffsetAuthorityApplication:
    """Re-correlate both receivers on one independently established CFO branch.

    A broadband cross-ambiguity measurement can establish RX1-minus-RX0 CFO
    without using the Qin symbol alias.  RX1 is then seeded at RX0 plus that
    offset and both derotations use one reference sample.  This makes a common
    pilot-symbol alias and template response cancel in RX1 times conjugate RX0.

    The authority must be bound and persisted by the calling analysis.  This
    function does not infer or validate it from the pilot being measured.
    """

    if len(seeds) != 2 or not math.isfinite(receiver_offset_authority_hz):
        raise ValueError("receiver offset authority and dual seeds must be finite")
    reference = (
        seeds[0].reference_sample
        if common_reference_sample is None
        else float(common_reference_sample)
    )
    if not math.isfinite(reference):
        raise ValueError("common receiver offset authority reference must be finite")
    applied = (
        ReceiverPhaseSeed(seeds[0].acquired_cfo_hz, reference),
        ReceiverPhaseSeed(
            seeds[0].acquired_cfo_hz + receiver_offset_authority_hz,
            reference,
        ),
    )
    observation = extract_dual_receiver_phase_branch_lifted(
        iq,
        sample_rate_hz,
        edge,
        frame_epoch_sample,
        applied,
        frame_radius=frame_radius,
        symbol_indices=symbol_indices,
    )
    return ReceiverOffsetAuthorityApplication(
        receiver_offset_authority_hz=receiver_offset_authority_hz,
        common_reference_sample=reference,
        original_seeds=seeds,
        applied_seeds=applied,
        observation=observation,
    )
