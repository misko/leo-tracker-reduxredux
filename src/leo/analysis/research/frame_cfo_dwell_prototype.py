"""Bounded research prototype for independently qualified 750 Hz frame CFO.

The 20 ms GLRT remains authoritative for detection, frame epoch, and CFO-alias
identity.  This module only refines one explicitly supplied acquisition basin
inside complete 1/750-second frame opportunities.  It never connects carrier
phase across frames and never substitutes a wider sensitivity search for the
primary result.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import asdict, dataclass, replace
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
from leo.contracts.digests import canonical_digest

SYMBOL_CFO_ALIAS_SPACING_HZ = 1.0 / OFDM_SYMBOL_DURATION_S


class PrototypeRegionRole(StrEnum):
    EARLY_MEDIAN_MARGIN = "early_median_margin"
    MIDDLE_MEDIAN_MARGIN = "middle_median_margin"
    LATE_MEDIAN_MARGIN = "late_median_margin"
    HIGH_MARGIN = "high_margin"
    LOW_POSITIVE_MARGIN = "low_positive_margin"
    REFILL_BOUNDARY = "refill_boundary"


@dataclass(frozen=True, slots=True)
class FrameCfoDwellPrototypeConfig:
    region_duration_s: float = 0.075
    primary_residual_half_width_hz: float = 2_000.0
    sensitivity_residual_half_width_hz: float = 6_000.0
    strong_exact_gate: float = 0.10
    strong_margin_gate: float = 0.05
    minimum_validation_frames: int = 24
    minimum_ramp_frames: int = 6
    minimum_ramp_span_s: float = 0.008
    minimum_validation_ramps: int = 3

    def __post_init__(self) -> None:
        positive = (
            self.region_duration_s,
            self.primary_residual_half_width_hz,
            self.sensitivity_residual_half_width_hz,
            self.strong_exact_gate,
            self.strong_margin_gate,
            self.minimum_ramp_span_s,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("prototype thresholds must be finite and positive")
        if self.sensitivity_residual_half_width_hz <= self.primary_residual_half_width_hz:
            raise ValueError("sensitivity search must be wider than the primary search")
        counts = (
            self.minimum_validation_frames,
            self.minimum_ramp_frames,
            self.minimum_validation_ramps,
        )
        if any(value < 1 for value in counts):
            raise ValueError("prototype support counts must be positive")


@dataclass(frozen=True, slots=True)
class PrototypeProbe:
    probe_index: int
    canonical_observation_id: str
    source_observation_id: str
    detection_time_s: float
    detection_sample_start: int
    local_epoch_sample: int
    raw_source_cfo_hz: float
    observation_alias_index: int
    exact_score: float
    control_score: float
    margin: float

    @property
    def aligned_epoch_sample(self) -> int:
        return self.detection_sample_start + self.local_epoch_sample


@dataclass(frozen=True, slots=True)
class TrajectoryHypothesis:
    trajectory_id: str
    branch_id: str
    alias_index: int
    reference_time_s: float
    absolute_coefficients_hz: tuple[float, ...]
    automatic_correction_eligible: bool

    def model_cfo_hz(self, time_s: npt.ArrayLike) -> np.ndarray:
        local = np.asarray(time_s, dtype=float) - self.reference_time_s
        return np.asarray(np.polyval(self.absolute_coefficients_hz, local), dtype=float)

    def model_rate_hz_s(self, time_s: float) -> float:
        derivative = np.polyder(np.asarray(self.absolute_coefficients_hz, dtype=float))
        return float(np.polyval(derivative, time_s - self.reference_time_s))


@dataclass(frozen=True, slots=True)
class PrototypeRegion:
    region_id: str
    role: PrototypeRegionRole
    probe: PrototypeProbe
    sample_start: int
    sample_count: int
    strong_glrt_region: bool
    refill_boundary_sample: int | None

    @property
    def sample_stop(self) -> int:
        return self.sample_start + self.sample_count


@dataclass(frozen=True, slots=True)
class FrameOpportunity:
    frame_index: int
    frame_start_sample: int
    local_frame_start: int
    continuity_segment: int
    crosses_refill_boundary: bool
    strong_interior_opportunity: bool


@dataclass(frozen=True, slots=True)
class FrameCfoPrototypeRow:
    row_id: str
    region_id: str
    region_role: PrototypeRegionRole
    strong_interior_opportunity: bool
    trajectory_id: str
    branch_id: str
    trajectory_alias_index: int
    canonical_observation_id: str
    source_observation_id: str
    observation_alias_index: int
    frame_index: int
    frame_start_sample: int
    frame_time_s: float
    continuity_segment: int
    crosses_refill_boundary: bool
    raw_source_cfo_hz: float
    source_bound_seed_hz: float
    trajectory_model_cfo_hz: float
    primary: PilotFrameCfoEstimate | None
    sensitivity: PilotFrameCfoEstimate | None
    split_validation: PilotFrameCfoSplitValidation | None
    candidate_only: bool = True
    known_pilots_only: bool = True
    phase_continuity_assumed: bool = False
    sensitivity_substituted: bool = False

    def document(self) -> dict[str, object]:
        def estimate(
            value: PilotFrameCfoEstimate | PilotFrameCfoSplitValidation | None,
        ) -> dict[str, object] | None:
            if value is None:
                return None
            document = asdict(value)
            document["status"] = value.status.value
            return document

        return {
            "row_id": self.row_id,
            "region_id": self.region_id,
            "region_role": self.region_role.value,
            "strong_interior_opportunity": self.strong_interior_opportunity,
            "trajectory_id": self.trajectory_id,
            "branch_id": self.branch_id,
            "trajectory_alias_index": self.trajectory_alias_index,
            "canonical_observation_id": self.canonical_observation_id,
            "source_observation_id": self.source_observation_id,
            "observation_alias_index": self.observation_alias_index,
            "frame_index": self.frame_index,
            "frame_start_sample": self.frame_start_sample,
            "frame_time_s": self.frame_time_s,
            "continuity_segment": self.continuity_segment,
            "crosses_refill_boundary": self.crosses_refill_boundary,
            "raw_source_cfo_hz": self.raw_source_cfo_hz,
            "source_bound_seed_hz": self.source_bound_seed_hz,
            "trajectory_model_cfo_hz": self.trajectory_model_cfo_hz,
            "primary": estimate(self.primary),
            "sensitivity": estimate(self.sensitivity),
            "split_validation": estimate(self.split_validation),
            "candidate_only": self.candidate_only,
            "known_pilots_only": self.known_pilots_only,
            "phase_continuity_assumed": self.phase_continuity_assumed,
            "sensitivity_substituted": self.sensitivity_substituted,
        }


def source_bound_seed_hz(probe: PrototypeProbe, hypothesis: TrajectoryHypothesis) -> float:
    """Lift one exact raw GLRT source into one explicit final alias hypothesis."""

    return float(
        probe.raw_source_cfo_hz
        + (hypothesis.alias_index - probe.observation_alias_index) * SYMBOL_CFO_ALIAS_SPACING_HZ
    )


def select_prototype_regions(
    probes: tuple[PrototypeProbe, ...],
    *,
    refill_boundaries: tuple[int, ...],
    sample_rate_hz: int,
    recording_sample_count: int,
    config: FrameCfoDwellPrototypeConfig | None = None,
) -> tuple[PrototypeRegion, ...]:
    """Select six deterministic, disjoint regions from GLRT and refill evidence."""

    settings = config or FrameCfoDwellPrototypeConfig()
    if sample_rate_hz <= 0 or recording_sample_count <= 0:
        raise ValueError("recording geometry must be positive")
    region_samples = round(settings.region_duration_s * sample_rate_hz)
    ordered = tuple(
        sorted(
            probes,
            key=lambda item: (
                item.detection_time_s,
                item.detection_sample_start,
                item.probe_index,
            ),
        )
    )
    if len({item.probe_index for item in ordered}) != len(ordered):
        raise ValueError("prototype probe indices must be unique")
    eligible = tuple(
        item
        for item in ordered
        if item.aligned_epoch_sample >= 1
        and item.aligned_epoch_sample + region_samples <= recording_sample_count
    )
    if len(eligible) < 6:
        raise ValueError("fewer than six complete GLRT-bound prototype regions are available")
    boundaries = tuple(sorted(set(int(item) for item in refill_boundaries)))
    if boundaries != refill_boundaries:
        raise ValueError("refill boundaries must be unique and sorted")
    if any(item <= 0 or item >= recording_sample_count for item in boundaries):
        raise ValueError("refill boundary lies outside the recording interior")

    first_time = eligible[0].detection_time_s
    last_time = eligible[-1].detection_time_s
    span = last_time - first_time
    if span <= 0.0:
        raise ValueError("prototype probes do not span time")
    third_edges = (first_time, first_time + span / 3.0, first_time + 2.0 * span / 3.0, last_time)

    role_candidates: dict[PrototypeRegionRole, tuple[tuple[PrototypeProbe, int | None], ...]] = {}
    for third_index, role in enumerate(
        (
            PrototypeRegionRole.EARLY_MEDIAN_MARGIN,
            PrototypeRegionRole.MIDDLE_MEDIAN_MARGIN,
            PrototypeRegionRole.LATE_MEDIAN_MARGIN,
        )
    ):
        lower = third_edges[third_index]
        upper = third_edges[third_index + 1]
        members = tuple(
            item
            for item in eligible
            if item.detection_time_s >= lower
            and (
                item.detection_time_s < upper
                or (third_index == 2 and item.detection_time_s <= upper)
            )
        )
        median = float(np.median([item.margin for item in members]))
        ranked = sorted(
            members,
            key=lambda item: (
                abs(item.margin - median),
                -item.exact_score,
                item.detection_time_s,
                item.probe_index,
            ),
        )
        role_candidates[role] = tuple((item, None) for item in ranked)

    role_candidates[PrototypeRegionRole.HIGH_MARGIN] = tuple(
        (item, None)
        for item in sorted(
            eligible,
            key=lambda item: (
                -item.margin,
                -item.exact_score,
                item.detection_time_s,
                item.probe_index,
            ),
        )
    )
    positive = tuple(item for item in eligible if item.margin > 0.0)
    role_candidates[PrototypeRegionRole.LOW_POSITIVE_MARGIN] = tuple(
        (item, None)
        for item in sorted(
            positive,
            key=lambda item: (
                item.margin,
                item.exact_score,
                item.detection_time_s,
                item.probe_index,
            ),
        )
    )
    boundary_candidates = []
    for item in eligible:
        start = item.aligned_epoch_sample
        stop = start + region_samples
        inside = tuple(boundary for boundary in boundaries if start < boundary < stop)
        for boundary in inside:
            boundary_candidates.append(
                (
                    abs(boundary - (start + region_samples / 2.0)),
                    item.detection_time_s,
                    item.probe_index,
                    item,
                    boundary,
                )
            )
    role_candidates[PrototypeRegionRole.REFILL_BOUNDARY] = tuple(
        (item, boundary) for _distance, _time, _index, item, boundary in sorted(boundary_candidates)
    )

    selected: list[PrototypeRegion] = []
    strong_roles = {
        PrototypeRegionRole.EARLY_MEDIAN_MARGIN,
        PrototypeRegionRole.MIDDLE_MEDIAN_MARGIN,
        PrototypeRegionRole.LATE_MEDIAN_MARGIN,
        PrototypeRegionRole.HIGH_MARGIN,
    }
    for role in PrototypeRegionRole:
        candidates = role_candidates.get(role, ())
        chosen: tuple[PrototypeProbe, int | None] | None = None
        for candidate, candidate_boundary in candidates:
            start = candidate.aligned_epoch_sample
            stop = start + region_samples
            if all(stop <= item.sample_start or start >= item.sample_stop for item in selected):
                chosen = (candidate, candidate_boundary)
                break
        if chosen is None:
            raise ValueError(f"cannot select a disjoint {role.value} prototype region")
        probe, selected_boundary = chosen
        strong = bool(
            role in strong_roles
            and probe.exact_score >= settings.strong_exact_gate
            and probe.margin >= settings.strong_margin_gate
        )
        region_id = canonical_digest(
            {
                "role": role.value,
                "probe_index": probe.probe_index,
                "sample_start": probe.aligned_epoch_sample,
                "sample_count": region_samples,
            }
        )
        selected.append(
            PrototypeRegion(
                region_id=region_id,
                role=role,
                probe=probe,
                sample_start=probe.aligned_epoch_sample,
                sample_count=region_samples,
                strong_glrt_region=strong,
                refill_boundary_sample=selected_boundary,
            )
        )
    return tuple(selected)


def frame_opportunities(
    region: PrototypeRegion,
    *,
    sample_rate_hz: int,
    refill_boundaries: tuple[int, ...],
) -> tuple[FrameOpportunity, ...]:
    """Build an exact rounded 750 Hz frame lattice with refill-aware guards."""

    if sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive")
    boundaries = tuple(sorted(set(refill_boundaries)))
    if boundaries != refill_boundaries:
        raise ValueError("refill boundaries must be unique and sorted")
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    output = []
    frame_index = 0
    while True:
        local_start = round(frame_index * sample_rate_hz / FRAME_RATE_HZ)
        if local_start + frame_content > region.sample_count:
            break
        absolute = region.sample_start + local_start
        slice_start = absolute - 1
        slice_stop = absolute + frame_content + 1
        first = bisect.bisect_right(boundaries, slice_start)
        crosses = first < len(boundaries) and boundaries[first] < slice_stop
        output.append(
            FrameOpportunity(
                frame_index=frame_index,
                frame_start_sample=absolute,
                local_frame_start=local_start,
                continuity_segment=bisect.bisect_right(boundaries, absolute),
                crosses_refill_boundary=crosses,
                strong_interior_opportunity=region.strong_glrt_region and not crosses,
            )
        )
        frame_index += 1
    return tuple(output)


def analyze_region_hypothesis(
    guarded_region_samples: npt.ArrayLike,
    *,
    region: PrototypeRegion,
    hypothesis: TrajectoryHypothesis,
    edge: StarlinkEdge | str,
    sample_rate_hz: int,
    refill_boundaries: tuple[int, ...],
    config: FrameCfoDwellPrototypeConfig | None = None,
) -> tuple[FrameCfoPrototypeRow, ...]:
    """Run primary, wide-sensitivity, and split-validation lanes for one region."""

    settings = config or FrameCfoDwellPrototypeConfig()
    values = np.asarray(guarded_region_samples, dtype=np.complex128)
    if values.ndim != 1 or values.size != region.sample_count + 2:
        raise ValueError("guarded region must contain the region plus one sample on each side")
    if not np.all(np.isfinite(values)):
        raise ValueError("guarded region samples must be finite")
    primary_config = replace(
        PilotFrameCfoConfig(),
        residual_half_width_hz=settings.primary_residual_half_width_hz,
    )
    sensitivity_config = replace(
        primary_config,
        residual_half_width_hz=settings.sensitivity_residual_half_width_hz,
    )
    seed_hz = source_bound_seed_hz(region.probe, hypothesis)
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    output = []
    for opportunity in frame_opportunities(
        region,
        sample_rate_hz=sample_rate_hz,
        refill_boundaries=refill_boundaries,
    ):
        reference_sample = opportunity.frame_start_sample + float(
            np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S) * sample_rate_hz
        )
        frame_time_s = reference_sample / sample_rate_hz
        primary = None
        sensitivity = None
        split = None
        if not opportunity.crosses_refill_boundary:
            local = opportunity.local_frame_start
            guarded = values[local : local + frame_content + 2]
            primary = estimate_edge_pilot_frame_cfo(
                guarded,
                sample_rate_hz,
                frame_start_sample=opportunity.frame_start_sample,
                acquisition_absolute_cfo_hz=seed_hz,
                edge=edge,
                config=primary_config,
            )
            sensitivity = estimate_edge_pilot_frame_cfo(
                guarded,
                sample_rate_hz,
                frame_start_sample=opportunity.frame_start_sample,
                acquisition_absolute_cfo_hz=seed_hz,
                edge=edge,
                config=sensitivity_config,
            )
            split = estimate_edge_pilot_frame_cfo_split_validation(
                guarded,
                sample_rate_hz,
                frame_start_sample=opportunity.frame_start_sample,
                acquisition_absolute_cfo_hz=seed_hz,
                edge=edge,
                config=primary_config,
            )
        identity = {
            "region_id": region.region_id,
            "trajectory_id": hypothesis.trajectory_id,
            "frame_start_sample": opportunity.frame_start_sample,
        }
        output.append(
            FrameCfoPrototypeRow(
                row_id=canonical_digest(identity),
                region_id=region.region_id,
                region_role=region.role,
                strong_interior_opportunity=opportunity.strong_interior_opportunity,
                trajectory_id=hypothesis.trajectory_id,
                branch_id=hypothesis.branch_id,
                trajectory_alias_index=hypothesis.alias_index,
                canonical_observation_id=region.probe.canonical_observation_id,
                source_observation_id=region.probe.source_observation_id,
                observation_alias_index=region.probe.observation_alias_index,
                frame_index=opportunity.frame_index,
                frame_start_sample=opportunity.frame_start_sample,
                frame_time_s=frame_time_s,
                continuity_segment=opportunity.continuity_segment,
                crosses_refill_boundary=opportunity.crosses_refill_boundary,
                raw_source_cfo_hz=region.probe.raw_source_cfo_hz,
                source_bound_seed_hz=seed_hz,
                trajectory_model_cfo_hz=float(hypothesis.model_cfo_hz(frame_time_s)),
                primary=primary,
                sensitivity=sensitivity,
                split_validation=split,
            )
        )
    return tuple(output)


def summarize_hypothesis(
    rows: tuple[FrameCfoPrototypeRow, ...],
    hypothesis: TrajectoryHypothesis,
    *,
    config: FrameCfoDwellPrototypeConfig | None = None,
) -> dict[str, object]:
    """Summarize non-tautological diagnostics and an even/odd common-rate fit."""

    settings = config or FrameCfoDwellPrototypeConfig()
    if not rows or any(item.trajectory_id != hypothesis.trajectory_id for item in rows):
        raise ValueError("summary rows must belong to exactly the requested hypothesis")
    quality = PilotFrameCfoConfig(residual_half_width_hz=settings.primary_residual_half_width_hz)
    complete = tuple(
        item
        for item in rows
        if item.primary is not None and item.primary.status is NumericalStatus.COMPLETE
    )
    diagnostic = tuple(
        item
        for item in complete
        if item.primary is not None
        and item.primary.exact_coherence is not None
        and item.primary.coherence_margin is not None
        and item.primary.exact_coherence >= quality.minimum_exact_coherence
        and item.primary.coherence_margin >= quality.minimum_coherence_margin
    )
    strong = tuple(item for item in rows if item.strong_interior_opportunity)
    retained = tuple(
        item for item in strong if item.primary is not None and item.primary.measurement_supported
    )

    def p95(field: str) -> float | None:
        values = [getattr(item.primary, field) for item in diagnostic if item.primary is not None]
        finite = np.asarray([value for value in values if value is not None], dtype=float)
        return float(np.percentile(finite, 95)) if finite.size else None

    strong_diagnostic = tuple(item for item in diagnostic if item.strong_interior_opportunity)
    strong_diagnostic_estimates = tuple(
        item.primary for item in strong_diagnostic if item.primary is not None
    )
    boundary_fraction = (
        float(np.mean([item.search_boundary for item in strong_diagnostic_estimates]))
        if strong_diagnostic_estimates
        else None
    )
    paired_search = tuple(
        (item.primary, item.sensitivity)
        for item in diagnostic
        if item.primary is not None
        and item.primary.residual_cfo_hz is not None
        and item.sensitivity is not None
        and item.sensitivity.residual_cfo_hz is not None
    )
    wide_values = []
    for primary, sensitivity in paired_search:
        assert primary is not None and primary.residual_cfo_hz is not None
        assert sensitivity is not None and sensitivity.residual_cfo_hz is not None
        wide_values.append(sensitivity.residual_cfo_hz - primary.residual_cfo_hz)
    wide_difference = np.asarray(wide_values, dtype=float)
    validation = _validation_summary(rows, hypothesis, settings)
    return {
        "trajectory_id": hypothesis.trajectory_id,
        "branch_id": hypothesis.branch_id,
        "alias_index": hypothesis.alias_index,
        "automatic_correction_eligible": hypothesis.automatic_correction_eligible,
        "frame_opportunity_count": len(rows),
        "refill_crossing_frame_count": sum(item.crosses_refill_boundary for item in rows),
        "numerically_complete_frame_count": len(complete),
        "diagnostic_frame_count": len(diagnostic),
        "supported_frame_count": sum(
            bool(item.primary and item.primary.measurement_supported) for item in rows
        ),
        "strong_interior_opportunity_count": len(strong),
        "strong_interior_supported_count": len(retained),
        "strong_interior_retention_fraction": (len(retained) / len(strong) if strong else None),
        "diagnostics_population": (
            "all numerically complete continuity-safe frames passing only exact-Qin "
            "coherence/control gates; no reported diagnostic selects its own population"
        ),
        "even_odd_p95_hz": p95("even_odd_disagreement_hz"),
        "timing_spread_p95_hz": p95("timing_spread_hz"),
        "half_frame_difference_p95_z": p95("half_frame_difference_z"),
        "tone_deletion_spread_p95_hz": p95("tone_deletion_spread_hz"),
        "strong_search_boundary_fraction": boundary_fraction,
        "primary_sensitivity_pair_count": len(paired_search),
        "primary_sensitivity_difference_p95_hz": (
            float(np.percentile(np.abs(wide_difference), 95)) if wide_difference.size else None
        ),
        "wide_supported_primary_unsupported_count": sum(
            bool(
                item.sensitivity
                and item.sensitivity.measurement_supported
                and item.primary
                and not item.primary.measurement_supported
            )
            for item in diagnostic
        ),
        "sensitivity_substitution_count": sum(item.sensitivity_substituted for item in rows),
        "heldout_validation": validation,
    }


def _validation_summary(
    rows: tuple[FrameCfoPrototypeRow, ...],
    hypothesis: TrajectoryHypothesis,
    config: FrameCfoDwellPrototypeConfig,
) -> dict[str, object]:
    validation = tuple(
        item
        for item in rows
        if not item.crosses_refill_boundary
        and item.split_validation is not None
        and item.split_validation.status is NumericalStatus.COMPLETE
        and item.split_validation.training_supported
        and item.split_validation.even_absolute_cfo_hz is not None
        and item.split_validation.odd_absolute_cfo_hz is not None
    )
    grouped: dict[tuple[str, int], list[FrameCfoPrototypeRow]] = {}
    for item in validation:
        grouped.setdefault((item.region_id, item.continuity_segment), []).append(item)
    ramps = []
    for key, members in sorted(grouped.items()):
        ordered = tuple(sorted(members, key=lambda item: item.frame_time_s))
        span = ordered[-1].frame_time_s - ordered[0].frame_time_s
        if len(ordered) >= config.minimum_ramp_frames and span >= config.minimum_ramp_span_s:
            ramps.append((key, ordered))
    eligible_count = sum(len(members) for _key, members in ramps)
    if (
        eligible_count < config.minimum_validation_frames
        or len(ramps) < config.minimum_validation_ramps
    ):
        return {
            "status": "insufficient",
            "reason": "even-only validation cohort lacks minimum refill-safe ramp support",
            "even_selected_frame_count": len(validation),
            "fitted_frame_count": eligible_count,
            "ramp_count": len(ramps),
            "odd_symbols_influenced_membership": False,
        }

    reference = float(np.mean([item.frame_time_s for _key, members in ramps for item in members]))
    ramp_centers = {
        key: float(np.mean([item.frame_time_s for item in members])) for key, members in ramps
    }
    row_count = eligible_count
    design = np.zeros((row_count, len(ramps) + 1), dtype=float)
    train = np.empty(row_count, dtype=float)
    odd = np.empty(row_count, dtype=float)
    model = np.empty(row_count, dtype=float)
    ramp_indexes = np.empty(row_count, dtype=int)
    cursor = 0
    for ramp_index, (key, ramp_members) in enumerate(ramps):
        for item in ramp_members:
            split = item.split_validation
            assert split is not None
            assert split.even_absolute_cfo_hz is not None
            assert split.odd_absolute_cfo_hz is not None
            design[cursor, ramp_index] = 1.0
            design[cursor, -1] = item.frame_time_s - ramp_centers[key]
            train[cursor] = float(split.even_absolute_cfo_hz)
            odd[cursor] = float(split.odd_absolute_cfo_hz)
            model[cursor] = item.trajectory_model_cfo_hz
            ramp_indexes[cursor] = ramp_index
            cursor += 1
    coefficients, covariance, _train_residuals = _robust_linear_solve(design, train)
    local_predicted = design @ coefficients
    model_predicted = np.empty_like(model)
    for ramp_index in range(len(ramps)):
        selected = ramp_indexes == ramp_index
        centered_model = model[selected] - float(np.mean(model[selected]))
        intercept = float(np.median(train[selected] - centered_model))
        model_predicted[selected] = intercept + centered_model
    local_errors = odd - local_predicted
    model_errors = odd - model_predicted
    local_rms = float(np.sqrt(np.mean(local_errors**2)))
    model_rms = float(np.sqrt(np.mean(model_errors**2)))
    slope_sigma = float(math.sqrt(max(0.0, covariance[-1, -1])))
    local_rate = float(coefficients[-1])
    model_rate = hypothesis.model_rate_hz_s(reference)
    return {
        "status": "complete",
        "reason": "even-only membership and free-intercept common slope are supported",
        "even_selected_frame_count": len(validation),
        "fitted_frame_count": eligible_count,
        "ramp_count": len(ramps),
        "reference_time_s": reference,
        "local_rate_hz_s": local_rate,
        "local_rate_conditional_sigma_hz_s": slope_sigma,
        "trajectory_model_rate_hz_s": model_rate,
        "rate_difference_hz_s": local_rate - model_rate,
        "local_odd_validation_rms_hz": local_rms,
        "trajectory_odd_validation_rms_hz": model_rms,
        "odd_validation_improvement_fraction": (
            1.0 - local_rms / model_rms if model_rms > 0.0 else None
        ),
        "odd_validation_p95_absolute_hz": float(np.percentile(np.abs(local_errors), 95)),
        "odd_symbols_influenced_membership": False,
    }


def _robust_linear_solve(
    design: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    weights = np.ones(len(values), dtype=float)
    for _iteration in range(50):
        residuals = values - design @ coefficients
        center = float(np.median(residuals))
        scale = max(5.0, 1.4826 * float(np.median(np.abs(residuals - center))))
        normalized = np.abs(residuals) / (1.345 * scale)
        weights = np.ones(len(values), dtype=float)
        tail = normalized > 1.0
        weights[tail] = 1.0 / normalized[tail]
        root = np.sqrt(weights)
        updated = np.linalg.lstsq(design * root[:, None], values * root, rcond=None)[0]
        if float(np.max(np.abs(updated - coefficients))) < 1e-7:
            coefficients = updated
            break
        coefficients = updated
    residuals = values - design @ coefficients
    dof = max(1, len(values) - design.shape[1])
    variance = float(np.sum(weights * residuals**2) / dof)
    covariance = np.linalg.pinv(design.T @ (weights[:, None] * design)) * variance
    return coefficients, covariance, residuals
