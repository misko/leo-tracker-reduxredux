"""Pure, fixed-grid research prototype for contiguous Qin frame recovery.

The analyzer in this module owns no recording I/O and publishes no persisted
product.  A caller supplies one contiguous IQ array and one or more explicit
GLRT anchors.  Each anchor owns an absolute half-open sample interval and its
750 Hz frame lattice is projected both forward and backward throughout that
interval.  This is deliberately different from starting a short replay at the
GLRT seed and thereby leaving artificial holes between replays.

The full-frame estimator is retained as a diagnostic.  Selection and tracking
use the even-Qin training fold from the split estimator; odd Qin is held out and
can therefore score one-step predictions without changing membership, filter
state, reacquisition, or locklet boundaries.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import numpy.typing as npt

from leo.analysis.qam import (
    PilotFrameCfoConfig,
    PilotFrameCfoEstimate,
    PilotFrameCfoSplitValidation,
    estimate_edge_pilot_frame_cfo,
    estimate_edge_pilot_frame_cfo_split_validation,
)
from leo.analysis.starlink import FRAME_RATE_HZ, OFDM_SYMBOL_DURATION_S, NumericalStatus
from leo.analysis.starlink.templates import StarlinkEdge


class FrameOpportunityOutcome(StrEnum):
    """Estimator disposition of one nominal 750 Hz frame opportunity.

    These values are an analysis ledger, not an independent occupancy test.
    In particular, ``ESTIMATOR_NO_RESULT`` only says that the Qin estimator
    returned no measurement from the supplied slice.
    """

    SUPPORTED = "supported"
    REJECTED = "rejected"
    ESTIMATOR_NO_RESULT = "estimator_no_result"
    CROSSES_REFILL_BOUNDARY = "crosses_refill_boundary"
    CROSSES_INCOMPATIBLE_ANCHOR = "crosses_incompatible_anchor"
    INCOMPLETE_CAPTURE = "incomplete_capture"


class RecoveryFilterMode(StrEnum):
    """Causal lifecycle after processing one opportunity."""

    ACQUIRE = "acquire"
    TRACK = "track"
    COAST = "coast"
    LOST = "lost"
    REACQUIRE = "reacquire"


class LockletEndReason(StrEnum):
    """Reason that frequency/rate continuity was deliberately terminated."""

    END_OF_INPUT = "end_of_input"
    COAST_EXPIRED = "coast_expired"
    REFILL_BOUNDARY = "refill_boundary"
    UNANCHORED_GAP = "unanchored_gap"
    ANCHOR_SOURCE_CHANGED = "anchor_source_changed"
    ANCHOR_EDGE_CHANGED = "anchor_edge_changed"
    ANCHOR_ALIAS_CHANGED = "anchor_alias_changed"
    ANCHOR_EPOCH_INCOMPATIBLE = "anchor_epoch_incompatible"
    ANCHOR_CFO_INCOMPATIBLE = "anchor_cfo_incompatible"


@dataclass(frozen=True, slots=True)
class FrameRecoveryAnchor:
    """One GLRT-owned absolute frame lattice over a caller-selected interval.

    ``epoch_sample`` is any known frame start on the lattice.  It need not lie
    inside the ownership interval: negative lattice indices intentionally let
    a seed found late in a probe recover opportunities earlier in that probe.
    ``sample_source_id`` identifies the IQ coordinate system.  The optional
    ``continuity_source_id`` identifies a qualified physical candidate;
    unknown source or alias identity is intentionally incompatible with a
    replacement anchor.  Observation IDs are provenance and may change
    between otherwise compatible anchors.
    """

    anchor_id: str
    sample_source_id: str
    canonical_observation_id: str | None
    source_observation_id: str | None
    edge: StarlinkEdge | str
    cfo_alias_index: int | None
    epoch_sample: int
    acquisition_absolute_cfo_hz: float
    ownership_start_sample: int
    ownership_stop_sample: int
    continuity_source_id: str | None = None

    def __post_init__(self) -> None:
        if not self.anchor_id or not self.sample_source_id:
            raise ValueError("anchor and sample-source IDs must be nonempty")
        optional_ids = (
            self.canonical_observation_id,
            self.source_observation_id,
            self.continuity_source_id,
        )
        if any(value is not None and not value for value in optional_ids):
            raise ValueError("present recovery anchor identifiers must be nonempty")
        if self.cfo_alias_index is not None and not isinstance(self.cfo_alias_index, int):
            raise ValueError("CFO alias index must be an integer or unknown")
        sample_values = (
            self.epoch_sample,
            self.ownership_start_sample,
            self.ownership_stop_sample,
        )
        if any(not isinstance(value, int) for value in sample_values):
            raise ValueError("anchor sample coordinates must be integers")
        if self.ownership_start_sample >= self.ownership_stop_sample:
            raise ValueError("anchor ownership interval must be nonempty")
        if not math.isfinite(self.acquisition_absolute_cfo_hz):
            raise ValueError("anchor CFO must be finite")
        object.__setattr__(self, "edge", StarlinkEdge(self.edge))


@dataclass(frozen=True, slots=True)
class FrameRecoveryConfig:
    """Frozen gates for the additive continuous-recovery experiment."""

    pilot: PilotFrameCfoConfig = field(default_factory=PilotFrameCfoConfig)
    maximum_coast_frames: int = 2
    frequency_innovation_gate_sigma: float = 6.0
    frequency_noise_floor_hz: float = 25.0
    initial_rate_sigma_hz_s: float = 5_000.0
    rate_process_sigma_hz_s_sqrt_s: float = 750.0
    maximum_anchor_epoch_error_samples: int = 1
    maximum_anchor_cfo_difference_hz: float = 10_000.0

    def __post_init__(self) -> None:
        if self.maximum_coast_frames < 0:
            raise ValueError("maximum coast frames must be nonnegative")
        if self.maximum_anchor_epoch_error_samples < 0:
            raise ValueError("anchor epoch tolerance must be nonnegative")
        positive = (
            self.frequency_innovation_gate_sigma,
            self.frequency_noise_floor_hz,
            self.initial_rate_sigma_hz_s,
            self.rate_process_sigma_hz_s_sqrt_s,
            self.maximum_anchor_cfo_difference_hz,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("recovery gates and noise scales must be finite and positive")


@dataclass(frozen=True, slots=True)
class UnanchoredSampleSpan:
    """Input samples which no acquisition anchor was authorized to own."""

    start_sample: int
    stop_sample: int

    @property
    def sample_count(self) -> int:
        return self.stop_sample - self.start_sample


@dataclass(frozen=True, slots=True)
class RecoveredFrame:
    """Complete causal accounting for one nominal frame opportunity."""

    opportunity_index: int
    anchor_id: str
    lattice_index: int
    frame_start_sample: int
    reference_sample: float
    outcome: FrameOpportunityOutcome
    mode: RecoveryFilterMode
    locklet_index: int | None
    reacquired: bool
    hard_split_before: bool
    split_reason: LockletEndReason | None
    estimator_seed_cfo_hz: float | None
    predicted_cfo_hz: float | None
    tracked_cfo_hz: float | None
    tracked_rate_hz_s: float | None
    filter_accepted: bool
    predicted_only: bool
    frequency_innovation_hz: float | None
    normalized_frequency_innovation: float | None
    odd_prediction_error_hz: float | None
    rejection_reasons: tuple[str, ...]
    primary: PilotFrameCfoEstimate | None
    split_validation: PilotFrameCfoSplitValidation | None


@dataclass(frozen=True, slots=True)
class RecoveryLocklet:
    """One independently initialized frequency/rate continuity episode."""

    locklet_index: int
    first_frame_start_sample: int
    last_frame_start_sample: int
    supported_frame_count: int
    predicted_only_frame_count: int
    reacquired: bool
    ended_by: LockletEndReason


@dataclass(frozen=True, slots=True)
class ContinuousFrameRecoveryResult:
    """All opportunities, locklets, and uncovered input from one analysis."""

    sample_start: int
    sample_stop: int
    sample_rate_hz: int
    frames: tuple[RecoveredFrame, ...]
    locklets: tuple[RecoveryLocklet, ...]
    unanchored_spans: tuple[UnanchoredSampleSpan, ...]

    @property
    def accounted_sample_count(self) -> int:
        return (
            self.sample_stop
            - self.sample_start
            - sum(span.sample_count for span in self.unanchored_spans)
        )


@dataclass(frozen=True, slots=True)
class _Opportunity:
    anchor: FrameRecoveryAnchor
    lattice_index: int
    frame_start_sample: int


@dataclass(slots=True)
class _ActiveLocklet:
    index: int
    first_frame_start_sample: int
    last_frame_start_sample: int
    supported_frame_count: int
    predicted_only_frame_count: int
    reacquired: bool
    state: np.ndarray
    covariance: np.ndarray
    state_time_s: float
    coast_frames: int = 0


def anchors_compatible(
    left: FrameRecoveryAnchor,
    right: FrameRecoveryAnchor,
    *,
    sample_rate_hz: int,
    config: FrameRecoveryConfig | None = None,
) -> bool:
    """Return whether two adjacent anchors may share a frequency locklet."""

    settings = config or FrameRecoveryConfig()
    return _anchor_incompatibility(left, right, sample_rate_hz, settings) is None


def recover_contiguous_frames(
    samples: npt.ArrayLike,
    *,
    sample_start: int,
    sample_rate_hz: int,
    anchors: tuple[FrameRecoveryAnchor, ...],
    refill_boundaries: tuple[int, ...] = (),
    config: FrameRecoveryConfig | None = None,
) -> ContinuousFrameRecoveryResult:
    """Estimate every anchor-owned opportunity on an exact 750 Hz lattice.

    The returned rows are intentionally not a persisted contract.  A missed or
    rejected measurement may be represented by a prediction for at most
    ``maximum_coast_frames``.  Refills, unanchored gaps, incompatible anchors,
    and an expired coast always terminate the active locklet.
    """

    values = np.asarray(samples, dtype=np.complex128)
    settings = config or FrameRecoveryConfig()
    if values.ndim != 1:
        raise ValueError("continuous recovery samples must be one dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("continuous recovery samples must be finite")
    if not isinstance(sample_start, int) or sample_start < 0:
        raise ValueError("sample_start must be a nonnegative integer")
    if not isinstance(sample_rate_hz, int) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be a positive integer")
    minimum_rate_hz = 8 * 234_375
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz} Hz")
    sample_stop = sample_start + values.size
    ordered_anchors = _validate_anchors(anchors, sample_start, sample_stop)
    boundaries = tuple(sorted(set(refill_boundaries)))
    if boundaries != refill_boundaries:
        raise ValueError("refill boundaries must be unique and sorted")
    if any(boundary <= sample_start or boundary >= sample_stop for boundary in boundaries):
        raise ValueError("refill boundaries must lie strictly inside the input")

    uncovered = _unanchored_spans(ordered_anchors, sample_start, sample_stop)
    opportunities = _frame_opportunities(
        ordered_anchors,
        sample_start=sample_start,
        sample_stop=sample_stop,
        sample_rate_hz=sample_rate_hz,
    )
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    reference_offset = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S) * sample_rate_hz
    )
    anchor_hard_boundaries = _anchor_hard_boundaries(
        ordered_anchors,
        sample_rate_hz,
        settings,
    )

    frames: list[RecoveredFrame] = []
    locklets: list[RecoveryLocklet] = []
    active: _ActiveLocklet | None = None
    previous_opportunity: _Opportunity | None = None
    handled_refills: set[int] = set()

    def finish_active(reason: LockletEndReason) -> None:
        nonlocal active
        if active is None:
            return
        locklets.append(
            RecoveryLocklet(
                locklet_index=active.index,
                first_frame_start_sample=active.first_frame_start_sample,
                last_frame_start_sample=active.last_frame_start_sample,
                supported_frame_count=active.supported_frame_count,
                predicted_only_frame_count=active.predicted_only_frame_count,
                reacquired=active.reacquired,
                ended_by=reason,
            )
        )
        active = None

    for opportunity_index, opportunity in enumerate(opportunities):
        anchor = opportunity.anchor
        start = opportunity.frame_start_sample
        reference_sample = start + reference_offset
        reference_time_s = reference_sample / sample_rate_hz
        hard_split_before = False
        split_reason: LockletEndReason | None = None

        if previous_opportunity is not None and previous_opportunity.anchor != anchor:
            prior = previous_opportunity.anchor
            if prior.ownership_stop_sample != anchor.ownership_start_sample:
                split_reason = LockletEndReason.UNANCHORED_GAP
            else:
                split_reason = _anchor_incompatibility(prior, anchor, sample_rate_hz, settings)
            if split_reason is not None:
                hard_split_before = True
                finish_active(split_reason)

        intervening_refill = _first_boundary(
            tuple(boundary for boundary in boundaries if boundary not in handled_refills),
            previous_opportunity.frame_start_sample if previous_opportunity else sample_start - 1,
            start,
        )
        if intervening_refill is not None:
            handled_refills.add(intervening_refill)
            hard_split_before = True
            split_reason = LockletEndReason.REFILL_BOUNDARY
            finish_active(split_reason)

        slice_start = start - 1
        slice_stop = start + frame_content + 1
        refill_crossing = _crossed_boundary(boundaries, slice_start, slice_stop)
        anchor_crossing = _crossed_boundary(anchor_hard_boundaries, slice_start, slice_stop)
        if refill_crossing is not None or anchor_crossing is not None:
            if refill_crossing is not None:
                handled_refills.add(refill_crossing)
            reason = (
                LockletEndReason.REFILL_BOUNDARY
                if refill_crossing is not None
                else anchor_hard_boundaries[anchor_crossing]  # type: ignore[index]
            )
            hard_split_before = True
            split_reason = reason
            finish_active(reason)
            frames.append(
                _empty_frame(
                    opportunity_index,
                    opportunity,
                    reference_sample,
                    outcome=(
                        FrameOpportunityOutcome.CROSSES_REFILL_BOUNDARY
                        if refill_crossing is not None
                        else FrameOpportunityOutcome.CROSSES_INCOMPATIBLE_ANCHOR
                    ),
                    mode=_idle_mode(locklets),
                    hard_split_before=hard_split_before,
                    split_reason=split_reason,
                    rejection_reasons=(reason.value,),
                )
            )
            previous_opportunity = opportunity
            continue

        local_start = slice_start - sample_start
        local_stop = slice_stop - sample_start
        if start < 1 or local_start < 0 or local_stop > values.size:
            frame, active = _missed_frame(
                opportunity_index,
                opportunity,
                reference_sample,
                FrameOpportunityOutcome.INCOMPLETE_CAPTURE,
                ("guarded_frame_outside_capture",),
                active,
                locklets,
                settings,
                sample_rate_hz,
                hard_split_before,
                split_reason,
                finish_active,
            )
            frames.append(frame)
            previous_opportunity = opportunity
            continue

        predicted_state, predicted_covariance = _prediction(active, reference_time_s, settings)
        seed_cfo_hz = (
            float(predicted_state[0])
            if predicted_state is not None
            else anchor.acquisition_absolute_cfo_hz
        )
        guarded = values[local_start:local_stop]
        primary = estimate_edge_pilot_frame_cfo(
            guarded,
            sample_rate_hz,
            frame_start_sample=start,
            acquisition_absolute_cfo_hz=seed_cfo_hz,
            edge=anchor.edge,
            config=settings.pilot,
        )
        split = estimate_edge_pilot_frame_cfo_split_validation(
            guarded,
            sample_rate_hz,
            frame_start_sample=start,
            acquisition_absolute_cfo_hz=seed_cfo_hz,
            edge=anchor.edge,
            config=settings.pilot,
        )
        outcome = _measurement_outcome(split)
        reasons = split.training_rejection_reasons
        measurement_hz = split.even_absolute_cfo_hz
        measurement_sigma_hz = split.even_frequency_uncertainty_hz
        odd_error = (
            float(split.odd_absolute_cfo_hz - predicted_state[0])
            if split.odd_absolute_cfo_hz is not None and predicted_state is not None
            else None
        )

        if outcome is not FrameOpportunityOutcome.SUPPORTED:
            frame, active = _missed_frame(
                opportunity_index,
                opportunity,
                reference_sample,
                outcome,
                reasons,
                active,
                locklets,
                settings,
                sample_rate_hz,
                hard_split_before,
                split_reason,
                finish_active,
                estimator_seed_cfo_hz=seed_cfo_hz,
                primary=primary,
                split_validation=split,
                predicted_state=predicted_state,
                predicted_covariance=predicted_covariance,
                odd_prediction_error_hz=odd_error,
            )
            frames.append(frame)
            previous_opportunity = opportunity
            continue

        assert measurement_hz is not None and measurement_sigma_hz is not None
        if active is None:
            reacquired = bool(locklets)
            variance = measurement_sigma_hz**2 + settings.frequency_noise_floor_hz**2
            active = _ActiveLocklet(
                index=len(locklets),
                first_frame_start_sample=start,
                last_frame_start_sample=start,
                supported_frame_count=1,
                predicted_only_frame_count=0,
                reacquired=reacquired,
                state=np.asarray((measurement_hz, 0.0), dtype=float),
                covariance=np.diag((variance, settings.initial_rate_sigma_hz_s**2)),
                state_time_s=reference_time_s,
            )
            frames.append(
                RecoveredFrame(
                    opportunity_index=opportunity_index,
                    anchor_id=anchor.anchor_id,
                    lattice_index=opportunity.lattice_index,
                    frame_start_sample=start,
                    reference_sample=reference_sample,
                    outcome=outcome,
                    mode=RecoveryFilterMode.TRACK,
                    locklet_index=active.index,
                    reacquired=reacquired,
                    hard_split_before=hard_split_before,
                    split_reason=split_reason,
                    estimator_seed_cfo_hz=seed_cfo_hz,
                    predicted_cfo_hz=None,
                    tracked_cfo_hz=measurement_hz,
                    tracked_rate_hz_s=0.0,
                    filter_accepted=True,
                    predicted_only=False,
                    frequency_innovation_hz=None,
                    normalized_frequency_innovation=None,
                    odd_prediction_error_hz=None,
                    rejection_reasons=(),
                    primary=primary,
                    split_validation=split,
                )
            )
            previous_opportunity = opportunity
            continue

        assert predicted_state is not None and predicted_covariance is not None
        measurement_variance = measurement_sigma_hz**2 + settings.frequency_noise_floor_hz**2
        innovation = float(measurement_hz - predicted_state[0])
        innovation_variance = float(predicted_covariance[0, 0] + measurement_variance)
        normalized = innovation / math.sqrt(max(innovation_variance, 1e-20))
        if abs(normalized) > settings.frequency_innovation_gate_sigma:
            frame, active = _missed_frame(
                opportunity_index,
                opportunity,
                reference_sample,
                outcome,
                ("frequency_innovation_gate",),
                active,
                locklets,
                settings,
                sample_rate_hz,
                hard_split_before,
                split_reason,
                finish_active,
                estimator_seed_cfo_hz=seed_cfo_hz,
                primary=primary,
                split_validation=split,
                predicted_state=predicted_state,
                predicted_covariance=predicted_covariance,
                frequency_innovation_hz=innovation,
                normalized_frequency_innovation=normalized,
                odd_prediction_error_hz=odd_error,
            )
            frames.append(frame)
            previous_opportunity = opportunity
            continue

        gain = predicted_covariance[:, 0] / innovation_variance
        updated_state = predicted_state + gain * innovation
        identity = np.eye(2)
        measurement = np.asarray(((1.0, 0.0),))
        residual_projection = identity - np.outer(gain, measurement[0])
        updated_covariance = (
            residual_projection @ predicted_covariance @ residual_projection.T
            + np.outer(gain, gain) * measurement_variance
        )
        active.state = updated_state
        active.covariance = 0.5 * (updated_covariance + updated_covariance.T)
        active.state_time_s = reference_time_s
        active.coast_frames = 0
        active.last_frame_start_sample = start
        active.supported_frame_count += 1
        frames.append(
            RecoveredFrame(
                opportunity_index=opportunity_index,
                anchor_id=anchor.anchor_id,
                lattice_index=opportunity.lattice_index,
                frame_start_sample=start,
                reference_sample=reference_sample,
                outcome=outcome,
                mode=RecoveryFilterMode.TRACK,
                locklet_index=active.index,
                reacquired=False,
                hard_split_before=hard_split_before,
                split_reason=split_reason,
                estimator_seed_cfo_hz=seed_cfo_hz,
                predicted_cfo_hz=float(predicted_state[0]),
                tracked_cfo_hz=float(updated_state[0]),
                tracked_rate_hz_s=float(updated_state[1]),
                filter_accepted=True,
                predicted_only=False,
                frequency_innovation_hz=innovation,
                normalized_frequency_innovation=float(normalized),
                odd_prediction_error_hz=odd_error,
                rejection_reasons=(),
                primary=primary,
                split_validation=split,
            )
        )
        previous_opportunity = opportunity

    finish_active(LockletEndReason.END_OF_INPUT)
    return ContinuousFrameRecoveryResult(
        sample_start=sample_start,
        sample_stop=sample_stop,
        sample_rate_hz=sample_rate_hz,
        frames=tuple(frames),
        locklets=tuple(locklets),
        unanchored_spans=uncovered,
    )


def _validate_anchors(
    anchors: tuple[FrameRecoveryAnchor, ...],
    sample_start: int,
    sample_stop: int,
) -> tuple[FrameRecoveryAnchor, ...]:
    if not anchors:
        raise ValueError("continuous recovery requires at least one anchor")
    ordered = tuple(sorted(anchors, key=lambda item: (item.ownership_start_sample, item.anchor_id)))
    if len({item.anchor_id for item in ordered}) != len(ordered):
        raise ValueError("recovery anchor IDs must be unique")
    if any(
        left.ownership_stop_sample > right.ownership_start_sample
        for left, right in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("recovery anchor ownership intervals must not overlap")
    if not any(
        item.ownership_stop_sample > sample_start and item.ownership_start_sample < sample_stop
        for item in ordered
    ):
        raise ValueError("no recovery anchor overlaps the input")
    return ordered


def _frame_opportunities(
    anchors: tuple[FrameRecoveryAnchor, ...],
    *,
    sample_start: int,
    sample_stop: int,
    sample_rate_hz: int,
) -> tuple[_Opportunity, ...]:
    output: list[_Opportunity] = []
    for anchor in anchors:
        start = max(sample_start, anchor.ownership_start_sample)
        stop = min(sample_stop, anchor.ownership_stop_sample)
        if start >= stop:
            continue
        index = math.floor((start - anchor.epoch_sample) * FRAME_RATE_HZ / sample_rate_hz) - 2
        frame_start = _lattice_sample(anchor.epoch_sample, index, sample_rate_hz)
        while frame_start < start:
            index += 1
            frame_start = _lattice_sample(anchor.epoch_sample, index, sample_rate_hz)
        while frame_start < stop:
            output.append(_Opportunity(anchor, index, frame_start))
            index += 1
            frame_start = _lattice_sample(anchor.epoch_sample, index, sample_rate_hz)
    output.sort(key=lambda item: (item.frame_start_sample, item.anchor.anchor_id))
    if any(
        left.frame_start_sample >= right.frame_start_sample
        for left, right in zip(output, output[1:], strict=False)
    ):
        raise ValueError("anchor-owned frame opportunities must be strictly ordered")
    return tuple(output)


def _lattice_sample(epoch_sample: int, frame_index: int, sample_rate_hz: int) -> int:
    return epoch_sample + round(frame_index * sample_rate_hz / FRAME_RATE_HZ)


def _nearest_lattice_sample(anchor: FrameRecoveryAnchor, sample: int, sample_rate_hz: int) -> int:
    approximate = round((sample - anchor.epoch_sample) * FRAME_RATE_HZ / sample_rate_hz)
    candidates = (
        _lattice_sample(anchor.epoch_sample, approximate - 1, sample_rate_hz),
        _lattice_sample(anchor.epoch_sample, approximate, sample_rate_hz),
        _lattice_sample(anchor.epoch_sample, approximate + 1, sample_rate_hz),
    )
    return min(candidates, key=lambda value: (abs(value - sample), value))


def _anchor_incompatibility(
    left: FrameRecoveryAnchor,
    right: FrameRecoveryAnchor,
    sample_rate_hz: int,
    config: FrameRecoveryConfig,
) -> LockletEndReason | None:
    if left.sample_source_id != right.sample_source_id:
        return LockletEndReason.ANCHOR_SOURCE_CHANGED
    if (
        left.continuity_source_id is None
        or right.continuity_source_id is None
        or left.continuity_source_id != right.continuity_source_id
    ):
        return LockletEndReason.ANCHOR_SOURCE_CHANGED
    if left.edge != right.edge:
        return LockletEndReason.ANCHOR_EDGE_CHANGED
    if (
        left.cfo_alias_index is None
        or right.cfo_alias_index is None
        or left.cfo_alias_index != right.cfo_alias_index
    ):
        return LockletEndReason.ANCHOR_ALIAS_CHANGED
    boundary = right.ownership_start_sample
    left_start = _nearest_lattice_sample(left, boundary, sample_rate_hz)
    right_start = _nearest_lattice_sample(right, boundary, sample_rate_hz)
    if abs(left_start - right_start) > config.maximum_anchor_epoch_error_samples:
        return LockletEndReason.ANCHOR_EPOCH_INCOMPATIBLE
    if (
        abs(left.acquisition_absolute_cfo_hz - right.acquisition_absolute_cfo_hz)
        > config.maximum_anchor_cfo_difference_hz
    ):
        return LockletEndReason.ANCHOR_CFO_INCOMPATIBLE
    return None


def _anchor_hard_boundaries(
    anchors: tuple[FrameRecoveryAnchor, ...],
    sample_rate_hz: int,
    config: FrameRecoveryConfig,
) -> dict[int, LockletEndReason]:
    output: dict[int, LockletEndReason] = {}
    for left, right in zip(anchors, anchors[1:], strict=False):
        if left.ownership_stop_sample != right.ownership_start_sample:
            continue
        reason = _anchor_incompatibility(left, right, sample_rate_hz, config)
        if reason is not None:
            output[right.ownership_start_sample] = reason
    return output


def _unanchored_spans(
    anchors: tuple[FrameRecoveryAnchor, ...],
    sample_start: int,
    sample_stop: int,
) -> tuple[UnanchoredSampleSpan, ...]:
    cursor = sample_start
    output = []
    for anchor in anchors:
        start = max(sample_start, anchor.ownership_start_sample)
        stop = min(sample_stop, anchor.ownership_stop_sample)
        if start >= stop:
            continue
        if start > cursor:
            output.append(UnanchoredSampleSpan(cursor, start))
        cursor = max(cursor, stop)
    if cursor < sample_stop:
        output.append(UnanchoredSampleSpan(cursor, sample_stop))
    return tuple(output)


def _first_boundary(boundaries: tuple[int, ...], lower: int, upper: int) -> int | None:
    index = bisect.bisect_right(boundaries, lower)
    return boundaries[index] if index < len(boundaries) and boundaries[index] <= upper else None


def _crossed_boundary(
    boundaries: tuple[int, ...] | dict[int, LockletEndReason],
    slice_start: int,
    slice_stop: int,
) -> int | None:
    ordered = tuple(boundaries)
    index = bisect.bisect_right(ordered, slice_start)
    return ordered[index] if index < len(ordered) and ordered[index] < slice_stop else None


def _prediction(
    active: _ActiveLocklet | None,
    target_time_s: float,
    config: FrameRecoveryConfig,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if active is None:
        return None, None
    dt_s = target_time_s - active.state_time_s
    if dt_s <= 0.0:
        raise ValueError("frame reference times must be strictly increasing")
    transition = np.asarray(((1.0, dt_s), (0.0, 1.0)))
    process_power = config.rate_process_sigma_hz_s_sqrt_s**2
    process = process_power * np.asarray(((dt_s**3 / 3.0, dt_s**2 / 2.0), (dt_s**2 / 2.0, dt_s)))
    return (
        transition @ active.state,
        transition @ active.covariance @ transition.T + process,
    )


def _measurement_outcome(split: PilotFrameCfoSplitValidation) -> FrameOpportunityOutcome:
    if split.status is NumericalStatus.NO_RESULT:
        return FrameOpportunityOutcome.ESTIMATOR_NO_RESULT
    if split.status is not NumericalStatus.COMPLETE or not split.training_supported:
        return FrameOpportunityOutcome.REJECTED
    return FrameOpportunityOutcome.SUPPORTED


def _idle_mode(locklets: list[RecoveryLocklet]) -> RecoveryFilterMode:
    return RecoveryFilterMode.REACQUIRE if locklets else RecoveryFilterMode.ACQUIRE


def _missed_frame(
    opportunity_index: int,
    opportunity: _Opportunity,
    reference_sample: float,
    outcome: FrameOpportunityOutcome,
    rejection_reasons: tuple[str, ...],
    active: _ActiveLocklet | None,
    locklets: list[RecoveryLocklet],
    config: FrameRecoveryConfig,
    sample_rate_hz: int,
    hard_split_before: bool,
    split_reason: LockletEndReason | None,
    finish_active: Callable[[LockletEndReason], None],
    *,
    estimator_seed_cfo_hz: float | None = None,
    primary: PilotFrameCfoEstimate | None = None,
    split_validation: PilotFrameCfoSplitValidation | None = None,
    predicted_state: np.ndarray | None = None,
    predicted_covariance: np.ndarray | None = None,
    frequency_innovation_hz: float | None = None,
    normalized_frequency_innovation: float | None = None,
    odd_prediction_error_hz: float | None = None,
) -> tuple[RecoveredFrame, _ActiveLocklet | None]:
    predicted_only = False
    locklet_index: int | None = None
    tracked_cfo_hz: float | None = None
    tracked_rate_hz_s: float | None = None
    mode = _idle_mode(locklets)
    if active is not None:
        if predicted_state is None or predicted_covariance is None:
            target_time_s = reference_sample / sample_rate_hz
            predicted_state, predicted_covariance = _prediction(active, target_time_s, config)
        assert predicted_state is not None and predicted_covariance is not None
        active.coast_frames += 1
        if active.coast_frames <= config.maximum_coast_frames:
            active.state = predicted_state
            active.covariance = predicted_covariance
            active.state_time_s = reference_sample / sample_rate_hz
            active.last_frame_start_sample = opportunity.frame_start_sample
            active.predicted_only_frame_count += 1
            predicted_only = True
            locklet_index = active.index
            tracked_cfo_hz = float(active.state[0])
            tracked_rate_hz_s = float(active.state[1])
            mode = RecoveryFilterMode.COAST
        else:
            finish_active(LockletEndReason.COAST_EXPIRED)
            active = None
            mode = RecoveryFilterMode.LOST
    frame = RecoveredFrame(
        opportunity_index=opportunity_index,
        anchor_id=opportunity.anchor.anchor_id,
        lattice_index=opportunity.lattice_index,
        frame_start_sample=opportunity.frame_start_sample,
        reference_sample=reference_sample,
        outcome=outcome,
        mode=mode,
        locklet_index=locklet_index,
        reacquired=False,
        hard_split_before=hard_split_before,
        split_reason=split_reason,
        estimator_seed_cfo_hz=estimator_seed_cfo_hz,
        predicted_cfo_hz=float(predicted_state[0]) if predicted_state is not None else None,
        tracked_cfo_hz=tracked_cfo_hz,
        tracked_rate_hz_s=tracked_rate_hz_s,
        filter_accepted=False,
        predicted_only=predicted_only,
        frequency_innovation_hz=frequency_innovation_hz,
        normalized_frequency_innovation=normalized_frequency_innovation,
        odd_prediction_error_hz=odd_prediction_error_hz,
        rejection_reasons=rejection_reasons,
        primary=primary,
        split_validation=split_validation,
    )
    return frame, active


def _empty_frame(
    opportunity_index: int,
    opportunity: _Opportunity,
    reference_sample: float,
    *,
    outcome: FrameOpportunityOutcome,
    mode: RecoveryFilterMode,
    hard_split_before: bool,
    split_reason: LockletEndReason | None,
    rejection_reasons: tuple[str, ...],
) -> RecoveredFrame:
    return RecoveredFrame(
        opportunity_index=opportunity_index,
        anchor_id=opportunity.anchor.anchor_id,
        lattice_index=opportunity.lattice_index,
        frame_start_sample=opportunity.frame_start_sample,
        reference_sample=reference_sample,
        outcome=outcome,
        mode=mode,
        locklet_index=None,
        reacquired=False,
        hard_split_before=hard_split_before,
        split_reason=split_reason,
        estimator_seed_cfo_hz=None,
        predicted_cfo_hz=None,
        tracked_cfo_hz=None,
        tracked_rate_hz_s=None,
        filter_accepted=False,
        predicted_only=False,
        frequency_innovation_hz=None,
        normalized_frequency_innovation=None,
        odd_prediction_error_hz=None,
        rejection_reasons=rejection_reasons,
        primary=None,
        split_validation=None,
    )


__all__ = [
    "ContinuousFrameRecoveryResult",
    "FrameOpportunityOutcome",
    "FrameRecoveryAnchor",
    "FrameRecoveryConfig",
    "LockletEndReason",
    "RecoveredFrame",
    "RecoveryFilterMode",
    "RecoveryLocklet",
    "UnanchoredSampleSpan",
    "anchors_compatible",
    "recover_contiguous_frames",
]
