"""Bounded adaptive dual-RX double-difference extraction service primitives."""

from __future__ import annotations

import itertools
import math

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import (
    circular_frequency_delta,
    select_consistent_receiver_pairs,
)
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
    DualReceiverPhaseObservation,
    ReceiverPhaseSeed,
    extract_dual_receiver_phase,
)
from leo.scanner.adaptive_dual_rx_phase_product_v2 import (
    AdaptiveDualRxDoubleDifferenceHypothesisV2,
    AdaptiveDualRxPhaseVisitV2,
)
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopFractionalCandidateV1,
    AdaptiveHopVisitAnalysisV1,
)

_TIMING_GATE_SAMPLES = 9.0
_PILOT_CONTROL_RATIO_GATE = 2.0
_PHASE_RESULTANT_GATE = 0.5
_MINIMUM_DISTINCT_SIGNAL_SEPARATION_HZ = 5_000.0


def _timing_residual_samples(
    left: AdaptiveHopFractionalCandidateV1,
    right: AdaptiveHopFractionalCandidateV1,
    frame_period_samples: float,
) -> float:
    left_epoch = left.integer_epoch_sample + left.fractional_epoch_offset_samples
    right_epoch = right.integer_epoch_sample + right.fractional_epoch_offset_samples
    difference = right_epoch - left_epoch
    return float(abs(difference - round(difference / frame_period_samples) * frame_period_samples))


def _phase_blind_pairs(
    visit: AdaptiveHopVisitAnalysisV1,
) -> list[tuple[AdaptiveHopFractionalCandidateV1, AdaptiveHopFractionalCandidateV1, float, int]]:
    probes = {(probe.probe_index, probe.receiver_id): probe for probe in visit.probes}
    frame_period = visit.configuration.sample_rate_hz / 750.0
    output = []
    probe_indexes = sorted(
        {key[0] for key in probes if (key[0], 0) in probes and (key[0], 1) in probes}
    )
    for probe_index in probe_indexes:
        left = tuple(
            item for item in probes[probe_index, 0].candidates if item.passed_fractional_margin_gate
        )
        right = tuple(
            item for item in probes[probe_index, 1].candidates if item.passed_fractional_margin_gate
        )
        edges = []
        for left_index, left_candidate in enumerate(left):
            for right_index, right_candidate in enumerate(right):
                if (
                    _timing_residual_samples(left_candidate, right_candidate, frame_period)
                    > _TIMING_GATE_SAMPLES
                ):
                    continue
                receiver_offset_hz = (
                    right_candidate.fractional_tracking_cfo_hz
                    - left_candidate.fractional_tracking_cfo_hz
                )
                quality = min(left_candidate.fractional_margin, right_candidate.fractional_margin)
                edges.append((left_index, right_index, receiver_offset_hz, quality))
        selected = select_consistent_receiver_pairs(edges)
        probe_start_samples = (
            probe_index
            * visit.configuration.probe_stride_ms
            * (visit.configuration.sample_rate_hz // 1000)
        )
        output.extend(
            (left[i], right[j], offset, probe_start_samples) for i, j, offset, _ in selected
        )
    distinct = []
    for pair in sorted(
        output,
        key=lambda item: (
            -min(item[0].fractional_margin, item[1].fractional_margin),
            item[3],
            item[0].fractional_tracking_cfo_hz,
        ),
    ):
        if any(
            abs(
                circular_frequency_delta(
                    pair[0].fractional_tracking_cfo_hz,
                    retained[0].fractional_tracking_cfo_hz,
                )
            )
            < _MINIMUM_DISTINCT_SIGNAL_SEPARATION_HZ
            or abs(
                circular_frequency_delta(
                    pair[1].fractional_tracking_cfo_hz,
                    retained[1].fractional_tracking_cfo_hz,
                )
            )
            < _MINIMUM_DISTINCT_SIGNAL_SEPARATION_HZ
            for retained in distinct
        ):
            continue
        distinct.append(pair)
        if len(distinct) == 8:
            break
    return distinct


def _extract_pair(
    iq: np.ndarray,
    visit: AdaptiveHopVisitAnalysisV1,
    pair: tuple[
        AdaptiveHopFractionalCandidateV1,
        AdaptiveHopFractionalCandidateV1,
        float,
        int,
    ],
) -> DualReceiverPhaseObservation | None:
    left, right, _, probe_start_samples = pair
    references = tuple(
        probe_start_samples
        + candidate.integer_epoch_sample
        + candidate.fractional_epoch_offset_samples
        for candidate in (left, right)
    )
    observation = extract_dual_receiver_phase(
        iq,
        visit.configuration.sample_rate_hz,
        visit.target.edge,
        probe_start_samples + left.integer_epoch_sample,
        (
            ReceiverPhaseSeed(left.acquired_cfo_hz, references[0]),
            ReceiverPhaseSeed(right.acquired_cfo_hz, references[1]),
        ),
    )
    if (
        observation.resultant_length < _PHASE_RESULTANT_GATE
        or min(receiver.exact_to_control_power_ratio for receiver in observation.receivers)
        < _PILOT_CONTROL_RATIO_GATE
    ):
        return None
    return observation


def extract_phase_visit_v2(
    iq: np.ndarray,
    visit: AdaptiveHopVisitAnalysisV1,
    *,
    glrt_binding_sha256: str,
) -> AdaptiveDualRxPhaseVisitV2:
    """Retain every two-signal hypothesis after phase-blind RX pairing."""
    pairs = _phase_blind_pairs(visit)
    extracted = [(pair, _extract_pair(iq, visit, pair)) for pair in pairs]
    qualified = [(pair, result) for pair, result in extracted if result is not None]
    hypotheses = []
    sample_rate_hz = visit.configuration.sample_rate_hz
    visit_origin_s = (visit.valid_start_counter - visit.source_origin_counter) / sample_rate_hz
    for (low_pair, low), (high_pair, high) in itertools.combinations(qualified, 2):
        assert low is not None and high is not None
        separation_hz = abs(
            circular_frequency_delta(
                low_pair[0].fractional_tracking_cfo_hz,
                high_pair[0].fractional_tracking_cfo_hz,
            )
        )
        if separation_hz < _MINIMUM_DISTINCT_SIGNAL_SEPARATION_HZ:
            continue
        if low_pair[0].fractional_tracking_cfo_hz > high_pair[0].fractional_tracking_cfo_hz:
            (low_pair, low), (high_pair, high) = (high_pair, high), (low_pair, low)
        common_sample = 0.5 * (low.center_sample + high.center_sample)
        low_phase = (
            low.wrapped_phase_rad
            + 2
            * math.pi
            * low.relative_frequency_hz
            * (common_sample - low.center_sample)
            / sample_rate_hz
        )
        high_phase = (
            high.wrapped_phase_rad
            + 2
            * math.pi
            * high.relative_frequency_hz
            * (common_sample - high.center_sample)
            / sample_rate_hz
        )
        low_time_s = visit_origin_s + low.center_sample / sample_rate_hz
        high_time_s = visit_origin_s + high.center_sample / sample_rate_hz
        low_delta_s = (common_sample - low.center_sample) / sample_rate_hz
        high_delta_s = (common_sample - high.center_sample) / sample_rate_hz
        async_sigma_rad = (
            2
            * math.pi
            * math.hypot(
                low_delta_s * low.relative_frequency_standard_error_hz,
                high_delta_s * high.relative_frequency_standard_error_hz,
            )
        )
        common_frames = len(
            set(low.receivers[0].frame_starts).intersection(high.receivers[0].frame_starts)
        )
        hypotheses.append(
            AdaptiveDualRxDoubleDifferenceHypothesisV2(
                hypothesis_index=len(hypotheses),
                low_rx0_tracking_cfo_hz=low_pair[0].fractional_tracking_cfo_hz,
                high_rx0_tracking_cfo_hz=high_pair[0].fractional_tracking_cfo_hz,
                alias_aware_signal_separation_hz=separation_hz,
                receiver_offset_hz=0.5 * (low_pair[2] + high_pair[2]),
                wrapped_high_minus_low_rad=float(np.angle(np.exp(1j * (high_phase - low_phase)))),
                standard_error_rad=math.hypot(
                    math.radians(
                        math.hypot(low.phase_standard_error_deg, high.phase_standard_error_deg)
                    ),
                    async_sigma_rad,
                ),
                common_session_time_s=visit_origin_s + common_sample / sample_rate_hz,
                low_center_session_time_s=low_time_s,
                high_center_session_time_s=high_time_s,
                asynchronous_center_separation_s=abs(high_time_s - low_time_s),
                asynchronous_correction_standard_error_rad=async_sigma_rad,
                direct_common_frame_count=common_frames,
                phase_resultant_floor=min(low.resultant_length, high.resultant_length),
                exact_to_control_power_ratio_floor=min(
                    receiver.exact_to_control_power_ratio
                    for observation in (low, high)
                    for receiver in observation.receivers
                ),
            )
        )
    state = "qualified" if hypotheses else "insufficient_signal"
    if hypotheses:
        reason = "phase_blind_two_signal_hypotheses"
    elif len(pairs) < 2:
        reason = "fewer_than_two_phase_blind_receiver_pairs"
    elif len(qualified) < 2:
        reason = "fewer_than_two_phase_quality_pairs"
    else:
        reason = "no_alias_distinct_two_signal_hypothesis"
    return AdaptiveDualRxPhaseVisitV2(
        session_id=visit.session_id,
        input_manifest_sha256=visit.input_manifest_sha256,
        glrt_binding_sha256=glrt_binding_sha256,
        visit_index=visit.visit_index,
        target_index=visit.target_index,
        edge=visit.target.edge,
        state=state,
        reason=reason,
        consistent_receiver_pair_count=len(pairs),
        phase_quality_pair_count=len(qualified),
        hypotheses=tuple(hypotheses),
    )
