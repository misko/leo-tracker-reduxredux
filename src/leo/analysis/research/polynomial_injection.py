"""Exact-Qin polynomial-phase injection and rate-calibration kernels.

The array kernels in this module are infrastructure-free.  A caller is
responsible for supplying one digest-verified real-background span and the
already validated preregistration.  Even Qin is the only training source;
odd Qin is retained as response-only evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from leo.analysis.qam.pilot import (
    PilotFrameCfoConfig,
    evaluate_edge_pilot_frame_cfo_likelihood,
)
from leo.analysis.research.adaptive_frame_cfo import (
    AdaptiveFrameCfoConfig,
    AdaptiveFrameCfoPoint,
    track_adaptive_frame_cfo,
)
from leo.analysis.research.polynomial_injection_protocol import (
    HistoryEstimator,
    InjectionScenario,
    PolynomialInjectionProtocol,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.templates import (
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
    template_sha256,
)

_QIN_TEMPLATE_DIGEST = "15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657"


@dataclass(frozen=True, slots=True)
class PolynomialTruth:
    """Injected truth in receiver-clock and physical-time coordinates."""

    receiver_time_s: float
    physical_time_from_reference_s: float
    receiver_canonical_cfo_hz: float
    receiver_raw_cfo_hz: float
    receiver_rate_hz_s: float
    receiver_acceleration_hz_s2: float
    receiver_jerk_hz_s3: float
    physical_cfo_hz: float
    physical_rate_hz_s: float
    physical_acceleration_hz_s2: float
    physical_jerk_hz_s3: float
    alias_label_hz: float


@dataclass(frozen=True, slots=True)
class InjectionDiagnostics:
    """Auditable normalization and occupancy facts for one injected span."""

    background_power: float
    template_power: float
    amplitude_scale: float
    target_snr_db: float
    occupied_frame_count: int
    opportunity_count: int


@dataclass(frozen=True, slots=True)
class FrameCfoEvidence:
    """One exact-Qin frame opportunity with parity-separated response."""

    scenario_id: str
    frame_index: int
    local_frame_start_sample: int
    absolute_frame_start_sample: int
    reference_time_s: float
    occupied: bool
    status: str
    training_supported: bool
    training_rejection_reasons: tuple[str, ...]
    coarse_seed_hz: float
    alias_label_hz: float
    even_canonical_cfo_hz: float | None
    odd_canonical_cfo_hz: float | None
    even_frequency_uncertainty_hz: float | None
    odd_frequency_uncertainty_hz: float | None
    even_exact_coherence: float | None
    even_control_coherence: float | None
    even_coherence_margin: float | None
    even_exact_profile_max: float | None
    even_control_profile_max: float | None
    odd_exact_profile_max: float | None
    odd_control_profile_max: float | None
    even_profile_margin: float | None
    odd_profile_margin: float | None
    even_search_boundary: bool
    odd_search_boundary: bool
    receiver_truth_cfo_hz: float
    physical_truth_cfo_hz: float


@dataclass(frozen=True, slots=True)
class RateEstimateRow:
    """One causal fixed-history rate output and both truth-coordinate errors."""

    scenario_id: str
    estimator: str
    history_s: float
    frame_start_sample: int
    reference_time_s: float
    status: str
    selected_history_s: float | None
    estimate_rate_hz_s: float | None
    rate_sigma_hz_s: float | None
    receiver_truth_rate_hz_s: float
    physical_truth_rate_hz_s: float
    receiver_error_hz_s: float | None
    physical_error_hz_s: float | None
    receiver_covered_95: bool | None
    physical_covered_95: bool | None
    receiver_failure: bool | None
    physical_failure: bool | None
    step_phase: str


@dataclass(frozen=True, slots=True)
class CubicEstimate:
    """One full-span weighted polynomial diagnostic."""

    scenario_id: str
    status: str
    frame_count: int
    reference_time_s: float
    cfo_hz: float | None
    rate_hz_s: float | None
    acceleration_hz_s2: float | None
    jerk_hz_s3: float | None
    cfo_sigma_hz: float | None
    rate_sigma_hz_s: float | None
    acceleration_sigma_hz_s2: float | None
    jerk_sigma_hz_s3: float | None
    residual_rms_hz: float | None
    receiver_rate_truth_hz_s: float
    receiver_acceleration_truth_hz_s2: float
    receiver_jerk_truth_hz_s3: float
    physical_rate_truth_hz_s: float
    physical_acceleration_truth_hz_s2: float
    physical_jerk_truth_hz_s3: float


def qin_frame_starts(*, frame_count: int, sample_rate_hz: int) -> np.ndarray:
    """Return the production-aligned rounded 750 Hz frame lattice."""

    if frame_count < 1 or sample_rate_hz < 1:
        raise ValueError("frame count and sample rate must be positive")
    indexes = np.arange(frame_count, dtype=np.int64)
    starts = np.rint(indexes * sample_rate_hz / 750.0).astype(np.int64)
    if np.any(np.diff(starts) <= 0):
        raise ValueError("frame lattice is not strictly increasing")
    return starts


def occupied_frame_mask(*, frame_count: int, occupancy: float, seed: int) -> np.ndarray:
    """Choose an exact-count, scenario-seeded frame subset without response data."""

    if frame_count < 1:
        raise ValueError("frame_count must be positive")
    if not math.isfinite(occupancy) or not 0.0 < occupancy <= 1.0:
        raise ValueError("occupancy must lie in (0, 1]")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    count = int(round(frame_count * occupancy))
    generator = np.random.Generator(np.random.PCG64(seed + 10_000_000))
    scores = generator.random(frame_count)
    selected = np.argsort(scores, kind="stable")[:count]
    mask = np.zeros(frame_count, dtype=bool)
    mask[selected] = True
    return mask


def truth_at_receiver_time(
    scenario: InjectionScenario,
    receiver_time_s: float,
    *,
    carrier_origin_hz: float,
    reference_time_s: float,
    alias_change_time_s: float,
    cfo_step_time_s: float,
) -> PolynomialTruth:
    """Evaluate the exact injected CFO and its first three derivatives."""

    if not math.isfinite(receiver_time_s):
        raise ValueError("receiver time must be finite")
    clock_scale = 1.0 + scenario.sample_clock_offset_ppm * 1e-6
    if clock_scale <= 0.0:
        raise ValueError("sample-clock scale must remain positive")
    physical_time = (receiver_time_s - reference_time_s) / clock_scale
    rate = scenario.rate_hz_s
    acceleration = scenario.acceleration_hz_s2
    jerk = scenario.jerk_hz_s3
    physical_cfo = (
        carrier_origin_hz
        + rate * physical_time
        + 0.5 * acceleration * physical_time**2
        + jerk * physical_time**3 / 6.0
    )
    if receiver_time_s >= cfo_step_time_s:
        physical_cfo += scenario.cfo_step_hz
    physical_rate = rate + acceleration * physical_time + 0.5 * jerk * physical_time**2
    physical_acceleration = acceleration + jerk * physical_time
    alias_label_hz = scenario.alias_change_hz if receiver_time_s >= alias_change_time_s else 0.0
    receiver_cfo = physical_cfo / clock_scale
    return PolynomialTruth(
        receiver_time_s=receiver_time_s,
        physical_time_from_reference_s=physical_time,
        receiver_canonical_cfo_hz=receiver_cfo,
        receiver_raw_cfo_hz=receiver_cfo + alias_label_hz,
        receiver_rate_hz_s=physical_rate / clock_scale**2,
        receiver_acceleration_hz_s2=physical_acceleration / clock_scale**3,
        receiver_jerk_hz_s3=jerk / clock_scale**4,
        physical_cfo_hz=physical_cfo,
        physical_rate_hz_s=physical_rate,
        physical_acceleration_hz_s2=physical_acceleration,
        physical_jerk_hz_s3=jerk,
        alias_label_hz=alias_label_hz,
    )


def inject_exact_qin(
    background: npt.ArrayLike,
    scenario: InjectionScenario,
    protocol: PolynomialInjectionProtocol,
) -> tuple[np.ndarray, np.ndarray, InjectionDiagnostics]:
    """Inject exact lower-edge Qin frames into one real complex background."""

    values = np.asarray(background, dtype=np.complex64)
    if (
        values.ndim != 1
        or values.size != protocol.background(scenario.background_session_id).sample_count
    ):
        raise ValueError("background must be the exact protocol span")
    if not np.all(np.isfinite(values)):
        raise ValueError("background contains non-finite samples")
    template = qin_edge_pilot_frame(
        protocol.background(scenario.background_session_id).sample_rate_hz,
        "lower",
    )
    if template.size != 3_333 or template_sha256(template) != _QIN_TEMPLATE_DIGEST:
        raise ValueError("runtime Qin template differs from the preregistration")
    starts = qin_frame_starts(
        frame_count=protocol.frame_count,
        sample_rate_hz=protocol.background(scenario.background_session_id).sample_rate_hz,
    )
    if starts[-1] + template.size > values.size:
        raise ValueError("Qin lattice exceeds the frozen background span")
    if np.any(starts[:-1] + template.size > starts[1:]):
        raise ValueError("Qin template placements overlap")
    occupied = occupied_frame_mask(
        frame_count=protocol.frame_count,
        occupancy=scenario.frame_occupancy,
        seed=scenario.seed,
    )
    background_power = float(np.mean(np.abs(values.astype(np.complex128)) ** 2))
    template_power = float(np.mean(np.abs(template.astype(np.complex128)) ** 2))
    if background_power <= np.finfo(float).tiny or template_power <= np.finfo(float).tiny:
        raise ValueError("background and template powers must be positive")
    amplitude = math.sqrt(background_power * 10.0 ** (scenario.snr_db / 10.0) / template_power)
    output = values.copy()
    sample_rate_hz = protocol.background(scenario.background_session_id).sample_rate_hz
    sample_offsets = np.arange(template.size, dtype=float)
    for frame_index in np.flatnonzero(occupied):
        start = int(starts[frame_index])
        receiver_time_s = (start + sample_offsets) / sample_rate_hz
        phase_cycles = _phase_cycles(
            scenario,
            receiver_time_s,
            carrier_origin_hz=protocol.carrier_origin_hz,
            reference_time_s=protocol.reference_time_s,
            alias_change_time_s=protocol.alias_change_time_s,
            cfo_step_time_s=protocol.cfo_step_time_s,
        )
        signal = amplitude * template * np.exp(2j * np.pi * phase_cycles)
        output[start : start + template.size] += np.asarray(signal, dtype=np.complex64)
    return (
        output,
        occupied,
        InjectionDiagnostics(
            background_power=background_power,
            template_power=template_power,
            amplitude_scale=amplitude,
            target_snr_db=scenario.snr_db,
            occupied_frame_count=int(np.sum(occupied)),
            opportunity_count=protocol.frame_count,
        ),
    )


def evaluate_exact_qin_frames(
    samples: npt.ArrayLike,
    occupied: npt.ArrayLike,
    scenario: InjectionScenario,
    protocol: PolynomialInjectionProtocol,
    *,
    absolute_span_start_sample: int,
) -> tuple[FrameCfoEvidence, ...]:
    """Run the public parity-split Qin frame-CFO kernel on every opportunity."""

    values = np.asarray(samples, dtype=np.complex64)
    occupancy = np.asarray(occupied, dtype=bool)
    if values.ndim != 1 or occupancy.shape != (protocol.frame_count,):
        raise ValueError("injected samples or occupancy mask have the wrong geometry")
    background = protocol.background(scenario.background_session_id)
    sample_rate_hz = background.sample_rate_hz
    starts = qin_frame_starts(frame_count=protocol.frame_count, sample_rate_hz=sample_rate_hz)
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    grid = np.arange(
        -protocol.frame_cfo_search_half_width_hz,
        protocol.frame_cfo_search_half_width_hz + 0.5 * protocol.profile_step_hz,
        protocol.profile_step_hz,
    )
    config = PilotFrameCfoConfig(
        residual_half_width_hz=protocol.frame_cfo_search_half_width_hz,
        minimum_exact_coherence=protocol.minimum_exact_coherence,
        minimum_coherence_margin=protocol.minimum_coherence_margin,
    )
    output: list[FrameCfoEvidence] = []
    for frame_index, raw_start in enumerate(starts):
        local_start = int(raw_start)
        reference_time_s = local_start / sample_rate_hz + reference_offset_s
        truth = _truth(scenario, protocol, reference_time_s)
        coarse_seed = _nearest_alias_bin(truth.receiver_raw_cfo_hz)
        absolute_start = absolute_span_start_sample + local_start
        if local_start < 1 or local_start + frame_content + 1 > values.size:
            output.append(
                _incomplete_frame(
                    scenario,
                    frame_index,
                    local_start,
                    absolute_start,
                    reference_time_s,
                    bool(occupancy[frame_index]),
                    coarse_seed,
                    truth,
                )
            )
            continue
        guarded = values[local_start - 1 : local_start + frame_content + 1]
        profile = evaluate_edge_pilot_frame_cfo_likelihood(
            guarded,
            sample_rate_hz,
            frame_start_sample=absolute_start,
            acquisition_absolute_cfo_hz=coarse_seed,
            edge="lower",
            residual_grid_hz=grid,
            config=config,
        )
        split = profile.split_validation
        if profile.status is not NumericalStatus.COMPLETE:
            output.append(
                _incomplete_frame(
                    scenario,
                    frame_index,
                    local_start,
                    absolute_start,
                    reference_time_s,
                    bool(occupancy[frame_index]),
                    coarse_seed,
                    truth,
                )
            )
            continue
        profile_maxima = tuple(
            float(np.max(curve))
            for curve in (
                profile.even_exact_log_likelihood,
                profile.even_control_log_likelihood,
                profile.odd_exact_log_likelihood,
                profile.odd_control_log_likelihood,
            )
        )
        even_cfo = (
            None
            if split.even_absolute_cfo_hz is None
            else float(split.even_absolute_cfo_hz - truth.alias_label_hz)
        )
        odd_cfo = (
            None
            if split.odd_absolute_cfo_hz is None
            else float(split.odd_absolute_cfo_hz - truth.alias_label_hz)
        )
        output.append(
            FrameCfoEvidence(
                scenario_id=scenario.scenario_id,
                frame_index=frame_index,
                local_frame_start_sample=local_start,
                absolute_frame_start_sample=absolute_start,
                reference_time_s=reference_time_s,
                occupied=bool(occupancy[frame_index]),
                status=profile.status.value,
                training_supported=split.training_supported,
                training_rejection_reasons=split.training_rejection_reasons,
                coarse_seed_hz=coarse_seed,
                alias_label_hz=truth.alias_label_hz,
                even_canonical_cfo_hz=even_cfo,
                odd_canonical_cfo_hz=odd_cfo,
                even_frequency_uncertainty_hz=split.even_frequency_uncertainty_hz,
                odd_frequency_uncertainty_hz=split.odd_frequency_uncertainty_hz,
                even_exact_coherence=split.even_exact_coherence,
                even_control_coherence=split.even_control_coherence,
                even_coherence_margin=split.even_coherence_margin,
                even_exact_profile_max=profile_maxima[0],
                even_control_profile_max=profile_maxima[1],
                odd_exact_profile_max=profile_maxima[2],
                odd_control_profile_max=profile_maxima[3],
                even_profile_margin=profile_maxima[0] - profile_maxima[1],
                odd_profile_margin=profile_maxima[2] - profile_maxima[3],
                even_search_boundary=split.even_search_boundary,
                odd_search_boundary=split.odd_search_boundary,
                receiver_truth_cfo_hz=truth.receiver_canonical_cfo_hz,
                physical_truth_cfo_hz=truth.physical_cfo_hz,
            )
        )
    return tuple(output)


def fixed_history_rate_estimates(
    evidence: tuple[FrameCfoEvidence, ...],
    scenario: InjectionScenario,
    protocol: PolynomialInjectionProtocol,
) -> tuple[RateEstimateRow, ...]:
    """Apply the public robust line tracker with one fixed history at a time."""

    points = tuple(
        AdaptiveFrameCfoPoint(
            frame_start_sample=item.absolute_frame_start_sample,
            reference_time_s=item.reference_time_s,
            continuity_segment=0,
            even_cfo_hz=float(item.even_canonical_cfo_hz),
            even_cfo_sigma_hz=protocol.fixed_measurement_sigma_hz,
        )
        for item in evidence
        if item.training_supported and item.even_canonical_cfo_hz is not None
    )
    output: list[RateEstimateRow] = []
    for history in protocol.histories:
        config = _history_config(protocol, history)
        track = track_adaptive_frame_cfo(points, config=config)
        if not track.estimates:
            truth = _truth(scenario, protocol, protocol.reference_time_s)
            output.append(
                RateEstimateRow(
                    scenario_id=scenario.scenario_id,
                    estimator=history.name,
                    history_s=history.history_s,
                    frame_start_sample=-1,
                    reference_time_s=protocol.reference_time_s,
                    status="no_result",
                    selected_history_s=None,
                    estimate_rate_hz_s=None,
                    rate_sigma_hz_s=None,
                    receiver_truth_rate_hz_s=truth.receiver_rate_hz_s,
                    physical_truth_rate_hz_s=truth.physical_rate_hz_s,
                    receiver_error_hz_s=None,
                    physical_error_hz_s=None,
                    receiver_covered_95=None,
                    physical_covered_95=None,
                    receiver_failure=None,
                    physical_failure=None,
                    step_phase="no_result",
                )
            )
            continue
        for estimate in track.estimates:
            truth = _truth(scenario, protocol, estimate.reference_time_s)
            rate = estimate.rate_hz_s
            sigma = estimate.rate_sigma_hz_s
            receiver_error = None if rate is None else float(rate - truth.receiver_rate_hz_s)
            physical_error = None if rate is None else float(rate - truth.physical_rate_hz_s)
            output.append(
                RateEstimateRow(
                    scenario_id=scenario.scenario_id,
                    estimator=history.name,
                    history_s=history.history_s,
                    frame_start_sample=estimate.frame_start_sample,
                    reference_time_s=estimate.reference_time_s,
                    status="complete" if rate is not None and sigma is not None else "warmup",
                    selected_history_s=estimate.selected_history_s,
                    estimate_rate_hz_s=rate,
                    rate_sigma_hz_s=sigma,
                    receiver_truth_rate_hz_s=truth.receiver_rate_hz_s,
                    physical_truth_rate_hz_s=truth.physical_rate_hz_s,
                    receiver_error_hz_s=receiver_error,
                    physical_error_hz_s=physical_error,
                    receiver_covered_95=_covered(receiver_error, sigma),
                    physical_covered_95=_covered(physical_error, sigma),
                    receiver_failure=_failed(
                        receiver_error, protocol.rate_failure_absolute_error_hz_s
                    ),
                    physical_failure=_failed(
                        physical_error, protocol.rate_failure_absolute_error_hz_s
                    ),
                    step_phase=_step_phase(
                        scenario,
                        estimate.reference_time_s,
                        protocol.step_transition_exclusion_s,
                        protocol.cfo_step_time_s,
                    ),
                )
            )
    return tuple(output)


def fit_full_span_cubic(
    evidence: tuple[FrameCfoEvidence, ...],
    scenario: InjectionScenario,
    protocol: PolynomialInjectionProtocol,
) -> CubicEstimate:
    """Fit CFO, rate, acceleration, and jerk with the preregistered WLS diagnostic."""

    selected = tuple(
        item
        for item in evidence
        if item.training_supported and item.even_canonical_cfo_hz is not None
    )
    truth = _truth(scenario, protocol, protocol.reference_time_s)
    if len(selected) < protocol.diagnostic_minimum_frames:
        return _empty_cubic(scenario, truth, len(selected), protocol.reference_time_s)
    times = np.asarray([item.reference_time_s for item in selected], dtype=float)
    relative = times - protocol.reference_time_s
    values = np.asarray([item.even_canonical_cfo_hz for item in selected], dtype=float)
    design = np.column_stack(
        (
            np.ones(len(selected), dtype=float),
            relative,
            0.5 * relative**2,
            relative**3 / 6.0,
        )
    )
    precision = 1.0 / protocol.fixed_measurement_sigma_hz**2
    normal = precision * (design.T @ design)
    if float(np.linalg.cond(normal)) > protocol.maximum_normal_condition:
        return _empty_cubic(scenario, truth, len(selected), protocol.reference_time_s)
    coefficients = np.linalg.solve(normal, precision * design.T @ values)
    residual = values - design @ coefficients
    dof = max(len(values) - design.shape[1], 1)
    reduced_chi_square = float(np.sum((residual / protocol.fixed_measurement_sigma_hz) ** 2) / dof)
    covariance = np.linalg.inv(normal) * max(1.0, reduced_chi_square)
    sigma = np.sqrt(np.diag(covariance))
    return CubicEstimate(
        scenario_id=scenario.scenario_id,
        status="complete",
        frame_count=len(selected),
        reference_time_s=protocol.reference_time_s,
        cfo_hz=float(coefficients[0]),
        rate_hz_s=float(coefficients[1]),
        acceleration_hz_s2=float(coefficients[2]),
        jerk_hz_s3=float(coefficients[3]),
        cfo_sigma_hz=float(sigma[0]),
        rate_sigma_hz_s=float(sigma[1]),
        acceleration_sigma_hz_s2=float(sigma[2]),
        jerk_sigma_hz_s3=float(sigma[3]),
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        receiver_rate_truth_hz_s=truth.receiver_rate_hz_s,
        receiver_acceleration_truth_hz_s2=truth.receiver_acceleration_hz_s2,
        receiver_jerk_truth_hz_s3=truth.receiver_jerk_hz_s3,
        physical_rate_truth_hz_s=truth.physical_rate_hz_s,
        physical_acceleration_truth_hz_s2=truth.physical_acceleration_hz_s2,
        physical_jerk_truth_hz_s3=truth.physical_jerk_hz_s3,
    )


def _phase_cycles(
    scenario: InjectionScenario,
    receiver_time_s: np.ndarray,
    *,
    carrier_origin_hz: float,
    reference_time_s: float,
    alias_change_time_s: float,
    cfo_step_time_s: float,
) -> np.ndarray:
    clock_scale = 1.0 + scenario.sample_clock_offset_ppm * 1e-6
    physical_time = (receiver_time_s - reference_time_s) / clock_scale
    phase = (
        carrier_origin_hz * physical_time
        + 0.5 * scenario.rate_hz_s * physical_time**2
        + scenario.acceleration_hz_s2 * physical_time**3 / 6.0
        + scenario.jerk_hz_s3 * physical_time**4 / 24.0
    )
    step_time_physical = (cfo_step_time_s - reference_time_s) / clock_scale
    phase += scenario.cfo_step_hz * np.maximum(physical_time - step_time_physical, 0.0)
    phase += scenario.alias_change_hz * np.maximum(receiver_time_s - alias_change_time_s, 0.0)
    return phase


def _truth(
    scenario: InjectionScenario,
    protocol: PolynomialInjectionProtocol,
    receiver_time_s: float,
) -> PolynomialTruth:
    return truth_at_receiver_time(
        scenario,
        receiver_time_s,
        carrier_origin_hz=protocol.carrier_origin_hz,
        reference_time_s=protocol.reference_time_s,
        alias_change_time_s=protocol.alias_change_time_s,
        cfo_step_time_s=protocol.cfo_step_time_s,
    )


def _nearest_alias_bin(cfo_hz: float) -> float:
    return float(np.rint(cfo_hz / 750.0) * 750.0)


def _incomplete_frame(
    scenario: InjectionScenario,
    frame_index: int,
    local_start: int,
    absolute_start: int,
    reference_time_s: float,
    occupied: bool,
    coarse_seed: float,
    truth: PolynomialTruth,
) -> FrameCfoEvidence:
    return FrameCfoEvidence(
        scenario_id=scenario.scenario_id,
        frame_index=frame_index,
        local_frame_start_sample=local_start,
        absolute_frame_start_sample=absolute_start,
        reference_time_s=reference_time_s,
        occupied=occupied,
        status="incomplete_guard",
        training_supported=False,
        training_rejection_reasons=("guarded_frame_outside_frozen_span",),
        coarse_seed_hz=coarse_seed,
        alias_label_hz=truth.alias_label_hz,
        even_canonical_cfo_hz=None,
        odd_canonical_cfo_hz=None,
        even_frequency_uncertainty_hz=None,
        odd_frequency_uncertainty_hz=None,
        even_exact_coherence=None,
        even_control_coherence=None,
        even_coherence_margin=None,
        even_exact_profile_max=None,
        even_control_profile_max=None,
        odd_exact_profile_max=None,
        odd_control_profile_max=None,
        even_profile_margin=None,
        odd_profile_margin=None,
        even_search_boundary=False,
        odd_search_boundary=False,
        receiver_truth_cfo_hz=truth.receiver_canonical_cfo_hz,
        physical_truth_cfo_hz=truth.physical_cfo_hz,
    )


def _history_config(
    protocol: PolynomialInjectionProtocol, history: HistoryEstimator
) -> AdaptiveFrameCfoConfig:
    return AdaptiveFrameCfoConfig(
        history_durations_s=(history.history_s,),
        minimum_history_coverage=protocol.minimum_history_coverage,
        minimum_frames=history.minimum_frames,
        minimum_effective_frames=history.minimum_effective_frames,
        maximum_gap_s=protocol.maximum_gap_s,
        huber_tuning=protocol.huber_tuning,
        maximum_iterations=protocol.maximum_iterations,
        prediction_convergence_hz=protocol.prediction_convergence_hz,
        consistency_chi_square=protocol.consistency_chi_square,
        standardized_scale_floor=protocol.standardized_scale_floor,
        maximum_normal_condition=protocol.maximum_normal_condition,
    )


def _covered(error: float | None, sigma: float | None) -> bool | None:
    if error is None or sigma is None:
        return None
    return abs(error) <= 1.96 * sigma


def _failed(error: float | None, threshold: float) -> bool | None:
    if error is None:
        return None
    return abs(error) > threshold


def _step_phase(
    scenario: InjectionScenario,
    reference_time_s: float,
    transition_exclusion_s: float,
    step_time_s: float,
) -> str:
    if scenario.cfo_step_hz == 0.0:
        return "no_step"
    if reference_time_s < step_time_s:
        return "pre_step"
    if reference_time_s < step_time_s + transition_exclusion_s:
        return "transition"
    return "post_history"


def _empty_cubic(
    scenario: InjectionScenario,
    truth: PolynomialTruth,
    frame_count: int,
    reference_time_s: float,
) -> CubicEstimate:
    return CubicEstimate(
        scenario_id=scenario.scenario_id,
        status="insufficient",
        frame_count=frame_count,
        reference_time_s=reference_time_s,
        cfo_hz=None,
        rate_hz_s=None,
        acceleration_hz_s2=None,
        jerk_hz_s3=None,
        cfo_sigma_hz=None,
        rate_sigma_hz_s=None,
        acceleration_sigma_hz_s2=None,
        jerk_sigma_hz_s3=None,
        residual_rms_hz=None,
        receiver_rate_truth_hz_s=truth.receiver_rate_hz_s,
        receiver_acceleration_truth_hz_s2=truth.receiver_acceleration_hz_s2,
        receiver_jerk_truth_hz_s3=truth.receiver_jerk_hz_s3,
        physical_rate_truth_hz_s=truth.physical_rate_hz_s,
        physical_acceleration_truth_hz_s2=truth.physical_acceleration_hz_s2,
        physical_jerk_truth_hz_s3=truth.physical_jerk_hz_s3,
    )
