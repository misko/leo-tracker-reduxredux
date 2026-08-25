"""Seed-protected, short-block Qin pilot acquisition for research V4.

This module is deliberately additive.  It does not change the published V3
full-frame search or any persisted Standard contract.  The returned decisions
are uncalibrated candidate evidence: numerical completion, research admission,
tracking, and scientific qualification remain separate outcomes.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from functools import lru_cache
from itertools import islice, product

import numpy as np

from leo.analysis.starlink.acquisition import (
    DEFAULT_ACQUIRE_SYMBOLS,
    DEFAULT_ANCHOR_SYMBOLS,
    DEFAULT_VERIFY_SYMBOLS,
    NumericalStatus,
    _circular_local_peak_indexes,
    _folded_anchor_score_grid,
)
from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
    qin_edge_pilot_frame,
    qin_edge_pilot_symbols,
    template_sha256,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.states import StarlinkEdge

DEFAULT_CONDITIONAL_CONTROL_ROLLS = (17, 53, 101)
PER_SUBCARRIER_DERANGEMENT_ROLLS = (38, 75, 112, 149, 186, 223, 260, 297)
CFO_ALIAS_SPACING_HZ = 1.0 / OFDM_SYMBOL_DURATION_S


class PilotModeProposalOrigin(StrEnum):
    """How a bounded research candidate entered the retained inventory."""

    PROTECTED_SEED = "protected_seed"
    LOCAL_SEARCH = "local_search"
    GLOBAL_FALLBACK = "global_fallback"


class ResearchEvidenceDecision(StrEnum):
    """Uncalibrated disposition of one numerically evaluated pilot mode."""

    CANDIDATE = "candidate"
    REDUNDANT_LOCAL_PROPOSAL = "redundant_local_proposal"
    REDUNDANT_GLOBAL_PROPOSAL = "redundant_global_proposal"
    ALIAS_DUPLICATE = "alias_duplicate"
    WHOLE_WINDOW_INCONSISTENT = "whole_window_inconsistent"
    REJECTED = "rejected"


class TemplateEvidenceRole(StrEnum):
    """Declared use of one content-addressed Qin waveform."""

    EXPECTED = "expected"
    CONDITIONAL_GATE = "conditional_gate"
    ORBIT_BREAKING_DIAGNOSTIC = "orbit_breaking_diagnostic"


class ResearchDisposition(StrEnum):
    """Non-production disposition of one logically separate evidence claim."""

    INSUFFICIENT = "insufficient"
    UNASSESSED = "unassessed"
    NO_RESEARCH_CANDIDATE = "no_research_candidate"
    UNCALIBRATED_CANDIDATE = "uncalibrated_candidate"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class PilotTemplateIdentity:
    """Label, content digest, and declared search role for one template."""

    label: str
    template_sha256: str
    role: TemplateEvidenceRole
    gates_research_decision: bool
    independently_reacquired: bool

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValueError("pilot template label must be nonempty")
        if not re.fullmatch(r"[0-9a-f]{64}", self.template_sha256):
            raise ValueError("pilot template digest must be a lowercase SHA-256 digest")
        if not isinstance(self.gates_research_decision, bool) or not isinstance(
            self.independently_reacquired, bool
        ):
            raise ValueError("pilot template policy fields must be boolean")


@dataclass(frozen=True, slots=True)
class KnownPilotModeSeed:
    """Provenance-bound trajectory mode supplied to bounded reacquisition."""

    nominal_epoch_sample: int
    nominal_absolute_cfo_hz: float
    branch_id: str
    provenance_sha256: str
    nominal_doppler_rate_hz_s: float = 0.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.nominal_epoch_sample, bool)
            or not isinstance(self.nominal_epoch_sample, (int, np.integer))
            or self.nominal_epoch_sample < 0
        ):
            raise ValueError("seed epoch must be a nonnegative integer")
        if not math.isfinite(self.nominal_absolute_cfo_hz):
            raise ValueError("seed CFO must be finite")
        if not math.isfinite(self.nominal_doppler_rate_hz_s):
            raise ValueError("seed Doppler rate must be finite")
        if not self.branch_id or not self.branch_id.strip():
            raise ValueError("seed branch_id must be nonempty")
        if not re.fullmatch(r"[0-9a-f]{64}", self.provenance_sha256):
            raise ValueError("seed provenance_sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class SeededPilotAcquisitionConfig:
    """Frozen bounds and descriptive gates for the research acquisition."""

    block_duration_s: float = 0.020
    block_count: int = 4
    local_epoch_radius_samples: int = 2
    local_cfo_radius_hz: float = 500.0
    local_cfo_step_hz: float = 50.0
    retained_candidate_count: int = 4
    candidate_epoch_separation_samples: int = 2
    candidate_cfo_separation_hz: float = 100.0
    minimum_frame_support_per_block: int = 2
    minimum_exact_score: float = 0.08
    minimum_exact_minus_control_margin: float = 0.02
    minimum_consensus_blocks: int = 3
    control_symbol_rolls: tuple[int, ...] = DEFAULT_CONDITIONAL_CONTROL_ROLLS
    trajectory_epoch_radius_samples: int = 2
    trajectory_cfo_radius_hz: float = 100.0
    trajectory_candidates_per_block: int = 4
    maximum_trajectory_epoch_span_samples: int = 3
    maximum_adjacent_trajectory_epoch_step_samples: int = 1
    maximum_trajectory_epoch_fit_rms_samples: float = 0.75
    maximum_trajectory_cfo_span_hz: float = 100.0
    maximum_trajectory_path_count: int = 256
    global_fallback_enabled: bool = True
    global_proposal_block_index: int = 0
    global_proposal_symbols: tuple[int, ...] = DEFAULT_ANCHOR_SYMBOLS
    global_cfo_radius_hz: float = 2_000.0
    global_cfo_step_hz: float = 250.0
    global_retained_candidate_count: int = 8
    global_candidate_epoch_separation_samples: int = 20
    global_candidate_cfo_separation_hz: float = 500.0
    global_component_epoch_tolerance_samples: int = 3
    global_component_cfo_tolerance_hz: float = 1_000.0
    cfo_alias_equivalence_tolerance_hz: float = 1e-3
    cfo_alias_rate_tolerance_hz_s: float = 1.0
    cfo_alias_timing_tolerance_samples: float = 0.25
    maximum_additional_seed_count: int = 7
    maximum_sample_count: int = 250_000
    thresholds_calibrated: bool = False

    def __post_init__(self) -> None:
        finite = (
            self.block_duration_s,
            self.local_cfo_radius_hz,
            self.local_cfo_step_hz,
            self.candidate_cfo_separation_hz,
            self.minimum_exact_score,
            self.minimum_exact_minus_control_margin,
            self.trajectory_cfo_radius_hz,
            self.maximum_trajectory_epoch_fit_rms_samples,
            self.maximum_trajectory_cfo_span_hz,
            self.global_cfo_radius_hz,
            self.global_cfo_step_hz,
            self.global_candidate_cfo_separation_hz,
            self.global_component_cfo_tolerance_hz,
            self.cfo_alias_equivalence_tolerance_hz,
            self.cfo_alias_rate_tolerance_hz_s,
            self.cfo_alias_timing_tolerance_samples,
        )
        if not all(math.isfinite(value) for value in finite):
            raise ValueError("seeded-acquisition numerical settings must be finite")
        if self.block_duration_s <= 0.0:
            raise ValueError("block duration must be positive")
        if self.local_cfo_radius_hz < 0.0:
            raise ValueError("local CFO radius must be nonnegative")
        if self.trajectory_cfo_radius_hz < 0.0:
            raise ValueError("trajectory CFO radius must be nonnegative")
        if self.maximum_trajectory_epoch_fit_rms_samples < 0.0:
            raise ValueError("maximum trajectory epoch fit RMS must be nonnegative")
        if self.maximum_trajectory_cfo_span_hz < 0.0:
            raise ValueError("maximum trajectory CFO span must be nonnegative")
        if self.local_cfo_step_hz <= 0.0 or self.candidate_cfo_separation_hz <= 0.0:
            raise ValueError("CFO step and candidate separation must be positive")
        if self.global_cfo_radius_hz < 0.0:
            raise ValueError("global CFO radius must be nonnegative")
        if (
            self.global_cfo_step_hz <= 0.0
            or self.global_candidate_cfo_separation_hz <= 0.0
            or self.global_component_cfo_tolerance_hz <= 0.0
            or self.cfo_alias_equivalence_tolerance_hz <= 0.0
            or self.cfo_alias_rate_tolerance_hz_s < 0.0
            or self.cfo_alias_timing_tolerance_samples < 0.0
        ):
            raise ValueError("global CFO steps and separations must be positive")
        if not 0.0 <= self.minimum_exact_score <= 1.0:
            raise ValueError("minimum exact score must lie in zero to one")
        if not -1.0 <= self.minimum_exact_minus_control_margin <= 1.0:
            raise ValueError("minimum exact-minus-control margin must lie in minus one to one")
        integers = (
            self.block_count,
            self.retained_candidate_count,
            self.candidate_epoch_separation_samples,
            self.minimum_frame_support_per_block,
            self.minimum_consensus_blocks,
            self.trajectory_candidates_per_block,
            self.maximum_trajectory_path_count,
            self.global_retained_candidate_count,
            self.global_candidate_epoch_separation_samples,
            self.maximum_additional_seed_count,
            self.maximum_sample_count,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in integers
        ):
            raise ValueError("seeded-acquisition counts and bounds must be positive integers")
        if (
            isinstance(self.local_epoch_radius_samples, bool)
            or not isinstance(self.local_epoch_radius_samples, int)
            or self.local_epoch_radius_samples < 0
        ):
            raise ValueError("local epoch radius must be a nonnegative integer")
        if (
            isinstance(self.trajectory_epoch_radius_samples, bool)
            or not isinstance(self.trajectory_epoch_radius_samples, int)
            or self.trajectory_epoch_radius_samples < 0
        ):
            raise ValueError("trajectory epoch radius must be a nonnegative integer")
        if (
            isinstance(self.maximum_trajectory_epoch_span_samples, bool)
            or not isinstance(self.maximum_trajectory_epoch_span_samples, int)
            or self.maximum_trajectory_epoch_span_samples < 0
        ):
            raise ValueError("maximum trajectory epoch span must be nonnegative")
        if (
            isinstance(self.maximum_adjacent_trajectory_epoch_step_samples, bool)
            or not isinstance(self.maximum_adjacent_trajectory_epoch_step_samples, int)
            or self.maximum_adjacent_trajectory_epoch_step_samples < 0
        ):
            raise ValueError("maximum adjacent trajectory epoch step must be nonnegative")
        if (
            isinstance(self.global_component_epoch_tolerance_samples, bool)
            or not isinstance(self.global_component_epoch_tolerance_samples, int)
            or self.global_component_epoch_tolerance_samples < 0
        ):
            raise ValueError("global component epoch tolerance must be nonnegative")
        if (
            isinstance(self.global_proposal_block_index, bool)
            or not isinstance(self.global_proposal_block_index, int)
            or self.global_proposal_block_index != 0
        ):
            raise ValueError("global proposal block index is fixed at zero")
        if (
            not isinstance(self.global_proposal_symbols, tuple)
            or not self.global_proposal_symbols
            or len(set(self.global_proposal_symbols)) != len(self.global_proposal_symbols)
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value not in DEFAULT_ACQUIRE_SYMBOLS
                for value in self.global_proposal_symbols
            )
        ):
            raise ValueError("global proposal symbols must be unique even acquisition symbols")
        if self.minimum_consensus_blocks > self.block_count:
            raise ValueError("minimum consensus cannot exceed block count")
        normalized_rolls = tuple(value % 300 for value in self.control_symbol_rolls)
        if (
            not self.control_symbol_rolls
            or len(set(normalized_rolls)) != len(normalized_rolls)
            or any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in self.control_symbol_rolls
            )
        ):
            raise ValueError(
                "control symbol rolls must be nonempty, integer, and unique modulo 300"
            )
        if any(value == 0 for value in normalized_rolls):
            raise ValueError("conditional controls cannot use the exact zero-roll pilot")
        if not isinstance(self.thresholds_calibrated, bool):
            raise ValueError("thresholds_calibrated must be boolean")
        if not isinstance(self.global_fallback_enabled, bool):
            raise ValueError("global_fallback_enabled must be boolean")
        if self.thresholds_calibrated:
            raise ValueError("seeded V4 acquisition thresholds are explicitly uncalibrated")

    @property
    def digest(self) -> str:
        """Content-address the complete deterministic research configuration."""

        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class KnownPilotBlockEvidence:
    """Held-out evidence for one mode on one absolute short block."""

    block_index: int
    start_sample: int
    stop_sample: int
    first_frame_start_sample: int
    projected_epoch_sample: int
    trajectory_epoch_sample: int
    trajectory_epoch_residual_samples: int
    absolute_cfo_hz: float
    trajectory_cfo_residual_hz: float
    acquire_score: float
    verify_score: float
    control_scores: tuple[float, ...]
    diagnostic_control_scores: tuple[float, ...]
    exact_minus_control_margin: float
    acquire_frame_support: int
    verify_frame_support: int
    control_frame_support: tuple[int, ...]
    diagnostic_control_frame_support: tuple[int, ...]
    frame_support: int
    passed_research_gate: bool


@dataclass(frozen=True, slots=True)
class KnownPilotModeCandidate:
    """One bounded discrete epoch/CFO mode and its uncalibrated evidence."""

    rank: int
    proposal_origin: PilotModeProposalOrigin
    source_seed_index: int
    source_branch_id: str
    source_provenance_sha256: str
    source_nominal_epoch_sample: int
    source_nominal_absolute_cfo_hz: float
    proposal_epoch_sample: int
    proposal_absolute_cfo_hz: float
    epoch_sample: int
    absolute_cfo_hz: float
    doppler_rate_hz_s: float
    canonical_cfo_hz: float
    cfo_alias_lift: int
    acquire_score: float
    median_verify_score: float
    median_control_score: float
    median_diagnostic_control_scores: tuple[float, ...]
    median_exact_minus_control_margin: float
    passing_block_count: int
    frame_support: int
    blocks: tuple[KnownPilotBlockEvidence, ...]
    trajectory_block_epoch_samples: tuple[int, ...]
    trajectory_block_epoch_residual_samples: tuple[int, ...]
    trajectory_block_absolute_cfo_hz: tuple[float, ...]
    trajectory_block_cfo_residual_hz: tuple[float, ...]
    trajectory_epoch_span_samples: int
    trajectory_max_adjacent_epoch_step_samples: int
    trajectory_epoch_dispersion_samples: float
    trajectory_epoch_fit_rms_samples: float
    trajectory_timing_rate_samples_s: float
    trajectory_cfo_span_hz: float
    trajectory_cfo_dispersion_hz: float
    trajectory_cfo_fit_rms_hz: float
    trajectory_cfo_rate_residual_hz_s: float
    trajectory_path_sha256: str
    trajectory_admissible: bool
    whole_window_verify_score: float | None
    whole_window_control_scores: tuple[float, ...]
    whole_window_diagnostic_control_scores: tuple[float, ...]
    whole_window_exact_minus_control_margin: float | None
    whole_window_frame_support: int
    whole_window_consistent_with_blocks: bool
    decision: ResearchEvidenceDecision
    thresholds_calibrated: bool = False
    candidate_only: bool = True


@dataclass(frozen=True, slots=True)
class SeededPilotAcquisitionResult:
    """Auditable result of one bounded, seed-protected research search."""

    status: NumericalStatus
    config_digest: str
    seed: KnownPilotModeSeed
    additional_seeds: tuple[KnownPilotModeSeed, ...]
    evaluated_seed_count: int
    edge: StarlinkEdge
    expected_symbol_roll: int
    control_symbol_rolls: tuple[int, ...]
    exact_template_identity: PilotTemplateIdentity
    conditional_control_template_identities: tuple[PilotTemplateIdentity, ...]
    diagnostic_control_template_identities: tuple[PilotTemplateIdentity, ...]
    sample_rate_hz: float
    sample_count: int
    frame_period_samples: float
    block_starts: tuple[int, ...]
    searched_epoch_count: int
    searched_cfo_count: int
    evaluated_grid_point_count: int
    evaluated_block_score_count: int
    trajectory_path_evaluated_count: int
    trajectory_path_limit_truncated_count: int
    separation_suppressed_count: int
    candidate_limit_truncated_count: int
    global_fallback_attempted: bool
    global_proposal_block_index: int
    global_proposal_block_start_sample: int | None
    global_proposal_block_stop_sample: int | None
    global_proposal_sample_count: int
    global_proposal_symbol_count: int
    global_proposal_frame_offset_count: int
    global_searched_epoch_count: int
    global_searched_cfo_count: int
    global_evaluated_grid_point_count: int
    global_peak_count: int
    global_evaluated_block_score_count: int
    global_trajectory_path_evaluated_count: int
    global_trajectory_path_limit_truncated_count: int
    global_separation_suppressed_count: int
    global_candidate_limit_truncated_count: int
    whole_window_rescore_candidate_count: int
    whole_window_rescore_template_score_count: int
    retained_modes: tuple[KnownPilotModeCandidate, ...]
    presence_disposition: ResearchDisposition
    code_specificity_disposition: ResearchDisposition
    cfo_alias_resolution_disposition: ResearchDisposition
    uniqueness_disposition: ResearchDisposition
    reason: str
    thresholds_calibrated: bool = False
    specificity_claimed: bool = False
    candidate_only: bool = True

    @property
    def accepted_modes(self) -> tuple[KnownPilotModeCandidate, ...]:
        return tuple(
            mode
            for mode in self.retained_modes
            if mode.decision is ResearchEvidenceDecision.CANDIDATE
        )

    @property
    def winner(self) -> KnownPilotModeCandidate | None:
        return self.accepted_modes[0] if self.accepted_modes else None


@dataclass(frozen=True, slots=True)
class _Proposal:
    epoch_sample: int
    absolute_cfo_hz: float
    trajectory_reference_epoch_sample: int
    trajectory_reference_absolute_cfo_hz: float
    block_epoch_samples: tuple[int, ...]
    block_absolute_cfo_hz: tuple[float, ...]
    acquire_score: float
    block_scores: tuple[float, ...]
    block_support: tuple[int, ...]
    trajectory_epoch_span_samples: int
    trajectory_max_adjacent_epoch_step_samples: int
    trajectory_epoch_dispersion_samples: float
    trajectory_epoch_fit_rms_samples: float
    trajectory_timing_rate_samples_s: float
    trajectory_cfo_span_hz: float
    trajectory_cfo_dispersion_hz: float
    trajectory_cfo_fit_rms_hz: float
    trajectory_cfo_rate_residual_hz_s: float
    trajectory_path_sha256: str
    trajectory_admissible: bool
    trajectory_path_evaluated_count: int
    trajectory_path_limit_truncated_count: int


def acquire_seeded_known_pilot_modes(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    seed: KnownPilotModeSeed,
    additional_seeds: tuple[KnownPilotModeSeed, ...] = (),
    edge: StarlinkEdge | str,
    expected_symbol_roll: int = 0,
    config: SeededPilotAcquisitionConfig | None = None,
) -> SeededPilotAcquisitionResult:
    """Evaluate a protected trajectory seed on repeated held-out pilot blocks.

    The search first evaluates a bounded local component and always retains the
    exact supplied seed.  Only when that component has no accepted mode may one
    bounded global exact-template fallback propose alternatives.  Both stages
    use even Qin symbols for proposal scoring and odd Qin symbols for
    verification.  Conditional rolls are evaluated only at the exact
    candidate's epoch/CFO and on the same absolute verification samples; they
    are never independently reacquired.
    """

    values = np.asarray(samples, dtype=np.complex128)
    settings = config or SeededPilotAcquisitionConfig()
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if values.size > settings.maximum_sample_count:
        raise ValueError("seeded acquisition exceeds maximum_sample_count")
    if not np.all(np.isfinite(values)):
        raise ValueError("seeded-acquisition samples must be finite")
    if isinstance(expected_symbol_roll, bool) or not isinstance(expected_symbol_roll, int):
        raise ValueError("expected_symbol_roll must be an integer")
    if expected_symbol_roll % 300 in tuple(value % 300 for value in settings.control_symbol_rolls):
        raise ValueError("expected pilot cannot also appear in the conditional control bank")
    if not isinstance(additional_seeds, tuple) or any(
        not isinstance(item, KnownPilotModeSeed) for item in additional_seeds
    ):
        raise ValueError("additional_seeds must be a tuple of KnownPilotModeSeed values")
    if len(additional_seeds) > settings.maximum_additional_seed_count:
        raise ValueError("additional seed count exceeds the configured bound")
    seed_keys = tuple(
        (item.branch_id, item.provenance_sha256) for item in (seed, *additional_seeds)
    )
    if len(set(seed_keys)) != len(seed_keys):
        raise ValueError("seed branch/provenance identities must be unique")
    if additional_seeds:
        results = tuple(
            acquire_seeded_known_pilot_modes(
                values,
                sample_rate_hz,
                seed=item,
                edge=selected_edge,
                expected_symbol_roll=expected_symbol_roll,
                config=settings,
            )
            for item in (seed, *additional_seeds)
        )
        return _merge_seed_results(
            results,
            seed,
            additional_seeds,
            settings,
        )

    (
        exact_template,
        control_templates,
        diagnostic_control_templates,
        exact_template_identity,
        conditional_control_template_identities,
        diagnostic_control_template_identities,
    ) = _template_bank(
        sample_rate_hz,
        selected_edge,
        expected_symbol_roll,
        settings.control_symbol_rolls,
    )

    period = sample_rate_hz / FRAME_RATE_HZ
    epoch_count = math.ceil(period)
    block_length = round(settings.block_duration_s * sample_rate_hz)
    if block_length < 1 or values.size < block_length:
        return _insufficient_result(
            seed,
            selected_edge,
            expected_symbol_roll,
            settings,
            sample_rate_hz,
            values.size,
            period,
            "window is shorter than one configured short block",
            exact_template_identity,
            conditional_control_template_identities,
            diagnostic_control_template_identities,
        )
    block_starts = _evenly_spaced_block_starts(
        values.size,
        block_length,
        settings.block_count,
    )
    if len(set(block_starts)) != settings.block_count:
        return _insufficient_result(
            seed,
            selected_edge,
            expected_symbol_roll,
            settings,
            sample_rate_hz,
            values.size,
            period,
            "window cannot place the configured number of distinct short blocks",
            exact_template_identity,
            conditional_control_template_identities,
            diagnostic_control_template_identities,
        )
    nominal_epoch = seed.nominal_epoch_sample % epoch_count
    epochs = _local_epochs(
        nominal_epoch,
        settings.local_epoch_radius_samples,
        epoch_count,
    )
    cfo_grid = _centered_grid(
        seed.nominal_absolute_cfo_hz,
        settings.local_cfo_radius_hz,
        settings.local_cfo_step_hz,
    )
    blocks = tuple((start, start + block_length) for start in block_starts)
    (
        proposals,
        local_block_score_count,
        trajectory_path_evaluated_count,
        trajectory_path_truncated_count,
    ) = _score_proposals(
        values,
        exact_template,
        sample_rate_hz,
        tuple((epoch, cfo_hz) for epoch in epochs for cfo_hz in cfo_grid),
        tuple((epoch, cfo_hz) for epoch in epochs for cfo_hz in cfo_grid),
        seed.nominal_doppler_rate_hz_s,
        blocks,
        settings.minimum_frame_support_per_block,
        epoch_count,
        settings,
    )
    retained, suppressed_count, truncated_count = _retain_proposals(
        proposals,
        nominal_epoch,
        seed.nominal_absolute_cfo_hz,
        epoch_count,
        settings,
    )
    adjudicated_modes = tuple(
        _adjudicate_proposal(
            proposal,
            values,
            exact_template,
            control_templates,
            diagnostic_control_templates,
            sample_rate_hz,
            seed,
            nominal_epoch,
            blocks,
            settings,
        )
        for proposal in retained
    )
    (
        local_modes,
        whole_window_rescore_candidate_count,
        whole_window_rescore_template_score_count,
    ) = _rescore_candidate_modes_on_whole_window(
        adjudicated_modes,
        values,
        exact_template,
        control_templates,
        diagnostic_control_templates,
        sample_rate_hz,
        settings,
    )
    local_modes = _mark_one_local_component_representative(
        local_modes,
        nominal_epoch,
        seed.nominal_absolute_cfo_hz,
        epoch_count,
    )
    global_fallback_attempted = settings.global_fallback_enabled and not any(
        mode.decision is ResearchEvidenceDecision.CANDIDATE for mode in local_modes
    )
    proposal_block_start, proposal_block_stop = blocks[settings.global_proposal_block_index]
    global_proposal_sample_count = (
        proposal_block_stop - proposal_block_start if global_fallback_attempted else 0
    )
    global_proposal_symbol_count = (
        len(settings.global_proposal_symbols) if global_fallback_attempted else 0
    )
    global_proposal_frame_offset_count = (
        _frame_offset_count(global_proposal_sample_count, period)
        if global_fallback_attempted
        else 0
    )
    global_cfo_count = 0
    global_grid_count = 0
    global_peak_count = 0
    global_block_score_count = 0
    global_trajectory_path_evaluated_count = 0
    global_trajectory_path_truncated_count = 0
    global_suppressed_count = 0
    global_truncated_count = 0
    global_modes: tuple[KnownPilotModeCandidate, ...] = ()
    if global_fallback_attempted:
        (
            global_proposals,
            global_cfo_count,
            global_grid_count,
            global_peak_count,
            global_block_score_count,
            global_trajectory_path_evaluated_count,
            global_trajectory_path_truncated_count,
            global_suppressed_count,
            global_truncated_count,
        ) = _global_fallback_proposals(
            values,
            exact_template,
            sample_rate_hz,
            seed,
            nominal_epoch,
            epoch_count,
            blocks,
            settings,
        )
        global_adjudicated = tuple(
            _adjudicate_proposal(
                proposal,
                values,
                exact_template,
                control_templates,
                diagnostic_control_templates,
                sample_rate_hz,
                seed,
                nominal_epoch,
                blocks,
                settings,
                proposal_origin=PilotModeProposalOrigin.GLOBAL_FALLBACK,
            )
            for proposal in global_proposals
        )
        (
            global_modes,
            global_rescore_count,
            global_rescore_template_count,
        ) = _rescore_candidate_modes_on_whole_window(
            global_adjudicated,
            values,
            exact_template,
            control_templates,
            diagnostic_control_templates,
            sample_rate_hz,
            settings,
        )
        global_modes = _mark_global_component_representatives(
            global_modes,
            epoch_count,
            settings,
        )
        whole_window_rescore_candidate_count += global_rescore_count
        whole_window_rescore_template_score_count += global_rescore_template_count
    modes = local_modes + global_modes
    ordered = sorted(
        modes,
        key=lambda mode: (
            mode.decision is ResearchEvidenceDecision.CANDIDATE,
            mode.median_verify_score,
            mode.acquire_score,
            -_circular_epoch_distance(mode.epoch_sample, nominal_epoch, epoch_count),
            -abs(mode.absolute_cfo_hz - seed.nominal_absolute_cfo_hz),
            -mode.epoch_sample,
            -mode.absolute_cfo_hz,
        ),
        reverse=True,
    )
    ranked = tuple(replace(mode, rank=index) for index, mode in enumerate(ordered, start=1))
    accepted = sum(mode.decision is ResearchEvidenceDecision.CANDIDATE for mode in ranked)
    (
        presence_disposition,
        code_specificity_disposition,
        cfo_alias_resolution_disposition,
        uniqueness_disposition,
    ) = _complete_dispositions(ranked, settings)
    return SeededPilotAcquisitionResult(
        status=NumericalStatus.COMPLETE,
        config_digest=settings.digest,
        seed=seed,
        additional_seeds=(),
        evaluated_seed_count=1,
        edge=selected_edge,
        expected_symbol_roll=expected_symbol_roll,
        control_symbol_rolls=settings.control_symbol_rolls,
        exact_template_identity=exact_template_identity,
        conditional_control_template_identities=conditional_control_template_identities,
        diagnostic_control_template_identities=diagnostic_control_template_identities,
        sample_rate_hz=float(sample_rate_hz),
        sample_count=values.size,
        frame_period_samples=float(period),
        block_starts=block_starts,
        searched_epoch_count=len(epochs),
        searched_cfo_count=len(cfo_grid),
        evaluated_grid_point_count=len(proposals),
        evaluated_block_score_count=local_block_score_count,
        trajectory_path_evaluated_count=trajectory_path_evaluated_count,
        trajectory_path_limit_truncated_count=trajectory_path_truncated_count,
        separation_suppressed_count=suppressed_count,
        candidate_limit_truncated_count=truncated_count,
        global_fallback_attempted=global_fallback_attempted,
        global_proposal_block_index=settings.global_proposal_block_index,
        global_proposal_block_start_sample=(
            proposal_block_start if global_fallback_attempted else None
        ),
        global_proposal_block_stop_sample=(
            proposal_block_stop if global_fallback_attempted else None
        ),
        global_proposal_sample_count=global_proposal_sample_count,
        global_proposal_symbol_count=global_proposal_symbol_count,
        global_proposal_frame_offset_count=global_proposal_frame_offset_count,
        global_searched_epoch_count=epoch_count if global_fallback_attempted else 0,
        global_searched_cfo_count=global_cfo_count,
        global_evaluated_grid_point_count=global_grid_count,
        global_peak_count=global_peak_count,
        global_evaluated_block_score_count=global_block_score_count,
        global_trajectory_path_evaluated_count=global_trajectory_path_evaluated_count,
        global_trajectory_path_limit_truncated_count=global_trajectory_path_truncated_count,
        global_separation_suppressed_count=global_suppressed_count,
        global_candidate_limit_truncated_count=global_truncated_count,
        whole_window_rescore_candidate_count=whole_window_rescore_candidate_count,
        whole_window_rescore_template_score_count=whole_window_rescore_template_score_count,
        retained_modes=ranked,
        presence_disposition=presence_disposition,
        code_specificity_disposition=code_specificity_disposition,
        cfo_alias_resolution_disposition=cfo_alias_resolution_disposition,
        uniqueness_disposition=uniqueness_disposition,
        reason=(
            f"bounded seeded acquisition returned {accepted} uncalibrated research candidate(s)"
            if accepted
            else (
                "exact-pilot presence evidence remained code-specificity ambiguous; "
                "no tracking candidate was admitted"
                if presence_disposition is ResearchDisposition.UNCALIBRATED_CANDIDATE
                else (
                    "bounded seeded acquisition completed; no mode passed "
                    "uncalibrated research gates"
                )
            )
        ),
    )


def canonicalize_cfo_alias(absolute_cfo_hz: float) -> tuple[float, int]:
    """Return a deterministic CFO representative and OFDM-symbol alias lift."""

    if not math.isfinite(absolute_cfo_hz):
        raise ValueError("CFO alias input must be finite")
    lift = math.floor((absolute_cfo_hz + 0.5 * CFO_ALIAS_SPACING_HZ) / CFO_ALIAS_SPACING_HZ)
    canonical = float(absolute_cfo_hz - lift * CFO_ALIAS_SPACING_HZ)
    if math.isclose(canonical, 0.0, rel_tol=0.0, abs_tol=1e-12):
        canonical = 0.0
    return canonical, int(lift)


def _template_bank(
    sample_rate_hz: float,
    edge: StarlinkEdge,
    expected_symbol_roll: int,
    conditional_rolls: tuple[int, ...],
) -> tuple[
    np.ndarray,
    tuple[np.ndarray, ...],
    tuple[np.ndarray, ...],
    PilotTemplateIdentity,
    tuple[PilotTemplateIdentity, ...],
    tuple[PilotTemplateIdentity, ...],
]:
    exact_payload = qin_edge_pilot_frame(
        sample_rate_hz,
        edge,
        symbol_roll=expected_symbol_roll,
    )
    conditional_payloads = tuple(
        qin_edge_pilot_frame(sample_rate_hz, edge, symbol_roll=roll) for roll in conditional_rolls
    )
    diagnostic_payloads = _orbit_breaking_control_payloads(sample_rate_hz, edge)
    exact_identity = PilotTemplateIdentity(
        label=f"qin-{edge.value}-scalar-roll-{expected_symbol_roll % 300}-expected-v1",
        template_sha256=template_sha256(exact_payload),
        role=TemplateEvidenceRole.EXPECTED,
        gates_research_decision=True,
        independently_reacquired=True,
    )
    conditional_identities = tuple(
        PilotTemplateIdentity(
            label=f"qin-{edge.value}-scalar-roll-{roll % 300}-conditional-v1",
            template_sha256=template_sha256(payload),
            role=TemplateEvidenceRole.CONDITIONAL_GATE,
            gates_research_decision=True,
            independently_reacquired=False,
        )
        for roll, payload in zip(conditional_rolls, conditional_payloads, strict=True)
    )
    opposite = StarlinkEdge.UPPER if edge is StarlinkEdge.LOWER else StarlinkEdge.LOWER
    diagnostic_identities = (
        PilotTemplateIdentity(
            label=(f"qin-{edge.value}-per-subcarrier-roll-derangement-v1"),
            template_sha256=template_sha256(diagnostic_payloads[0]),
            role=TemplateEvidenceRole.ORBIT_BREAKING_DIAGNOSTIC,
            gates_research_decision=False,
            independently_reacquired=False,
        ),
        PilotTemplateIdentity(
            label=f"qin-{opposite.value}-states-on-{edge.value}-tones-v1",
            template_sha256=template_sha256(diagnostic_payloads[1]),
            role=TemplateEvidenceRole.ORBIT_BREAKING_DIAGNOSTIC,
            gates_research_decision=False,
            independently_reacquired=False,
        ),
    )
    return (
        np.asarray(exact_payload, dtype=np.complex128),
        tuple(np.asarray(payload, dtype=np.complex128) for payload in conditional_payloads),
        tuple(np.asarray(payload, dtype=np.complex128) for payload in diagnostic_payloads),
        exact_identity,
        conditional_identities,
        diagnostic_identities,
    )


@lru_cache(maxsize=32)
def _orbit_breaking_control_payloads(
    sample_rate_hz: float,
    edge: StarlinkEdge,
) -> tuple[np.ndarray, np.ndarray]:
    source = qin_edge_pilot_symbols(edge)
    deranged = np.empty_like(source)
    for row in range(source.shape[0]):
        for column, roll in enumerate(PER_SUBCARRIER_DERANGEMENT_ROLLS):
            deranged[row, column] = source[(row - roll) % source.shape[0], column]
    opposite = StarlinkEdge.UPPER if edge is StarlinkEdge.LOWER else StarlinkEdge.LOWER
    output = (
        _sample_symbol_matrix_on_edge_tones(sample_rate_hz, edge, deranged),
        _sample_symbol_matrix_on_edge_tones(
            sample_rate_hz,
            edge,
            qin_edge_pilot_symbols(opposite),
        ),
    )
    for payload in output:
        payload.flags.writeable = False
    return output


def _sample_symbol_matrix_on_edge_tones(
    sample_rate_hz: float,
    edge: StarlinkEdge,
    symbols: np.ndarray,
) -> np.ndarray:
    """Sample supplied 300x8 Qin states on the selected edge frequencies."""

    if symbols.shape != (300, 8):
        raise ValueError("Qin control symbol matrix must have shape 300 by 8")
    count = round(sample_rate_hz / FRAME_RATE_HZ)
    time_s = np.arange(count, dtype=float) / sample_rate_hz
    symbol_index = np.floor(time_s / OFDM_SYMBOL_DURATION_S).astype(int)
    frequencies_hz = edge_frequencies_hz(edge)
    output = np.zeros(count, dtype=np.complex64)
    for index in range(2, 302):
        selected = np.flatnonzero(symbol_index == index)
        if not selected.size:
            continue
        local_time_s = time_s[selected] - index * OFDM_SYMBOL_DURATION_S
        values = np.zeros(selected.size, dtype=np.complex128)
        for column, frequency_hz in enumerate(frequencies_hz):
            values += symbols[index - 2, column] * np.exp(
                2j * np.pi * frequency_hz * (local_time_s - CYCLIC_PREFIX_DURATION_S)
            )
        output[selected] = values / math.sqrt(8)
    return output


def _complete_dispositions(
    modes: tuple[KnownPilotModeCandidate, ...],
    settings: SeededPilotAcquisitionConfig,
) -> tuple[
    ResearchDisposition,
    ResearchDisposition,
    ResearchDisposition,
    ResearchDisposition,
]:
    accepted_count = sum(mode.decision is ResearchEvidenceDecision.CANDIDATE for mode in modes)
    presence_supported = any(_has_uncalibrated_presence_evidence(mode, settings) for mode in modes)
    if accepted_count == 0 and presence_supported:
        return (
            ResearchDisposition.UNCALIBRATED_CANDIDATE,
            ResearchDisposition.AMBIGUOUS,
            ResearchDisposition.UNASSESSED,
            ResearchDisposition.UNASSESSED,
        )
    if accepted_count == 0:
        return (
            ResearchDisposition.NO_RESEARCH_CANDIDATE,
            ResearchDisposition.UNASSESSED,
            ResearchDisposition.UNASSESSED,
            ResearchDisposition.UNASSESSED,
        )
    return (
        ResearchDisposition.UNCALIBRATED_CANDIDATE,
        ResearchDisposition.AMBIGUOUS,
        ResearchDisposition.UNRESOLVED,
        (ResearchDisposition.AMBIGUOUS if accepted_count > 1 else ResearchDisposition.UNRESOLVED),
    )


def _has_uncalibrated_presence_evidence(
    mode: KnownPilotModeCandidate,
    settings: SeededPilotAcquisitionConfig,
) -> bool:
    """Separate exact-pilot presence support from conditional-code specificity."""

    supported = tuple(
        block
        for block in mode.blocks
        if min(block.acquire_frame_support, block.verify_frame_support)
        >= settings.minimum_frame_support_per_block
        and block.verify_score >= settings.minimum_exact_score
    )
    return (
        len(supported) >= settings.minimum_consensus_blocks
        and float(np.median(tuple(block.verify_score for block in supported)))
        >= settings.minimum_exact_score
        and mode.trajectory_admissible
    )


def _merge_seed_results(
    results: tuple[SeededPilotAcquisitionResult, ...],
    primary_seed: KnownPilotModeSeed,
    additional_seeds: tuple[KnownPilotModeSeed, ...],
    settings: SeededPilotAcquisitionConfig,
) -> SeededPilotAcquisitionResult:
    """Merge independently protected seed inventories without hiding provenance."""

    base = results[0]
    if any(
        result.config_digest != base.config_digest
        or result.edge is not base.edge
        or result.expected_symbol_roll != base.expected_symbol_roll
        for result in results[1:]
    ):
        raise ValueError("seed-set acquisition results do not share one configuration")
    modes = tuple(
        replace(mode, source_seed_index=seed_index)
        for seed_index, result in enumerate(results)
        for mode in result.retained_modes
    )
    modes = _collapse_same_epoch_cfo_alias_duplicates(modes, settings)
    ordered = sorted(
        modes,
        key=lambda mode: (
            -(mode.decision is ResearchEvidenceDecision.CANDIDATE),
            -(
                mode.whole_window_verify_score
                if mode.whole_window_verify_score is not None
                else -math.inf
            ),
            -mode.median_verify_score,
            -mode.acquire_score,
            mode.epoch_sample,
            mode.canonical_cfo_hz,
            mode.source_seed_index,
            mode.source_branch_id,
            mode.source_provenance_sha256,
        ),
    )
    ranked = tuple(replace(mode, rank=index) for index, mode in enumerate(ordered, start=1))
    accepted_count = sum(mode.decision is ResearchEvidenceDecision.CANDIDATE for mode in ranked)
    alias_duplicate_count = sum(
        mode.decision is ResearchEvidenceDecision.ALIAS_DUPLICATE for mode in ranked
    )
    if base.status is NumericalStatus.INSUFFICIENT:
        dispositions = (ResearchDisposition.INSUFFICIENT,) * 4
    else:
        dispositions = _complete_dispositions(ranked, settings)
        if alias_duplicate_count:
            dispositions = (
                dispositions[0],
                dispositions[1],
                ResearchDisposition.AMBIGUOUS,
                dispositions[3],
            )
    fallback_results = tuple(result for result in results if result.global_fallback_attempted)
    if fallback_results and any(
        result.global_proposal_block_start_sample
        != fallback_results[0].global_proposal_block_start_sample
        or result.global_proposal_block_stop_sample
        != fallback_results[0].global_proposal_block_stop_sample
        for result in fallback_results[1:]
    ):
        raise ValueError("seed-set global proposal spans differ")
    return replace(
        base,
        seed=primary_seed,
        additional_seeds=additional_seeds,
        evaluated_seed_count=len(results),
        searched_epoch_count=sum(result.searched_epoch_count for result in results),
        searched_cfo_count=sum(result.searched_cfo_count for result in results),
        evaluated_grid_point_count=sum(result.evaluated_grid_point_count for result in results),
        evaluated_block_score_count=sum(result.evaluated_block_score_count for result in results),
        trajectory_path_evaluated_count=sum(
            result.trajectory_path_evaluated_count for result in results
        ),
        trajectory_path_limit_truncated_count=sum(
            result.trajectory_path_limit_truncated_count for result in results
        ),
        separation_suppressed_count=sum(result.separation_suppressed_count for result in results),
        candidate_limit_truncated_count=sum(
            result.candidate_limit_truncated_count for result in results
        ),
        global_fallback_attempted=any(result.global_fallback_attempted for result in results),
        global_proposal_block_start_sample=(
            fallback_results[0].global_proposal_block_start_sample if fallback_results else None
        ),
        global_proposal_block_stop_sample=(
            fallback_results[0].global_proposal_block_stop_sample if fallback_results else None
        ),
        global_proposal_sample_count=sum(result.global_proposal_sample_count for result in results),
        global_proposal_symbol_count=sum(result.global_proposal_symbol_count for result in results),
        global_proposal_frame_offset_count=sum(
            result.global_proposal_frame_offset_count for result in results
        ),
        global_searched_epoch_count=sum(result.global_searched_epoch_count for result in results),
        global_searched_cfo_count=sum(result.global_searched_cfo_count for result in results),
        global_evaluated_grid_point_count=sum(
            result.global_evaluated_grid_point_count for result in results
        ),
        global_peak_count=sum(result.global_peak_count for result in results),
        global_evaluated_block_score_count=sum(
            result.global_evaluated_block_score_count for result in results
        ),
        global_trajectory_path_evaluated_count=sum(
            result.global_trajectory_path_evaluated_count for result in results
        ),
        global_trajectory_path_limit_truncated_count=sum(
            result.global_trajectory_path_limit_truncated_count for result in results
        ),
        global_separation_suppressed_count=sum(
            result.global_separation_suppressed_count for result in results
        ),
        global_candidate_limit_truncated_count=sum(
            result.global_candidate_limit_truncated_count for result in results
        ),
        whole_window_rescore_candidate_count=sum(
            result.whole_window_rescore_candidate_count for result in results
        ),
        whole_window_rescore_template_score_count=sum(
            result.whole_window_rescore_template_score_count for result in results
        ),
        retained_modes=ranked,
        presence_disposition=dispositions[0],
        code_specificity_disposition=dispositions[1],
        cfo_alias_resolution_disposition=dispositions[2],
        uniqueness_disposition=dispositions[3],
        reason=(
            f"{len(results)} protected seed families returned {accepted_count} "
            f"uncalibrated component(s); {alias_duplicate_count} CFO alias duplicate(s)"
        ),
    )


def _collapse_same_epoch_cfo_alias_duplicates(
    modes: tuple[KnownPilotModeCandidate, ...],
    settings: SeededPilotAcquisitionConfig,
) -> tuple[KnownPilotModeCandidate, ...]:
    admitted = sorted(
        (mode for mode in modes if mode.decision is ResearchEvidenceDecision.CANDIDATE),
        key=lambda mode: (
            -(
                mode.whole_window_verify_score
                if mode.whole_window_verify_score is not None
                else -math.inf
            ),
            -mode.median_verify_score,
            -mode.acquire_score,
            mode.source_seed_index,
            mode.source_branch_id,
        ),
    )
    representatives: list[KnownPilotModeCandidate] = []
    duplicate_ids: set[int] = set()
    for mode in admitted:
        if any(
            _full_trajectory_is_one_cfo_alias(mode, other, settings) for other in representatives
        ):
            duplicate_ids.add(id(mode))
        else:
            representatives.append(mode)
    return tuple(
        replace(mode, decision=ResearchEvidenceDecision.ALIAS_DUPLICATE)
        if id(mode) in duplicate_ids
        else mode
        for mode in modes
    )


def _full_trajectory_is_one_cfo_alias(
    left: KnownPilotModeCandidate,
    right: KnownPilotModeCandidate,
    settings: SeededPilotAcquisitionConfig,
) -> bool:
    """Require timing and rate compatibility before collapsing a CFO alias lift."""

    if left.epoch_sample != right.epoch_sample or len(left.blocks) != len(right.blocks):
        return False
    if (
        abs(left.doppler_rate_hz_s - right.doppler_rate_hz_s)
        > settings.cfo_alias_rate_tolerance_hz_s
    ):
        return False
    if any(
        abs(left_residual - right_residual) > settings.cfo_alias_timing_tolerance_samples
        for left_residual, right_residual in zip(
            left.trajectory_block_epoch_residual_samples,
            right.trajectory_block_epoch_residual_samples,
            strict=True,
        )
    ):
        return False
    lifts: list[int] = []
    for left_cfo_hz, right_cfo_hz in zip(
        left.trajectory_block_absolute_cfo_hz,
        right.trajectory_block_absolute_cfo_hz,
        strict=True,
    ):
        difference_hz = left_cfo_hz - right_cfo_hz
        lift = round(difference_hz / CFO_ALIAS_SPACING_HZ)
        residual_hz = difference_hz - lift * CFO_ALIAS_SPACING_HZ
        if abs(residual_hz) > settings.cfo_alias_equivalence_tolerance_hz:
            return False
        lifts.append(lift)
    return bool(lifts) and len(set(lifts)) == 1


def _cfo_alias_distance_hz(left_hz: float, right_hz: float) -> float:
    difference = left_hz - right_hz
    return abs(difference - round(difference / CFO_ALIAS_SPACING_HZ) * CFO_ALIAS_SPACING_HZ)


def _mark_one_local_component_representative(
    modes: tuple[KnownPilotModeCandidate, ...],
    nominal_epoch: int,
    nominal_cfo_hz: float,
    epoch_count: int,
) -> tuple[KnownPilotModeCandidate, ...]:
    """Collapse the bounded local grid to one publishable component."""

    admitted = tuple(mode for mode in modes if mode.decision is ResearchEvidenceDecision.CANDIDATE)
    if len(admitted) <= 1:
        return modes
    representative = max(
        admitted,
        key=lambda mode: (
            mode.whole_window_consistent_with_blocks,
            mode.whole_window_verify_score
            if mode.whole_window_verify_score is not None
            else -math.inf,
            mode.whole_window_exact_minus_control_margin
            if mode.whole_window_exact_minus_control_margin is not None
            else -math.inf,
            mode.median_verify_score,
            mode.acquire_score,
            -_circular_epoch_distance(mode.epoch_sample, nominal_epoch, epoch_count),
            -abs(mode.absolute_cfo_hz - nominal_cfo_hz),
            -mode.epoch_sample,
            -mode.absolute_cfo_hz,
        ),
    )
    return tuple(
        mode
        if mode is representative or mode.decision is not ResearchEvidenceDecision.CANDIDATE
        else replace(mode, decision=ResearchEvidenceDecision.REDUNDANT_LOCAL_PROPOSAL)
        for mode in modes
    )


def _rescore_candidate_modes_on_whole_window(
    modes: tuple[KnownPilotModeCandidate, ...],
    values: np.ndarray,
    exact_template: np.ndarray,
    control_templates: tuple[np.ndarray, ...],
    diagnostic_control_templates: tuple[np.ndarray, ...],
    sample_rate_hz: float,
    settings: SeededPilotAcquisitionConfig,
) -> tuple[tuple[KnownPilotModeCandidate, ...], int, int]:
    """Require each block-admitted mode to survive a rate-aware odd-Qin replay."""

    output = []
    candidate_count = 0
    for mode in modes:
        if mode.decision is not ResearchEvidenceDecision.CANDIDATE:
            output.append(mode)
            continue
        candidate_count += 1
        exact_score, exact_support = _normalized_rate_aware_window_score(
            values,
            exact_template,
            sample_rate_hz,
            mode.epoch_sample,
            mode.absolute_cfo_hz,
            mode.doppler_rate_hz_s,
            DEFAULT_VERIFY_SYMBOLS,
            tuple(0.5 * (block.start_sample + block.stop_sample) for block in mode.blocks),
            mode.trajectory_block_epoch_residual_samples,
            mode.trajectory_block_cfo_residual_hz,
        )
        control_rows = tuple(
            _normalized_rate_aware_window_score(
                values,
                template,
                sample_rate_hz,
                mode.epoch_sample,
                mode.absolute_cfo_hz,
                mode.doppler_rate_hz_s,
                DEFAULT_VERIFY_SYMBOLS,
                tuple(0.5 * (block.start_sample + block.stop_sample) for block in mode.blocks),
                mode.trajectory_block_epoch_residual_samples,
                mode.trajectory_block_cfo_residual_hz,
            )
            for template in control_templates
        )
        diagnostic_rows = tuple(
            _normalized_rate_aware_window_score(
                values,
                template,
                sample_rate_hz,
                mode.epoch_sample,
                mode.absolute_cfo_hz,
                mode.doppler_rate_hz_s,
                DEFAULT_VERIFY_SYMBOLS,
                tuple(0.5 * (block.start_sample + block.stop_sample) for block in mode.blocks),
                mode.trajectory_block_epoch_residual_samples,
                mode.trajectory_block_cfo_residual_hz,
            )
            for template in diagnostic_control_templates
        )
        control_scores = tuple(row[0] for row in control_rows)
        diagnostic_scores = tuple(row[0] for row in diagnostic_rows)
        support = min(
            (exact_support, *(row[1] for row in control_rows)),
            default=0,
        )
        margin = exact_score - max(control_scores, default=0.0)
        consistent = (
            support >= settings.minimum_frame_support_per_block * settings.minimum_consensus_blocks
            and exact_score >= settings.minimum_exact_score
            and margin >= settings.minimum_exact_minus_control_margin
        )
        output.append(
            replace(
                mode,
                whole_window_verify_score=float(exact_score),
                whole_window_control_scores=control_scores,
                whole_window_diagnostic_control_scores=diagnostic_scores,
                whole_window_exact_minus_control_margin=float(margin),
                whole_window_frame_support=support,
                whole_window_consistent_with_blocks=consistent,
                decision=(
                    mode.decision
                    if consistent
                    else ResearchEvidenceDecision.WHOLE_WINDOW_INCONSISTENT
                ),
            )
        )
    template_count = 1 + len(control_templates) + len(diagnostic_control_templates)
    return tuple(output), candidate_count, candidate_count * template_count


def _normalized_rate_aware_window_score(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: float,
    doppler_rate_hz_s: float,
    symbols: tuple[int, ...],
    block_center_samples: tuple[float, ...],
    block_epoch_residual_samples: tuple[int, ...],
    block_cfo_residual_hz: tuple[float, ...],
) -> tuple[float, int]:
    """Replay a prefit even-Qin timing/CFO path on held-out odd symbols."""

    sample_indexes = _pilot_sample_indexes(sample_rate_hz, symbols)
    references = template[sample_indexes]
    template_energy = float(np.vdot(references, references).real)
    period = sample_rate_hz / FRAME_RATE_HZ
    scores = []
    frame_index = 0
    while True:
        nominal_frame_start = epoch_sample + round(frame_index * period)
        epoch_residual = _interpolate_prefit_path(
            nominal_frame_start,
            block_center_samples,
            tuple(float(value) for value in block_epoch_residual_samples),
        )
        frame_start = epoch_sample + round(frame_index * period + epoch_residual)
        absolute = frame_start + sample_indexes
        if absolute[0] < 0:
            frame_index += 1
            continue
        if absolute[-1] >= values.size:
            break
        time_s = absolute / sample_rate_hz
        cfo_residual_hz = _interpolate_prefit_path(
            frame_start,
            block_center_samples,
            block_cfo_residual_hz,
        )
        rotation = np.exp(
            -2j * np.pi * (absolute_cfo_hz * time_s + 0.5 * doppler_rate_hz_s * time_s**2)
            - 2j * np.pi * cfo_residual_hz * sample_indexes / sample_rate_hz
        )
        received = values[absolute]
        denominator = math.sqrt(template_energy * float(np.vdot(received, received).real))
        scores.append(
            float(abs(np.vdot(references, received * rotation)) / denominator)
            if denominator
            else 0.0
        )
        frame_index += 1
    return (float(np.mean(scores)) if scores else 0.0, len(scores))


def _interpolate_prefit_path(
    sample: float,
    block_center_samples: tuple[float, ...],
    values: tuple[float, ...],
) -> float:
    if len(block_center_samples) != len(values) or not values:
        raise ValueError("trajectory path coordinates must be nonempty and aligned")
    return float(np.interp(sample, block_center_samples, values))


def _global_fallback_proposals(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    seed: KnownPilotModeSeed,
    nominal_epoch: int,
    epoch_count: int,
    blocks: tuple[tuple[int, int], ...],
    settings: SeededPilotAcquisitionConfig,
) -> tuple[tuple[_Proposal, ...], int, int, int, int, int, int, int, int]:
    """Propose global peaks on one declared block before full evidence replay."""

    cfo_grid = _centered_grid(
        seed.nominal_absolute_cfo_hz,
        settings.global_cfo_radius_hz,
        settings.global_cfo_step_hz,
    )
    proposal_start, proposal_stop = blocks[settings.global_proposal_block_index]
    if proposal_start != 0:
        raise RuntimeError("global proposal block must remain capture-relative block zero")
    search_values = values[proposal_start:proposal_stop]
    if seed.nominal_doppler_rate_hz_s != 0.0:
        time_s = np.arange(proposal_start, proposal_stop, dtype=float) / sample_rate_hz
        search_values = search_values * np.exp(
            -1j * np.pi * seed.nominal_doppler_rate_hz_s * time_s**2
        )
    score_rows = _folded_anchor_score_grid(
        search_values,
        template,
        sample_rate_hz,
        cfo_grid,
        settings.global_proposal_symbols,
        epoch_count,
    )
    peaks = sorted(
        (
            (float(scores[epoch]), epoch, float(cfo_hz))
            for cfo_hz, scores in zip(cfo_grid, score_rows, strict=True)
            for epoch in _circular_local_peak_indexes(scores)
            if math.isfinite(float(scores[epoch])) and scores[epoch] > 0.0
        ),
        key=lambda item: (
            item[0],
            -_circular_epoch_distance(item[1], nominal_epoch, epoch_count),
            -abs(item[2] - seed.nominal_absolute_cfo_hz),
            -item[1],
            -item[2],
        ),
        reverse=True,
    )
    retained_peaks: list[tuple[float, int, float]] = []
    suppressed = 0
    truncated = 0
    for peak in peaks:
        _, epoch, cfo_hz = peak
        inside_local_search = (
            _circular_epoch_distance(epoch, nominal_epoch, epoch_count)
            <= settings.local_epoch_radius_samples
            and abs(cfo_hz - seed.nominal_absolute_cfo_hz) <= settings.local_cfo_radius_hz
        )
        separated = all(
            _circular_epoch_distance(epoch, other_epoch, epoch_count)
            >= settings.global_candidate_epoch_separation_samples
            or abs(cfo_hz - other_cfo_hz) > settings.global_candidate_cfo_separation_hz
            for _, other_epoch, other_cfo_hz in retained_peaks
        )
        if inside_local_search or not separated:
            suppressed += 1
        elif len(retained_peaks) < settings.global_retained_candidate_count:
            retained_peaks.append(peak)
        else:
            truncated += 1
    anchors = tuple((epoch, cfo_hz) for _, epoch, cfo_hz in retained_peaks)
    refinement_coordinates = tuple(
        sorted(
            {
                ((epoch + offset) % epoch_count, cfo_hz)
                for epoch, anchor_cfo_hz in anchors
                for offset in range(
                    -settings.trajectory_epoch_radius_samples,
                    settings.trajectory_epoch_radius_samples + 1,
                )
                for cfo_hz in cfo_grid
                if abs(cfo_hz - anchor_cfo_hz) <= settings.trajectory_cfo_radius_hz
            }
        )
    )
    (
        proposals,
        block_score_count,
        trajectory_path_count,
        trajectory_path_truncated_count,
    ) = _score_proposals(
        values,
        template,
        sample_rate_hz,
        anchors,
        refinement_coordinates,
        seed.nominal_doppler_rate_hz_s,
        blocks,
        settings.minimum_frame_support_per_block,
        epoch_count,
        settings,
    )
    return (
        proposals,
        len(cfo_grid),
        epoch_count * len(cfo_grid),
        len(peaks),
        block_score_count,
        trajectory_path_count,
        trajectory_path_truncated_count,
        suppressed,
        truncated,
    )


def _mark_global_component_representatives(
    modes: tuple[KnownPilotModeCandidate, ...],
    epoch_count: int,
    settings: SeededPilotAcquisitionConfig,
) -> tuple[KnownPilotModeCandidate, ...]:
    """Keep the strongest held-out representative of each nearby global mode."""

    ordered = sorted(
        (mode for mode in modes if mode.decision is ResearchEvidenceDecision.CANDIDATE),
        key=lambda mode: (
            mode.whole_window_consistent_with_blocks,
            mode.whole_window_verify_score
            if mode.whole_window_verify_score is not None
            else -math.inf,
            mode.whole_window_exact_minus_control_margin
            if mode.whole_window_exact_minus_control_margin is not None
            else -math.inf,
            mode.median_verify_score,
            mode.acquire_score,
            -mode.epoch_sample,
            -mode.absolute_cfo_hz,
        ),
        reverse=True,
    )
    representatives: list[KnownPilotModeCandidate] = []
    redundant_ids: set[int] = set()
    for mode in ordered:
        if any(
            _circular_epoch_distance(mode.epoch_sample, other.epoch_sample, epoch_count)
            <= settings.global_component_epoch_tolerance_samples
            and abs(mode.absolute_cfo_hz - other.absolute_cfo_hz)
            <= settings.global_component_cfo_tolerance_hz
            for other in representatives
        ):
            redundant_ids.add(id(mode))
        else:
            representatives.append(mode)
    return tuple(
        replace(mode, decision=ResearchEvidenceDecision.REDUNDANT_GLOBAL_PROPOSAL)
        if id(mode) in redundant_ids
        else mode
        for mode in modes
    )


def _score_proposals(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    anchors: tuple[tuple[int, float], ...],
    coordinates: tuple[tuple[int, float], ...],
    doppler_rate_hz_s: float,
    blocks: tuple[tuple[int, int], ...],
    minimum_support: int,
    epoch_count: int,
    settings: SeededPilotAcquisitionConfig,
) -> tuple[tuple[_Proposal, ...], int, int, int]:
    """Score one cached even-Qin lattice and select bounded block-local paths."""

    if not anchors:
        return (), 0, 0, 0
    matrix: dict[tuple[int, int, float], tuple[float, int]] = {}
    for block_index, (start, stop) in enumerate(blocks):
        center_time_s = 0.5 * (start + stop) / sample_rate_hz
        for epoch_sample, base_cfo_hz in coordinates:
            block_cfo_hz = base_cfo_hz + doppler_rate_hz_s * center_time_s
            matrix[(block_index, epoch_sample, base_cfo_hz)] = _normalized_absolute_block_score(
                values,
                template,
                sample_rate_hz,
                epoch_sample,
                block_cfo_hz,
                DEFAULT_ACQUIRE_SYMBOLS,
                start,
                stop,
            )

    proposals: list[_Proposal] = []
    path_evaluated_count = 0
    path_truncated_count = 0
    block_centers_s = tuple(0.5 * (start + stop) / sample_rate_hz for start, stop in blocks)
    epoch_geometry_cache: dict[
        tuple[tuple[int, ...], int],
        tuple[int, tuple[int, ...], int, int, float],
    ] = {}
    for anchor_epoch, anchor_cfo_hz in anchors:
        choices: list[tuple[tuple[float, int, int, float], ...]] = []
        for block_index in range(len(blocks)):
            rows = [
                (
                    matrix[(block_index, epoch_sample, base_cfo_hz)][0],
                    matrix[(block_index, epoch_sample, base_cfo_hz)][1],
                    epoch_sample,
                    base_cfo_hz,
                )
                for epoch_sample, base_cfo_hz in coordinates
                if _circular_epoch_distance(epoch_sample, anchor_epoch, epoch_count)
                <= settings.trajectory_epoch_radius_samples
                and abs(base_cfo_hz - anchor_cfo_hz) <= settings.trajectory_cfo_radius_hz
            ]
            rows.sort(
                key=lambda row: (
                    row[1] >= minimum_support,
                    row[0],
                    -_circular_epoch_distance(row[2], anchor_epoch, epoch_count),
                    -abs(row[3] - anchor_cfo_hz),
                    -row[2],
                    -row[3],
                ),
                reverse=True,
            )
            anchor_row = next(
                row
                for row in rows
                if row[2] == anchor_epoch
                and math.isclose(row[3], anchor_cfo_hz, rel_tol=0.0, abs_tol=1e-12)
            )
            selected = list(rows[: settings.trajectory_candidates_per_block])
            if anchor_row not in selected:
                selected[-1] = anchor_row
            choices.append(tuple(selected))

        path_universe_count = math.prod(len(rows) for rows in choices)
        evaluated_limit = min(path_universe_count, settings.maximum_trajectory_path_count)
        path_truncated_count += path_universe_count - evaluated_limit
        best: (
            tuple[
                tuple[object, ...],
                tuple[tuple[float, int, int, float], ...],
                tuple[int, ...],
                tuple[float, ...],
                int,
            ]
            | None
        ) = None
        for path in islice(product(*choices), evaluated_limit):
            path_evaluated_count += 1
            epochs = tuple(row[2] for row in path)
            geometry_key = (epochs, anchor_epoch)
            geometry = epoch_geometry_cache.get(geometry_key)
            if geometry is None:
                reference_epoch = _circular_medoid_epoch(epochs, anchor_epoch, epoch_count)
                epoch_residuals = tuple(
                    _signed_circular_epoch_delta(epoch, reference_epoch, epoch_count)
                    for epoch in epochs
                )
                epoch_span = max(epoch_residuals) - min(epoch_residuals)
                maximum_adjacent_epoch_step = max(
                    (
                        abs(_signed_circular_epoch_delta(right, left, epoch_count))
                        for left, right in zip(epochs, epochs[1:], strict=False)
                    ),
                    default=0,
                )
                epoch_fit_rms, _ = _linear_fit_residual_metrics(
                    block_centers_s,
                    tuple(float(value) for value in epoch_residuals),
                )
                geometry = (
                    reference_epoch,
                    epoch_residuals,
                    epoch_span,
                    maximum_adjacent_epoch_step,
                    epoch_fit_rms,
                )
                epoch_geometry_cache[geometry_key] = geometry
            (
                reference_epoch,
                epoch_residuals,
                epoch_span,
                maximum_adjacent_epoch_step,
                epoch_fit_rms,
            ) = geometry
            base_cfos_hz = tuple(float(row[3]) for row in path)
            cfo_span_hz = max(base_cfos_hz) - min(base_cfos_hz)
            path_admissible = (
                epoch_span <= settings.maximum_trajectory_epoch_span_samples
                and maximum_adjacent_epoch_step
                <= settings.maximum_adjacent_trajectory_epoch_step_samples
                and epoch_fit_rms <= settings.maximum_trajectory_epoch_fit_rms_samples
                and cfo_span_hz <= settings.maximum_trajectory_cfo_span_hz
            )
            supported_scores = tuple(row[0] for row in path if row[1] >= minimum_support)
            aggregate = _small_median(supported_scores) if supported_scores else 0.0
            path_scores = tuple(float(row[0]) for row in path)
            path_key: tuple[object, ...] = (
                len(supported_scores),
                aggregate,
                _small_mean(path_scores),
                path_admissible,
                -epoch_span,
                -maximum_adjacent_epoch_step,
                -epoch_fit_rms,
                -cfo_span_hz,
                -sum(_circular_epoch_distance(row[2], anchor_epoch, epoch_count) for row in path),
                -sum(abs(row[3] - anchor_cfo_hz) for row in path),
                tuple((-row[2], -row[3]) for row in path),
            )
            candidate = (path_key, path, epoch_residuals, supported_scores, reference_epoch)
            if best is None or candidate[0] > best[0]:
                best = candidate
        if best is None:
            raise RuntimeError("trajectory path search produced no bounded path")
        _, path, epoch_residuals, supported_scores, reference_epoch = best
        base_cfos_hz = tuple(float(row[3]) for row in path)
        reference_cfo_hz = _linear_medoid(base_cfos_hz, anchor_cfo_hz)
        cfo_residuals_hz = tuple(value - reference_cfo_hz for value in base_cfos_hz)
        epoch_fit_rms, timing_rate = _linear_fit_residual_metrics(
            block_centers_s,
            tuple(float(value) for value in epoch_residuals),
        )
        cfo_fit_rms, cfo_rate_residual = _linear_fit_residual_metrics(
            block_centers_s,
            cfo_residuals_hz,
        )
        epoch_span = max(epoch_residuals) - min(epoch_residuals)
        maximum_adjacent_epoch_step = max(
            (
                abs(_signed_circular_epoch_delta(right, left, epoch_count))
                for left, right in zip(
                    tuple(row[2] for row in path),
                    tuple(row[2] for row in path)[1:],
                    strict=False,
                )
            ),
            default=0,
        )
        cfo_span_hz = max(base_cfos_hz) - min(base_cfos_hz)
        trajectory_admissible = (
            epoch_span <= settings.maximum_trajectory_epoch_span_samples
            and maximum_adjacent_epoch_step
            <= settings.maximum_adjacent_trajectory_epoch_step_samples
            and epoch_fit_rms <= settings.maximum_trajectory_epoch_fit_rms_samples
            and cfo_span_hz <= settings.maximum_trajectory_cfo_span_hz
        )
        block_absolute_cfos_hz = tuple(
            base_cfo_hz + doppler_rate_hz_s * center_time_s
            for base_cfo_hz, center_time_s in zip(base_cfos_hz, block_centers_s, strict=True)
        )
        path_digest = canonical_digest(
            {
                "block_centers_s": block_centers_s,
                "epoch_samples": tuple(row[2] for row in path),
                "base_cfo_hz": base_cfos_hz,
                "even_scores": tuple(float(row[0]) for row in path),
                "frame_support": tuple(int(row[1]) for row in path),
            }
        ).removeprefix("sha256:")
        proposals.append(
            _Proposal(
                epoch_sample=anchor_epoch,
                absolute_cfo_hz=float(anchor_cfo_hz),
                trajectory_reference_epoch_sample=reference_epoch,
                trajectory_reference_absolute_cfo_hz=reference_cfo_hz,
                block_epoch_samples=tuple(row[2] for row in path),
                block_absolute_cfo_hz=block_absolute_cfos_hz,
                acquire_score=(float(np.median(supported_scores)) if supported_scores else 0.0),
                block_scores=tuple(float(row[0]) for row in path),
                block_support=tuple(int(row[1]) for row in path),
                trajectory_epoch_span_samples=epoch_span,
                trajectory_max_adjacent_epoch_step_samples=(maximum_adjacent_epoch_step),
                trajectory_epoch_dispersion_samples=float(
                    np.median(np.abs(np.asarray(epoch_residuals, dtype=float)))
                ),
                trajectory_epoch_fit_rms_samples=epoch_fit_rms,
                trajectory_timing_rate_samples_s=timing_rate,
                trajectory_cfo_span_hz=cfo_span_hz,
                trajectory_cfo_dispersion_hz=float(
                    np.median(np.abs(np.asarray(cfo_residuals_hz, dtype=float)))
                ),
                trajectory_cfo_fit_rms_hz=cfo_fit_rms,
                trajectory_cfo_rate_residual_hz_s=cfo_rate_residual,
                trajectory_path_sha256=path_digest,
                trajectory_admissible=trajectory_admissible,
                trajectory_path_evaluated_count=evaluated_limit,
                trajectory_path_limit_truncated_count=(path_universe_count - evaluated_limit),
            )
        )
    return (
        tuple(proposals),
        len(matrix),
        path_evaluated_count,
        path_truncated_count,
    )


def _small_median(values: tuple[float, ...]) -> float:
    """Match NumPy's scalar median without allocating an array for tiny paths."""

    if not values:
        raise ValueError("median requires at least one value")
    if len(values) > 4:
        return float(np.median(values))
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2.0)


def _small_mean(values: tuple[float, ...]) -> float:
    """Preserve NumPy's platform reduction order for trajectory tie-breaking."""

    if not values:
        raise ValueError("mean requires at least one value")
    return float(np.mean(values))


def _circular_medoid_epoch(
    epochs: tuple[int, ...],
    anchor_epoch: int,
    epoch_count: int,
) -> int:
    return min(
        set(epochs),
        key=lambda candidate: (
            sum(_circular_epoch_distance(candidate, epoch, epoch_count) for epoch in epochs),
            _circular_epoch_distance(candidate, anchor_epoch, epoch_count),
            candidate,
        ),
    )


def _linear_medoid(values: tuple[float, ...], anchor: float) -> float:
    return float(
        min(
            set(values),
            key=lambda candidate: (
                sum(abs(candidate - value) for value in values),
                abs(candidate - anchor),
                candidate,
            ),
        )
    )


def _linear_fit_residual_metrics(
    x_values: tuple[float, ...],
    y_values: tuple[float, ...],
) -> tuple[float, float]:
    if len(x_values) < 2 or math.isclose(max(x_values), min(x_values)):
        return 0.0, 0.0
    design = np.column_stack((np.ones(len(x_values)), np.asarray(x_values, dtype=float)))
    coefficients, *_ = np.linalg.lstsq(design, np.asarray(y_values, dtype=float), rcond=None)
    residual = np.asarray(y_values, dtype=float) - design @ coefficients
    return float(np.sqrt(np.mean(residual**2))), float(coefficients[1])


def _adjudicate_proposal(
    proposal: _Proposal,
    values: np.ndarray,
    exact_template: np.ndarray,
    control_templates: tuple[np.ndarray, ...],
    diagnostic_control_templates: tuple[np.ndarray, ...],
    sample_rate_hz: float,
    seed: KnownPilotModeSeed,
    nominal_epoch: int,
    blocks: tuple[tuple[int, int], ...],
    settings: SeededPilotAcquisitionConfig,
    *,
    proposal_origin: PilotModeProposalOrigin | None = None,
) -> KnownPilotModeCandidate:
    evidence = []
    epoch_count = math.ceil(sample_rate_hz / FRAME_RATE_HZ)
    for block_index, (
        (start, stop),
        acquire_score,
        acquire_support,
        block_epoch_sample,
        block_cfo_hz,
    ) in enumerate(
        zip(
            blocks,
            proposal.block_scores,
            proposal.block_support,
            proposal.block_epoch_samples,
            proposal.block_absolute_cfo_hz,
            strict=True,
        )
    ):
        projected, first_frame = _project_epoch(
            block_epoch_sample,
            start,
            sample_rate_hz / FRAME_RATE_HZ,
        )
        exact_score, exact_support = _normalized_absolute_block_score(
            values,
            exact_template,
            sample_rate_hz,
            block_epoch_sample,
            block_cfo_hz,
            DEFAULT_VERIFY_SYMBOLS,
            start,
            stop,
        )
        control_rows = tuple(
            _normalized_absolute_block_score(
                values,
                template,
                sample_rate_hz,
                block_epoch_sample,
                block_cfo_hz,
                DEFAULT_VERIFY_SYMBOLS,
                start,
                stop,
            )
            for template in control_templates
        )
        control_scores = tuple(row[0] for row in control_rows)
        diagnostic_rows = tuple(
            _normalized_absolute_block_score(
                values,
                template,
                sample_rate_hz,
                block_epoch_sample,
                block_cfo_hz,
                DEFAULT_VERIFY_SYMBOLS,
                start,
                stop,
            )
            for template in diagnostic_control_templates
        )
        diagnostic_scores = tuple(row[0] for row in diagnostic_rows)
        support = min(
            (
                acquire_support,
                exact_support,
                *(row[1] for row in control_rows),
            ),
            default=0,
        )
        control_max = max(control_scores, default=0.0)
        margin = exact_score - control_max
        passed = (
            support >= settings.minimum_frame_support_per_block
            and exact_score >= settings.minimum_exact_score
            and margin >= settings.minimum_exact_minus_control_margin
        )
        evidence.append(
            KnownPilotBlockEvidence(
                block_index=block_index,
                start_sample=start,
                stop_sample=stop,
                first_frame_start_sample=first_frame,
                projected_epoch_sample=projected,
                trajectory_epoch_sample=block_epoch_sample,
                trajectory_epoch_residual_samples=_signed_circular_epoch_delta(
                    block_epoch_sample,
                    proposal.trajectory_reference_epoch_sample,
                    epoch_count,
                ),
                absolute_cfo_hz=float(block_cfo_hz),
                trajectory_cfo_residual_hz=float(
                    block_cfo_hz
                    - (
                        proposal.trajectory_reference_absolute_cfo_hz
                        + seed.nominal_doppler_rate_hz_s * (0.5 * (start + stop) / sample_rate_hz)
                    )
                ),
                acquire_score=float(acquire_score),
                verify_score=float(exact_score),
                control_scores=control_scores,
                diagnostic_control_scores=diagnostic_scores,
                exact_minus_control_margin=float(margin),
                acquire_frame_support=acquire_support,
                verify_frame_support=exact_support,
                control_frame_support=tuple(row[1] for row in control_rows),
                diagnostic_control_frame_support=tuple(row[1] for row in diagnostic_rows),
                frame_support=support,
                passed_research_gate=passed,
            )
        )
    exact_scores = tuple(item.verify_score for item in evidence)
    control_maxima = tuple(max(item.control_scores, default=0.0) for item in evidence)
    diagnostic_columns = tuple(
        tuple(item.diagnostic_control_scores[index] for item in evidence)
        for index in range(len(diagnostic_control_templates))
    )
    margins = tuple(item.exact_minus_control_margin for item in evidence)
    passing_count = sum(item.passed_research_gate for item in evidence)
    median_exact = float(np.median(exact_scores))
    median_control = float(np.median(control_maxima))
    median_margin = float(np.median(margins))
    admitted = (
        proposal.trajectory_admissible
        and passing_count >= settings.minimum_consensus_blocks
        and median_exact >= settings.minimum_exact_score
        and median_margin >= settings.minimum_exact_minus_control_margin
    )
    canonical, alias_lift = canonicalize_cfo_alias(proposal.trajectory_reference_absolute_cfo_hz)
    return KnownPilotModeCandidate(
        rank=0,
        proposal_origin=(
            proposal_origin
            if proposal_origin is not None
            else (
                PilotModeProposalOrigin.PROTECTED_SEED
                if proposal.epoch_sample == nominal_epoch
                and math.isclose(
                    proposal.absolute_cfo_hz,
                    seed.nominal_absolute_cfo_hz,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                else PilotModeProposalOrigin.LOCAL_SEARCH
            )
        ),
        source_seed_index=0,
        source_branch_id=seed.branch_id,
        source_provenance_sha256=seed.provenance_sha256,
        source_nominal_epoch_sample=seed.nominal_epoch_sample,
        source_nominal_absolute_cfo_hz=seed.nominal_absolute_cfo_hz,
        proposal_epoch_sample=proposal.epoch_sample,
        proposal_absolute_cfo_hz=proposal.absolute_cfo_hz,
        epoch_sample=proposal.trajectory_reference_epoch_sample,
        absolute_cfo_hz=proposal.trajectory_reference_absolute_cfo_hz,
        doppler_rate_hz_s=seed.nominal_doppler_rate_hz_s,
        canonical_cfo_hz=canonical,
        cfo_alias_lift=alias_lift,
        acquire_score=proposal.acquire_score,
        median_verify_score=median_exact,
        median_control_score=median_control,
        median_diagnostic_control_scores=tuple(
            float(np.median(column)) for column in diagnostic_columns
        ),
        median_exact_minus_control_margin=median_margin,
        passing_block_count=passing_count,
        frame_support=sum(item.frame_support for item in evidence),
        blocks=tuple(evidence),
        trajectory_block_epoch_samples=proposal.block_epoch_samples,
        trajectory_block_epoch_residual_samples=tuple(
            item.trajectory_epoch_residual_samples for item in evidence
        ),
        trajectory_block_absolute_cfo_hz=proposal.block_absolute_cfo_hz,
        trajectory_block_cfo_residual_hz=tuple(
            item.trajectory_cfo_residual_hz for item in evidence
        ),
        trajectory_epoch_span_samples=proposal.trajectory_epoch_span_samples,
        trajectory_max_adjacent_epoch_step_samples=(
            proposal.trajectory_max_adjacent_epoch_step_samples
        ),
        trajectory_epoch_dispersion_samples=proposal.trajectory_epoch_dispersion_samples,
        trajectory_epoch_fit_rms_samples=proposal.trajectory_epoch_fit_rms_samples,
        trajectory_timing_rate_samples_s=proposal.trajectory_timing_rate_samples_s,
        trajectory_cfo_span_hz=proposal.trajectory_cfo_span_hz,
        trajectory_cfo_dispersion_hz=proposal.trajectory_cfo_dispersion_hz,
        trajectory_cfo_fit_rms_hz=proposal.trajectory_cfo_fit_rms_hz,
        trajectory_cfo_rate_residual_hz_s=proposal.trajectory_cfo_rate_residual_hz_s,
        trajectory_path_sha256=proposal.trajectory_path_sha256,
        trajectory_admissible=proposal.trajectory_admissible,
        whole_window_verify_score=None,
        whole_window_control_scores=(),
        whole_window_diagnostic_control_scores=(),
        whole_window_exact_minus_control_margin=None,
        whole_window_frame_support=0,
        whole_window_consistent_with_blocks=False,
        decision=(
            ResearchEvidenceDecision.CANDIDATE if admitted else ResearchEvidenceDecision.REJECTED
        ),
    )


def _retain_proposals(
    proposals: tuple[_Proposal, ...],
    nominal_epoch: int,
    nominal_cfo_hz: float,
    epoch_count: int,
    settings: SeededPilotAcquisitionConfig,
) -> tuple[tuple[_Proposal, ...], int, int]:
    seed = next(
        proposal
        for proposal in proposals
        if proposal.epoch_sample == nominal_epoch
        and math.isclose(
            proposal.absolute_cfo_hz,
            nominal_cfo_hz,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    )
    ordered = sorted(
        proposals,
        key=lambda proposal: (
            proposal.acquire_score,
            -_circular_epoch_distance(proposal.epoch_sample, nominal_epoch, epoch_count),
            -abs(proposal.absolute_cfo_hz - nominal_cfo_hz),
            -proposal.epoch_sample,
            -proposal.absolute_cfo_hz,
        ),
        reverse=True,
    )
    retained = [seed]
    suppressed = 0
    truncated = 0
    for proposal in ordered:
        if proposal is seed:
            continue
        if any(
            _circular_epoch_distance(
                proposal.epoch_sample,
                other.epoch_sample,
                epoch_count,
            )
            < settings.candidate_epoch_separation_samples
            and abs(proposal.absolute_cfo_hz - other.absolute_cfo_hz)
            <= settings.candidate_cfo_separation_hz
            for other in retained
        ):
            suppressed += 1
        elif len(retained) < settings.retained_candidate_count:
            retained.append(proposal)
        else:
            truncated += 1
    return tuple(retained), suppressed, truncated


def _project_epoch(
    epoch_sample: int,
    block_start_sample: int,
    period_samples: float,
) -> tuple[int, int]:
    """Project a capture-relative base epoch onto the exact rounded lattice."""

    frame_index = max(0, math.floor((block_start_sample - epoch_sample) / period_samples) - 1)
    first = epoch_sample + round(frame_index * period_samples)
    while first < block_start_sample:
        frame_index += 1
        first = epoch_sample + round(frame_index * period_samples)
    while frame_index > 0:
        previous = epoch_sample + round((frame_index - 1) * period_samples)
        if previous < block_start_sample:
            break
        frame_index -= 1
        first = previous
    return first - block_start_sample, first


def _normalized_absolute_block_score(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: float,
    symbols: tuple[int, ...],
    block_start_sample: int,
    block_stop_sample: int,
) -> tuple[float, int]:
    """Score complete frames while preserving the capture-relative lattice."""

    sample_indexes = _pilot_sample_indexes(sample_rate_hz, symbols)
    references = template[sample_indexes]
    template_energy = float(np.vdot(references, references).real)
    rotation = np.exp(-2j * np.pi * absolute_cfo_hz * sample_indexes / sample_rate_hz)
    period = sample_rate_hz / FRAME_RATE_HZ
    _, first_frame = _project_epoch(epoch_sample, block_start_sample, period)
    frame_index = round((first_frame - epoch_sample) / period)
    scores = []
    while True:
        frame_start = epoch_sample + round(frame_index * period)
        absolute = frame_start + sample_indexes
        if absolute[-1] >= block_stop_sample:
            break
        received = values[absolute]
        denominator = math.sqrt(template_energy * float(np.vdot(received, received).real))
        scores.append(
            float(abs(np.vdot(references, received * rotation)) / denominator)
            if denominator
            else 0.0
        )
        frame_index += 1
    return (float(np.mean(scores)) if scores else 0.0, len(scores))


@lru_cache(maxsize=32)
def _pilot_sample_indexes(sample_rate_hz: float, symbols: tuple[int, ...]) -> np.ndarray:
    result = np.concatenate(
        tuple(
            np.arange(
                round(symbol * sample_rate_hz * OFDM_SYMBOL_DURATION_S),
                round((symbol + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S),
            )
            for symbol in symbols
        )
    )
    result.flags.writeable = False
    return result


def _local_epochs(center: int, radius: int, epoch_count: int) -> tuple[int, ...]:
    return tuple(sorted({(center + offset) % epoch_count for offset in range(-radius, radius + 1)}))


def _centered_grid(center: float, radius: float, step: float) -> tuple[float, ...]:
    step_count = math.floor(radius / step + 1e-12)
    values = {float(center + offset * step) for offset in range(-step_count, step_count + 1)}
    values.add(float(center))
    values.add(float(center - radius))
    values.add(float(center + radius))
    return tuple(sorted(values))


def _evenly_spaced_block_starts(
    sample_count: int,
    block_length: int,
    block_count: int,
) -> tuple[int, ...]:
    if block_count == 1:
        return (0,)
    span = sample_count - block_length
    return tuple(round(index * span / (block_count - 1)) for index in range(block_count))


def _frame_offset_count(sample_count: int, period_samples: float) -> int:
    """Count the rounded frame starts supplied to the global proposal scorer."""

    count = 0
    while round(count * period_samples) < sample_count:
        count += 1
    return count


def _circular_epoch_distance(left: int, right: int, epoch_count: int) -> int:
    raw = abs(left - right)
    return min(raw, epoch_count - raw)


def _signed_circular_epoch_delta(value: int, reference: int, epoch_count: int) -> int:
    delta = (value - reference) % epoch_count
    if delta > epoch_count / 2:
        delta -= epoch_count
    return int(delta)


def _insufficient_result(
    seed: KnownPilotModeSeed,
    edge: StarlinkEdge,
    expected_symbol_roll: int,
    settings: SeededPilotAcquisitionConfig,
    sample_rate_hz: float,
    sample_count: int,
    period_samples: float,
    reason: str,
    exact_template_identity: PilotTemplateIdentity,
    conditional_control_template_identities: tuple[PilotTemplateIdentity, ...],
    diagnostic_control_template_identities: tuple[PilotTemplateIdentity, ...],
) -> SeededPilotAcquisitionResult:
    return SeededPilotAcquisitionResult(
        status=NumericalStatus.INSUFFICIENT,
        config_digest=settings.digest,
        seed=seed,
        additional_seeds=(),
        evaluated_seed_count=1,
        edge=edge,
        expected_symbol_roll=expected_symbol_roll,
        control_symbol_rolls=settings.control_symbol_rolls,
        exact_template_identity=exact_template_identity,
        conditional_control_template_identities=conditional_control_template_identities,
        diagnostic_control_template_identities=diagnostic_control_template_identities,
        sample_rate_hz=float(sample_rate_hz),
        sample_count=sample_count,
        frame_period_samples=float(period_samples),
        block_starts=(),
        searched_epoch_count=0,
        searched_cfo_count=0,
        evaluated_grid_point_count=0,
        evaluated_block_score_count=0,
        trajectory_path_evaluated_count=0,
        trajectory_path_limit_truncated_count=0,
        separation_suppressed_count=0,
        candidate_limit_truncated_count=0,
        global_fallback_attempted=False,
        global_proposal_block_index=settings.global_proposal_block_index,
        global_proposal_block_start_sample=None,
        global_proposal_block_stop_sample=None,
        global_proposal_sample_count=0,
        global_proposal_symbol_count=0,
        global_proposal_frame_offset_count=0,
        global_searched_epoch_count=0,
        global_searched_cfo_count=0,
        global_evaluated_grid_point_count=0,
        global_peak_count=0,
        global_evaluated_block_score_count=0,
        global_trajectory_path_evaluated_count=0,
        global_trajectory_path_limit_truncated_count=0,
        global_separation_suppressed_count=0,
        global_candidate_limit_truncated_count=0,
        whole_window_rescore_candidate_count=0,
        whole_window_rescore_template_score_count=0,
        retained_modes=(),
        presence_disposition=ResearchDisposition.INSUFFICIENT,
        code_specificity_disposition=ResearchDisposition.INSUFFICIENT,
        cfo_alias_resolution_disposition=ResearchDisposition.INSUFFICIENT,
        uniqueness_disposition=ResearchDisposition.INSUFFICIENT,
        reason=reason,
    )
