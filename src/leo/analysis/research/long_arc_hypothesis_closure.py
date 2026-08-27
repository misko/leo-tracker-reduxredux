"""Digest-closed prequential accounting for long-arc hypotheses.

This module is a pure reducer.  It consumes chronological, already-computed
proper log predictive scores for a frozen H0/H1/H1-switch/K2 inventory.  It
does not open radio data, propagate a TLE, construct or select candidates, fit
a nuisance state, choose a change point, or calibrate a likelihood.  Those
operations belong upstream and are represented here only by digest references.

Posterior probabilities are explicitly conditional on the evaluated state
inventory.  Pruned and otherwise unresolved prior mass has no predictive score
and therefore cannot honestly be updated; any such mass is retained in exact
prior accounting and forces the descriptive outcome to ``unresolved`` unless
the frozen policy explicitly permits it.  No returned outcome is a satellite
identity claim.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

from leo.contracts.digests import Sha256Digest, canonical_digest

type HypothesisFamily = Literal[
    "h0-radio-null",
    "h1-single-candidate",
    "h1-switch",
    "k2-two-candidate",
]
type OptionalFamily = Literal["h1-switch", "k2-two-candidate"]
type OptionalFamilyStatus = Literal["evaluated", "structurally-inapplicable"]
type ClosureDevelopmentLimitation = Literal["incomplete-opportunity-inventory"]
type ClosureOutcome = Literal["singleton", "ambiguity", "unresolved"]
type OutcomeReason = Literal[
    "incomplete-opportunity-inventory",
    "outside-evaluated-prior-mass",
    "radio-or-unassigned-competitive",
    "single-catalogue-connected-neighborhood-meets-policy",
    "connected-neighborhood-contains-multiple-catalogues",
    "multiple-connected-neighborhoods-required",
    "candidate-neighborhood-mass-diffuse",
]

_ALGORITHM_VERSION = "long-arc-prequential-hypothesis-closure-v1"
_FAMILY_ORDER: tuple[HypothesisFamily, ...] = (
    "h0-radio-null",
    "h1-single-candidate",
    "h1-switch",
    "k2-two-candidate",
)
_OPTIONAL_FAMILIES: tuple[OptionalFamily, ...] = (
    "h1-switch",
    "k2-two-candidate",
)
_HARD_MAX_HYPOTHESES = 100_000
_HARD_MAX_BLOCKS = 100_000
_HARD_MAX_SCORE_CELLS = 10_000_000


class LongArcHypothesisClosureInputError(ValueError):
    """The frozen hypothesis, prior, or chronological score inventory is invalid."""


class LongArcHypothesisClosureNumericalError(ValueError):
    """The prequential probability calculation is not representable."""


class LongArcHypothesisClosureWorkLimitError(ValueError):
    """The declared hypothesis-by-block work cap would be exceeded."""


@dataclass(frozen=True, slots=True)
class LongArcHypothesisPrior:
    """One explicit evaluated state and its unconditional prior mass.

    ``normalized_log_prior_probability`` is authoritative.  The derived linear
    value may be zero when an individually tiny catalogue/tau state underflows;
    such a state remains in every log-domain normalization and is not pruned.

    ``connected_neighborhood_label`` is supplied by a response-free
    observability analysis. Several candidate/tau states may deliberately share
    a single-linkage label. The label is a connected neighborhood, not a claim
    that every pair of endpoints is mutually indistinguishable.
    """

    hypothesis_id: Sha256Digest
    family: HypothesisFamily
    normalized_log_prior_probability: float
    connected_neighborhood_label: str
    catalog_numbers: tuple[int, ...]
    tau_s: tuple[float, ...]
    nuisance_model_reference_digest: Sha256Digest
    change_point_model_reference_digest: Sha256Digest | None = None
    prior_probability: float = field(init=False)
    prior_probability_representable: bool = field(init=False)

    def __post_init__(self) -> None:
        if not _is_digest(self.hypothesis_id):
            raise LongArcHypothesisClosureInputError("hypothesis_id must be digest-bound")
        if self.family not in _FAMILY_ORDER:
            raise LongArcHypothesisClosureInputError("hypothesis family is unsupported")
        if not math.isfinite(self.normalized_log_prior_probability):
            raise LongArcHypothesisClosureInputError("normalized log priors must be finite")
        if self.normalized_log_prior_probability > 0.0:
            raise LongArcHypothesisClosureInputError("normalized log priors cannot exceed log(1)")
        linear_prior = math.exp(self.normalized_log_prior_probability)
        object.__setattr__(self, "prior_probability", linear_prior)
        object.__setattr__(self, "prior_probability_representable", linear_prior > 0.0)
        if not self.connected_neighborhood_label.strip():
            raise LongArcHypothesisClosureInputError(
                "connected-neighborhood labels cannot be empty"
            )
        if not _is_digest(self.nuisance_model_reference_digest):
            raise LongArcHypothesisClosureInputError("nuisance models must be digest-referenced")
        if self.change_point_model_reference_digest is not None and not _is_digest(
            self.change_point_model_reference_digest
        ):
            raise LongArcHypothesisClosureInputError(
                "change-point models must be digest-referenced"
            )
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in self.catalog_numbers
        ):
            raise LongArcHypothesisClosureInputError("catalog numbers must be positive integers")
        if any(not math.isfinite(item) for item in self.tau_s):
            raise LongArcHypothesisClosureInputError("tau states must be finite")
        self._validate_family_shape()

    def _validate_family_shape(self) -> None:
        if self.family == "h0-radio-null":
            if self.catalog_numbers or self.tau_s:
                raise LongArcHypothesisClosureInputError(
                    "H0 states cannot carry catalogue or tau identities"
                )
            if self.change_point_model_reference_digest is not None:
                raise LongArcHypothesisClosureInputError(
                    "H0 states cannot carry a change-point model"
                )
            return
        if self.family == "h1-single-candidate":
            if len(self.catalog_numbers) != 1 or len(self.tau_s) != 1:
                raise LongArcHypothesisClosureInputError(
                    "H1 states require exactly one catalogue and one tau state"
                )
            if self.change_point_model_reference_digest is not None:
                raise LongArcHypothesisClosureInputError(
                    "persistent H1 states cannot carry a change-point model"
                )
            return
        if len(self.catalog_numbers) != 2 or len(self.tau_s) != 2:
            raise LongArcHypothesisClosureInputError(
                "switch and K2 states require exactly two catalogue/tau entries"
            )
        if self.family == "h1-switch":
            if self.change_point_model_reference_digest is None:
                raise LongArcHypothesisClosureInputError(
                    "H1-switch states require a frozen change-point model"
                )
            return
        if len(set(self.catalog_numbers)) != 2:
            raise LongArcHypothesisClosureInputError(
                "K2 states require two distinct simultaneous catalogues"
            )
        if self.change_point_model_reference_digest is not None:
            raise LongArcHypothesisClosureInputError(
                "simultaneous K2 states cannot carry a change-point model"
            )


@dataclass(frozen=True, slots=True)
class LongArcHypothesisBlockLogScore:
    """One upstream proper score on one exact future calendar block."""

    hypothesis_id: Sha256Digest
    proper_log_score: float
    score_reference_digest: Sha256Digest
    scored_observation_inventory_digest: Sha256Digest
    nuisance_state_reference_digest: Sha256Digest
    change_point_reference_digest: Sha256Digest | None = None
    score_kind: Literal["proper-log-predictive-density"] = field(
        default="proper-log-predictive-density", init=False
    )
    future_response_used_for_fit: Literal[False] = field(default=False, init=False)
    scored_once_without_refit: Literal[True] = field(default=True, init=False)

    def __post_init__(self) -> None:
        if not _is_digest(self.hypothesis_id):
            raise LongArcHypothesisClosureInputError(
                "block-score hypothesis identities must be digest-bound"
            )
        if not math.isfinite(self.proper_log_score):
            raise LongArcHypothesisClosureInputError("proper log scores must be finite")
        for label, value in (
            ("score reference", self.score_reference_digest),
            ("observation inventory", self.scored_observation_inventory_digest),
            ("nuisance state", self.nuisance_state_reference_digest),
        ):
            if not _is_digest(value):
                raise LongArcHypothesisClosureInputError(f"{label} must be digest-bound")
        if self.change_point_reference_digest is not None and not _is_digest(
            self.change_point_reference_digest
        ):
            raise LongArcHypothesisClosureInputError("score change points must be digest-bound")


@dataclass(frozen=True, slots=True)
class LongArcChronologicalScoreBlock:
    """A common, response-frozen block score for the complete evaluated inventory."""

    block_id: Sha256Digest
    block_start_utc_ns: int
    block_end_utc_ns: int
    observation_ids: tuple[Sha256Digest, ...]
    observation_inventory_digest: Sha256Digest
    conditioning_history_digest: Sha256Digest
    scores: tuple[LongArcHypothesisBlockLogScore, ...]
    block_digest: Sha256Digest

    def __post_init__(self) -> None:
        if not _is_digest(self.block_id) or not _is_digest(self.block_digest):
            raise LongArcHypothesisClosureInputError("score blocks must be digest-bound")
        if not _is_digest(self.observation_inventory_digest) or not _is_digest(
            self.conditioning_history_digest
        ):
            raise LongArcHypothesisClosureInputError(
                "block inventory and conditioning history must be digest-bound"
            )
        if (
            isinstance(self.block_start_utc_ns, bool)
            or not isinstance(self.block_start_utc_ns, int)
            or isinstance(self.block_end_utc_ns, bool)
            or not isinstance(self.block_end_utc_ns, int)
            or self.block_start_utc_ns < 0
            or self.block_end_utc_ns <= self.block_start_utc_ns
        ):
            raise LongArcHypothesisClosureInputError(
                "score blocks require a positive chronological UTC interval"
            )
        if not self.observation_ids or any(not _is_digest(item) for item in self.observation_ids):
            raise LongArcHypothesisClosureInputError(
                "score blocks require digest-bound observations"
            )
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise LongArcHypothesisClosureInputError("a score block cannot repeat an observation")
        if not self.scores:
            raise LongArcHypothesisClosureInputError("score blocks cannot be empty")


@dataclass(frozen=True, slots=True)
class LongArcHypothesisClosureEvidence:
    """One frozen sequence of priors and already-computed block scores."""

    sequence_label: str
    graph_content_digest: Sha256Digest
    scoring_protocol_digest: Sha256Digest
    prior_policy_digest: Sha256Digest
    connected_neighborhood_map_digest: Sha256Digest
    hypotheses: tuple[LongArcHypothesisPrior, ...]
    blocks: tuple[LongArcChronologicalScoreBlock, ...]
    pruned_prior_mass: float
    unresolved_prior_mass: float
    development_limitations: tuple[ClosureDevelopmentLimitation, ...]
    content_digest: Sha256Digest

    def __post_init__(self) -> None:
        if not self.sequence_label.strip():
            raise LongArcHypothesisClosureInputError("sequence label cannot be empty")
        for label, value in (
            ("graph", self.graph_content_digest),
            ("scoring protocol", self.scoring_protocol_digest),
            ("prior policy", self.prior_policy_digest),
            ("connected-neighborhood map", self.connected_neighborhood_map_digest),
            ("evidence content", self.content_digest),
        ):
            if not _is_digest(value):
                raise LongArcHypothesisClosureInputError(f"{label} must be digest-bound")
        if not self.hypotheses or not self.blocks:
            raise LongArcHypothesisClosureInputError(
                "closure evidence requires hypotheses and chronological blocks"
            )
        for mass_label, mass_value in (
            ("pruned prior mass", self.pruned_prior_mass),
            ("unresolved prior mass", self.unresolved_prior_mass),
        ):
            if not math.isfinite(mass_value) or mass_value < 0.0 or mass_value > 1.0:
                raise LongArcHypothesisClosureInputError(
                    f"{mass_label} must be finite and within [0,1]"
                )
        if self.development_limitations != tuple(sorted(set(self.development_limitations))):
            raise LongArcHypothesisClosureInputError(
                "development limitations must be unique and canonical"
            )
        if any(item != "incomplete-opportunity-inventory" for item in self.development_limitations):
            raise LongArcHypothesisClosureInputError("development limitation is unsupported")


@dataclass(frozen=True, slots=True)
class LongArcHypothesisClosureConfig:
    """Bounded descriptive policy for posterior summaries.

    These thresholds turn an already-normalized posterior into the labels
    ``singleton``, ``ambiguity``, and ``unresolved``.  They are digest-bound in
    the result, but they are not an identity gate or a calibration claim.
    """

    credible_neighborhood_probability: float = 0.95
    singleton_minimum_within_candidate_probability: float = 0.95
    minimum_candidate_posterior_probability: float = 0.5
    maximum_outside_prior_mass_for_resolved_outcome: float = 0.0
    prior_normalization_tolerance: float = 1e-12
    maximum_hypotheses: int = 4_096
    maximum_blocks: int = 4_096
    maximum_score_cells: int = 1_000_000

    def __post_init__(self) -> None:
        for label, value in (
            ("credible neighborhood probability", self.credible_neighborhood_probability),
            (
                "singleton minimum probability",
                self.singleton_minimum_within_candidate_probability,
            ),
        ):
            if not math.isfinite(value) or not 0.0 < value <= 1.0:
                raise LongArcHypothesisClosureInputError(f"{label} must be within (0,1]")
        for label, value in (
            (
                "minimum candidate posterior probability",
                self.minimum_candidate_posterior_probability,
            ),
            (
                "maximum outside prior mass",
                self.maximum_outside_prior_mass_for_resolved_outcome,
            ),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise LongArcHypothesisClosureInputError(f"{label} must be within [0,1]")
        if (
            not math.isfinite(self.prior_normalization_tolerance)
            or self.prior_normalization_tolerance < 0.0
            or self.prior_normalization_tolerance > 1e-9
        ):
            raise LongArcHypothesisClosureInputError(
                "prior normalization tolerance must be within [0,1e-9]"
            )
        limits = (
            ("maximum_hypotheses", self.maximum_hypotheses, _HARD_MAX_HYPOTHESES),
            ("maximum_blocks", self.maximum_blocks, _HARD_MAX_BLOCKS),
            ("maximum_score_cells", self.maximum_score_cells, _HARD_MAX_SCORE_CELLS),
        )
        for label, value, hard_limit in limits:
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                or value > hard_limit
            ):
                raise LongArcHypothesisClosureInputError(
                    f"{label} must be a positive bounded integer"
                )


@dataclass(frozen=True, slots=True)
class LongArcPriorMassAccounting:
    evaluated_prior_mass: float
    log_evaluated_prior_mass: float
    evaluated_candidate_prior_mass: float
    log_evaluated_candidate_prior_mass: float
    h0_radio_or_unassigned_prior_mass: float
    log_h0_radio_or_unassigned_prior_mass: float
    pruned_prior_mass: float
    unresolved_prior_mass: float
    outside_evaluated_prior_mass: float
    accounted_prior_mass: float
    normalization_residual: float
    prior_is_normalized: Literal[True] = field(default=True, init=False)
    h0_radio_or_unassigned_is_subset_of_evaluated: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class LongArcOptionalFamilyAvailability:
    family: OptionalFamily
    status: OptionalFamilyStatus
    evaluated_state_count: int
    evaluated_prior_mass: float
    log_evaluated_prior_mass: float | None
    reason: Literal[
        "explicit-states-present",
        "no-explicit-state-in-frozen-inventory",
    ]


@dataclass(frozen=True, slots=True)
class LongArcHypothesisPosteriorMass:
    hypothesis_id: Sha256Digest
    family: HypothesisFamily
    connected_neighborhood_label: str
    catalog_numbers: tuple[int, ...]
    tau_s: tuple[float, ...]
    normalized_log_prior_probability: float
    prior_probability: float
    prior_probability_representable: bool
    posterior_probability: float
    cumulative_proper_log_score: float
    nuisance_model_reference_digest: Sha256Digest
    nuisance_state_reference_digest: Sha256Digest
    change_point_model_reference_digest: Sha256Digest | None
    change_point_reference_digest: Sha256Digest | None
    score_reference_digest: Sha256Digest


@dataclass(frozen=True, slots=True)
class LongArcFamilyPosteriorMass:
    family: HypothesisFamily
    evaluated_state_count: int
    posterior_probability: float


@dataclass(frozen=True, slots=True)
class LongArcConnectedNeighborhoodPosteriorMass:
    family: HypothesisFamily
    connected_neighborhood_label: str
    evaluated_state_count: int
    catalog_numbers: tuple[int, ...]
    posterior_probability: float
    within_candidate_probability: float | None


@dataclass(frozen=True, slots=True)
class LongArcClosureOutcomeSummary:
    outcome: ClosureOutcome
    reason: OutcomeReason
    candidate_posterior_probability: float
    h0_radio_or_unassigned_posterior_probability: float
    outside_evaluated_prior_mass: float
    credible_connected_neighborhoods: tuple[LongArcConnectedNeighborhoodPosteriorMass, ...]
    credible_neighborhood_probability_target: float
    singleton_minimum_within_candidate_probability: float
    minimum_candidate_posterior_probability: float
    identity_claimed: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class LongArcPrequentialClosureSummary:
    block_index: int
    block_id: Sha256Digest
    block_start_utc_ns: int
    block_end_utc_ns: int
    cumulative_duration_s: float
    cumulative_observation_count: int
    block_log_predictive_evidence_conditioned_on_evaluated: float
    cumulative_log_evidence_conditioned_on_evaluated: float
    family_posterior: tuple[LongArcFamilyPosteriorMass, ...]
    connected_neighborhood_summary_status: Literal[
        "suppressed-final-prefix-map",
        "available-final-prefix",
    ]
    connected_neighborhood_posterior: tuple[LongArcConnectedNeighborhoodPosteriorMass, ...]
    hypothesis_entropy_nats: float
    family_entropy_nats: float
    connected_neighborhood_entropy_nats: float | None
    candidate_connected_neighborhood_entropy_nats: float | None
    effective_candidate_connected_neighborhood_count: float | None
    outcome: LongArcClosureOutcomeSummary | None


@dataclass(frozen=True, slots=True)
class LongArcHypothesisClosureResult:
    sequence_label: str
    graph_content_digest: Sha256Digest
    evidence_content_digest: Sha256Digest
    scoring_protocol_digest: Sha256Digest
    prior_policy_digest: Sha256Digest
    connected_neighborhood_map_digest: Sha256Digest
    config_digest: Sha256Digest
    prior_mass_accounting: LongArcPriorMassAccounting
    development_limitations: tuple[ClosureDevelopmentLimitation, ...]
    optional_family_availability: tuple[LongArcOptionalFamilyAvailability, ...]
    rolling_summaries: tuple[LongArcPrequentialClosureSummary, ...]
    final_summary: LongArcPrequentialClosureSummary
    final_hypothesis_posterior: tuple[LongArcHypothesisPosteriorMass, ...]
    nuisance_model_reference_digests: tuple[Sha256Digest, ...]
    nuisance_state_reference_digests: tuple[Sha256Digest, ...]
    change_point_model_reference_digests: tuple[Sha256Digest, ...]
    change_point_reference_digests: tuple[Sha256Digest, ...]
    result_digest: Sha256Digest
    algorithm_version: Literal["long-arc-prequential-hypothesis-closure-v1"] = field(
        default="long-arc-prequential-hypothesis-closure-v1", init=False
    )
    input_scores_are_precomputed: Literal[True] = field(default=True, init=False)
    common_calendar_blocks_enforced: Literal[True] = field(default=True, init=False)
    posterior_conditioned_on_evaluated_states: Literal[True] = field(default=True, init=False)
    outside_prior_mass_updated: Literal[False] = field(default=False, init=False)
    future_blocks_rewrite_prior_summaries: Literal[False] = field(default=False, init=False)
    candidate_selection_performed: Literal[False] = field(default=False, init=False)
    rf_response_accessed: Literal[False] = field(default=False, init=False)
    likelihood_fitted: Literal[False] = field(default=False, init=False)
    posterior_probability_calibrated: Literal[False] = field(default=False, init=False)
    model_selection_gate_produced: Literal[False] = field(default=False, init=False)
    outcome_is_descriptive: Literal[True] = field(default=True, init=False)
    rolling_connected_neighborhood_claims_suppressed: Literal[True] = field(
        default=True, init=False
    )
    identity_claimed: Literal[False] = field(default=False, init=False)


def observation_inventory_digest(
    *,
    block_id: Sha256Digest,
    block_start_utc_ns: int,
    block_end_utc_ns: int,
    observation_ids: tuple[Sha256Digest, ...],
) -> Sha256Digest:
    """Bind the exact common observation inventory of one calendar block."""

    return canonical_digest(
        {
            "block_id": block_id,
            "block_start_utc_ns": block_start_utc_ns,
            "block_end_utc_ns": block_end_utc_ns,
            "observation_ids": observation_ids,
        }
    )


def conditioning_history_digest(
    preceding_blocks: tuple[LongArcChronologicalScoreBlock, ...],
) -> Sha256Digest:
    """Bind only already-scored blocks, never the current or future response."""

    return canonical_digest(
        {
            "algorithm": "chronological-score-conditioning-history-v1",
            "preceding_block_digests": tuple(item.block_digest for item in preceding_blocks),
        }
    )


def seal_chronological_score_block(
    *,
    block_id: Sha256Digest,
    block_start_utc_ns: int,
    block_end_utc_ns: int,
    observation_ids: tuple[Sha256Digest, ...],
    scores: tuple[LongArcHypothesisBlockLogScore, ...],
    preceding_blocks: tuple[LongArcChronologicalScoreBlock, ...],
) -> LongArcChronologicalScoreBlock:
    """Package an upstream score bundle with inventory and causal-history digests."""

    inventory_digest = observation_inventory_digest(
        block_id=block_id,
        block_start_utc_ns=block_start_utc_ns,
        block_end_utc_ns=block_end_utc_ns,
        observation_ids=observation_ids,
    )
    if any(item.scored_observation_inventory_digest != inventory_digest for item in scores):
        raise LongArcHypothesisClosureInputError(
            "every hypothesis score must use the exact common block inventory"
        )
    history_digest = conditioning_history_digest(preceding_blocks)
    payload = {
        "block_id": block_id,
        "block_start_utc_ns": block_start_utc_ns,
        "block_end_utc_ns": block_end_utc_ns,
        "observation_ids": observation_ids,
        "observation_inventory_digest": inventory_digest,
        "conditioning_history_digest": history_digest,
        "scores": tuple(asdict(item) for item in scores),
    }
    return LongArcChronologicalScoreBlock(
        block_id=block_id,
        block_start_utc_ns=block_start_utc_ns,
        block_end_utc_ns=block_end_utc_ns,
        observation_ids=observation_ids,
        observation_inventory_digest=inventory_digest,
        conditioning_history_digest=history_digest,
        scores=scores,
        block_digest=canonical_digest(payload),
    )


def seal_long_arc_hypothesis_closure_evidence(
    *,
    sequence_label: str,
    graph_content_digest: Sha256Digest,
    scoring_protocol_digest: Sha256Digest,
    prior_policy_digest: Sha256Digest,
    connected_neighborhood_map_digest: Sha256Digest,
    hypotheses: tuple[LongArcHypothesisPrior, ...],
    blocks: tuple[LongArcChronologicalScoreBlock, ...],
    pruned_prior_mass: float = 0.0,
    unresolved_prior_mass: float = 0.0,
    development_limitations: tuple[ClosureDevelopmentLimitation, ...] = (),
) -> LongArcHypothesisClosureEvidence:
    """Digest-close an already-generated C3 score inventory."""

    payload = {
        "sequence_label": sequence_label,
        "graph_content_digest": graph_content_digest,
        "scoring_protocol_digest": scoring_protocol_digest,
        "prior_policy_digest": prior_policy_digest,
        "connected_neighborhood_map_digest": connected_neighborhood_map_digest,
        "hypotheses": tuple(asdict(item) for item in hypotheses),
        "block_digests": tuple(item.block_digest for item in blocks),
        "pruned_prior_mass": pruned_prior_mass,
        "unresolved_prior_mass": unresolved_prior_mass,
        "development_limitations": development_limitations,
    }
    return LongArcHypothesisClosureEvidence(
        sequence_label=sequence_label,
        graph_content_digest=graph_content_digest,
        scoring_protocol_digest=scoring_protocol_digest,
        prior_policy_digest=prior_policy_digest,
        connected_neighborhood_map_digest=connected_neighborhood_map_digest,
        hypotheses=hypotheses,
        blocks=blocks,
        pruned_prior_mass=pruned_prior_mass,
        unresolved_prior_mass=unresolved_prior_mass,
        development_limitations=development_limitations,
        content_digest=canonical_digest(payload),
    )


def close_long_arc_hypotheses(
    evidence: LongArcHypothesisClosureEvidence,
    config: LongArcHypothesisClosureConfig | None = None,
) -> LongArcHypothesisClosureResult:
    """Accumulate prequential posterior mass over a frozen state inventory."""

    if config is None:
        config = LongArcHypothesisClosureConfig()
    _validate_evidence(evidence, config)
    accounting = _prior_mass_accounting(evidence, config)
    availability = _optional_family_availability(evidence.hypotheses)
    cumulative_scores = [0.0] * len(evidence.hypotheses)
    conditional_log_priors = [
        item.normalized_log_prior_probability - accounting.log_evaluated_prior_mass
        for item in evidence.hypotheses
    ]
    summaries: list[LongArcPrequentialClosureSummary] = []
    final_hypothesis_posterior: tuple[LongArcHypothesisPosteriorMass, ...] = ()
    previous_log_evidence = 0.0
    cumulative_observation_count = 0
    first_start = evidence.blocks[0].block_start_utc_ns
    for block_index, block in enumerate(evidence.blocks, start=1):
        for index, score in enumerate(block.scores):
            cumulative_scores[index] += score.proper_log_score
            if not math.isfinite(cumulative_scores[index]):
                raise LongArcHypothesisClosureNumericalError(
                    "cumulative proper log score is not representable"
                )
        log_weights = tuple(
            prior + score
            for prior, score in zip(conditional_log_priors, cumulative_scores, strict=True)
        )
        cumulative_log_evidence = _log_sum_exp(log_weights)
        posterior = _normalized_probabilities(log_weights, cumulative_log_evidence)
        block_log_evidence = cumulative_log_evidence - previous_log_evidence
        if not math.isfinite(block_log_evidence):
            raise LongArcHypothesisClosureNumericalError(
                "block predictive evidence is not representable"
            )
        cumulative_observation_count += len(block.observation_ids)
        summary, final_hypothesis_posterior = _summarize_block(
            block_index=block_index,
            block=block,
            first_start_utc_ns=first_start,
            cumulative_observation_count=cumulative_observation_count,
            cumulative_scores=tuple(cumulative_scores),
            posterior=posterior,
            hypotheses=evidence.hypotheses,
            accounting=accounting,
            config=config,
            block_log_evidence=block_log_evidence,
            cumulative_log_evidence=cumulative_log_evidence,
            include_connected_neighborhood_summary=(block_index == len(evidence.blocks)),
            development_limitations=evidence.development_limitations,
        )
        summaries.append(summary)
        previous_log_evidence = cumulative_log_evidence
    config_digest = canonical_digest(asdict(config))
    nuisance_models = tuple(
        sorted({item.nuisance_model_reference_digest for item in evidence.hypotheses})
    )
    nuisance_states = tuple(
        sorted(
            {
                score.nuisance_state_reference_digest
                for block in evidence.blocks
                for score in block.scores
            }
        )
    )
    change_point_models = tuple(
        sorted(
            {
                item.change_point_model_reference_digest
                for item in evidence.hypotheses
                if item.change_point_model_reference_digest is not None
            }
        )
    )
    change_points = tuple(
        sorted(
            {
                score.change_point_reference_digest
                for block in evidence.blocks
                for score in block.scores
                if score.change_point_reference_digest is not None
            }
        )
    )
    payload = {
        "sequence_label": evidence.sequence_label,
        "graph_content_digest": evidence.graph_content_digest,
        "evidence_content_digest": evidence.content_digest,
        "scoring_protocol_digest": evidence.scoring_protocol_digest,
        "prior_policy_digest": evidence.prior_policy_digest,
        "connected_neighborhood_map_digest": evidence.connected_neighborhood_map_digest,
        "config_digest": config_digest,
        "prior_mass_accounting": asdict(accounting),
        "development_limitations": evidence.development_limitations,
        "optional_family_availability": tuple(asdict(item) for item in availability),
        "rolling_summaries": tuple(asdict(item) for item in summaries),
        "final_summary": asdict(summaries[-1]),
        "final_hypothesis_posterior": tuple(asdict(item) for item in final_hypothesis_posterior),
        "nuisance_model_reference_digests": nuisance_models,
        "nuisance_state_reference_digests": nuisance_states,
        "change_point_model_reference_digests": change_point_models,
        "change_point_reference_digests": change_points,
        "algorithm_version": _ALGORITHM_VERSION,
        "input_scores_are_precomputed": True,
        "common_calendar_blocks_enforced": True,
        "posterior_conditioned_on_evaluated_states": True,
        "outside_prior_mass_updated": False,
        "future_blocks_rewrite_prior_summaries": False,
        "candidate_selection_performed": False,
        "rf_response_accessed": False,
        "likelihood_fitted": False,
        "posterior_probability_calibrated": False,
        "model_selection_gate_produced": False,
        "outcome_is_descriptive": True,
        "rolling_connected_neighborhood_claims_suppressed": True,
        "identity_claimed": False,
    }
    return LongArcHypothesisClosureResult(
        sequence_label=evidence.sequence_label,
        graph_content_digest=evidence.graph_content_digest,
        evidence_content_digest=evidence.content_digest,
        scoring_protocol_digest=evidence.scoring_protocol_digest,
        prior_policy_digest=evidence.prior_policy_digest,
        connected_neighborhood_map_digest=evidence.connected_neighborhood_map_digest,
        config_digest=config_digest,
        prior_mass_accounting=accounting,
        development_limitations=evidence.development_limitations,
        optional_family_availability=availability,
        rolling_summaries=tuple(summaries),
        final_summary=summaries[-1],
        final_hypothesis_posterior=final_hypothesis_posterior,
        nuisance_model_reference_digests=nuisance_models,
        nuisance_state_reference_digests=nuisance_states,
        change_point_model_reference_digests=change_point_models,
        change_point_reference_digests=change_points,
        result_digest=canonical_digest(payload),
    )


def verify_long_arc_hypothesis_closure_result(
    result: LongArcHypothesisClosureResult,
) -> None:
    """Fail closed if a persisted result no longer matches its content digest."""

    payload = asdict(result)
    result_digest = payload.pop("result_digest")
    if result_digest != canonical_digest(payload):
        raise LongArcHypothesisClosureInputError("closure result digest differs")
    if not result.rolling_summaries or result.final_summary != result.rolling_summaries[-1]:
        raise LongArcHypothesisClosureInputError("closure final summary is not the final prefix")


def _validate_evidence(
    evidence: LongArcHypothesisClosureEvidence,
    config: LongArcHypothesisClosureConfig,
) -> None:
    hypothesis_count = len(evidence.hypotheses)
    block_count = len(evidence.blocks)
    score_cell_count = hypothesis_count * block_count
    if hypothesis_count > config.maximum_hypotheses:
        raise LongArcHypothesisClosureWorkLimitError("hypothesis work cap exceeded")
    if block_count > config.maximum_blocks:
        raise LongArcHypothesisClosureWorkLimitError("calendar-block work cap exceeded")
    if score_cell_count > config.maximum_score_cells:
        raise LongArcHypothesisClosureWorkLimitError("score-cell work cap exceeded")
    expected_content = canonical_digest(
        {
            "sequence_label": evidence.sequence_label,
            "graph_content_digest": evidence.graph_content_digest,
            "scoring_protocol_digest": evidence.scoring_protocol_digest,
            "prior_policy_digest": evidence.prior_policy_digest,
            "connected_neighborhood_map_digest": evidence.connected_neighborhood_map_digest,
            "hypotheses": tuple(asdict(item) for item in evidence.hypotheses),
            "block_digests": tuple(item.block_digest for item in evidence.blocks),
            "pruned_prior_mass": evidence.pruned_prior_mass,
            "unresolved_prior_mass": evidence.unresolved_prior_mass,
            "development_limitations": evidence.development_limitations,
        }
    )
    if evidence.content_digest != expected_content:
        raise LongArcHypothesisClosureInputError("closure evidence digest differs")
    hypothesis_ids = tuple(item.hypothesis_id for item in evidence.hypotheses)
    if len(set(hypothesis_ids)) != len(hypothesis_ids):
        raise LongArcHypothesisClosureInputError("hypothesis inventory contains duplicates")
    families = tuple(item.family for item in evidence.hypotheses)
    if "h0-radio-null" not in families or "h1-single-candidate" not in families:
        raise LongArcHypothesisClosureInputError("explicit H0 and persistent H1 are required")
    _prior_mass_accounting(evidence, config)
    prior_observations: set[str] = set()
    preceding_blocks: list[LongArcChronologicalScoreBlock] = []
    prior_end: int | None = None
    block_ids: set[str] = set()
    for block in evidence.blocks:
        if block.block_id in block_ids:
            raise LongArcHypothesisClosureInputError("chronological blocks repeat an identity")
        block_ids.add(block.block_id)
        if prior_end is not None and block.block_start_utc_ns < prior_end:
            raise LongArcHypothesisClosureInputError(
                "calendar score blocks overlap or are not chronological"
            )
        prior_end = block.block_end_utc_ns
        if prior_observations.intersection(block.observation_ids):
            raise LongArcHypothesisClosureInputError("chronological blocks repeat an observation")
        prior_observations.update(block.observation_ids)
        expected_inventory = observation_inventory_digest(
            block_id=block.block_id,
            block_start_utc_ns=block.block_start_utc_ns,
            block_end_utc_ns=block.block_end_utc_ns,
            observation_ids=block.observation_ids,
        )
        if block.observation_inventory_digest != expected_inventory:
            raise LongArcHypothesisClosureInputError("block observation inventory differs")
        expected_history = conditioning_history_digest(tuple(preceding_blocks))
        if block.conditioning_history_digest != expected_history:
            raise LongArcHypothesisClosureInputError(
                "block conditioning history is non-causal or differs"
            )
        expected_block_digest = canonical_digest(
            {
                "block_id": block.block_id,
                "block_start_utc_ns": block.block_start_utc_ns,
                "block_end_utc_ns": block.block_end_utc_ns,
                "observation_ids": block.observation_ids,
                "observation_inventory_digest": block.observation_inventory_digest,
                "conditioning_history_digest": block.conditioning_history_digest,
                "scores": tuple(asdict(item) for item in block.scores),
            }
        )
        if block.block_digest != expected_block_digest:
            raise LongArcHypothesisClosureInputError("chronological block digest differs")
        score_ids = tuple(item.hypothesis_id for item in block.scores)
        if score_ids != hypothesis_ids:
            raise LongArcHypothesisClosureInputError(
                "every block must score the exact ordered hypothesis inventory"
            )
        for hypothesis, score in zip(evidence.hypotheses, block.scores, strict=True):
            if score.scored_observation_inventory_digest != block.observation_inventory_digest:
                raise LongArcHypothesisClosureInputError(
                    "hypothesis scores do not share one common block inventory"
                )
            if (
                score.score_kind != "proper-log-predictive-density"
                or score.future_response_used_for_fit
                or not score.scored_once_without_refit
            ):
                raise LongArcHypothesisClosureInputError(
                    "all inputs must be frozen proper future scores without refit"
                )
            if hypothesis.family == "h1-switch":
                if score.change_point_reference_digest is None:
                    raise LongArcHypothesisClosureInputError(
                        "H1-switch block scores require change-point references"
                    )
            elif score.change_point_reference_digest is not None:
                raise LongArcHypothesisClosureInputError(
                    "only H1-switch scores may carry change-point references"
                )
        preceding_blocks.append(block)


def _prior_mass_accounting(
    evidence: LongArcHypothesisClosureEvidence,
    config: LongArcHypothesisClosureConfig,
) -> LongArcPriorMassAccounting:
    evaluated_log = _log_sum_exp(
        tuple(item.normalized_log_prior_probability for item in evidence.hypotheses)
    )
    h0_radio_or_unassigned_log = _log_sum_exp(
        tuple(
            item.normalized_log_prior_probability
            for item in evidence.hypotheses
            if item.family == "h0-radio-null"
        )
    )
    candidate_log = _log_sum_exp(
        tuple(
            item.normalized_log_prior_probability
            for item in evidence.hypotheses
            if item.family != "h0-radio-null"
        )
    )
    evaluated = math.exp(evaluated_log)
    h0_radio_or_unassigned = math.exp(h0_radio_or_unassigned_log)
    candidate = math.exp(candidate_log)
    outside = math.fsum((evidence.pruned_prior_mass, evidence.unresolved_prior_mass))
    accounted = math.fsum((h0_radio_or_unassigned, candidate, outside))
    if not all(
        math.isfinite(item)
        for item in (
            evaluated,
            h0_radio_or_unassigned,
            candidate,
            outside,
            accounted,
        )
    ):
        raise LongArcHypothesisClosureInputError("prior-mass accounting is not finite")
    if evaluated <= 0.0:
        raise LongArcHypothesisClosureInputError("evaluated prior mass must be positive")
    normalization_terms = [item.normalized_log_prior_probability for item in evidence.hypotheses]
    normalization_terms.extend(
        math.log(item)
        for item in (evidence.pruned_prior_mass, evidence.unresolved_prior_mass)
        if item > 0.0
    )
    normalized_log_total = _log_sum_exp(tuple(normalization_terms))
    if not math.isclose(
        normalized_log_total,
        0.0,
        rel_tol=0.0,
        abs_tol=config.prior_normalization_tolerance,
    ):
        raise LongArcHypothesisClosureInputError(
            "evaluated, pruned, and unresolved priors must sum to one"
        )
    return LongArcPriorMassAccounting(
        evaluated_prior_mass=evaluated,
        log_evaluated_prior_mass=evaluated_log,
        evaluated_candidate_prior_mass=candidate,
        log_evaluated_candidate_prior_mass=candidate_log,
        h0_radio_or_unassigned_prior_mass=h0_radio_or_unassigned,
        log_h0_radio_or_unassigned_prior_mass=h0_radio_or_unassigned_log,
        pruned_prior_mass=evidence.pruned_prior_mass,
        unresolved_prior_mass=evidence.unresolved_prior_mass,
        outside_evaluated_prior_mass=outside,
        accounted_prior_mass=accounted,
        normalization_residual=1.0 - accounted,
    )


def _optional_family_availability(
    hypotheses: tuple[LongArcHypothesisPrior, ...],
) -> tuple[LongArcOptionalFamilyAvailability, ...]:
    rows: list[LongArcOptionalFamilyAvailability] = []
    for family in _OPTIONAL_FAMILIES:
        states = tuple(item for item in hypotheses if item.family == family)
        present = bool(states)
        log_prior_mass = (
            _log_sum_exp(tuple(item.normalized_log_prior_probability for item in states))
            if present
            else None
        )
        rows.append(
            LongArcOptionalFamilyAvailability(
                family=family,
                status="evaluated" if present else "structurally-inapplicable",
                evaluated_state_count=len(states),
                evaluated_prior_mass=(
                    math.exp(log_prior_mass) if log_prior_mass is not None else 0.0
                ),
                log_evaluated_prior_mass=log_prior_mass,
                reason=(
                    "explicit-states-present"
                    if present
                    else "no-explicit-state-in-frozen-inventory"
                ),
            )
        )
    return tuple(rows)


def _summarize_block(
    *,
    block_index: int,
    block: LongArcChronologicalScoreBlock,
    first_start_utc_ns: int,
    cumulative_observation_count: int,
    cumulative_scores: tuple[float, ...],
    posterior: tuple[float, ...],
    hypotheses: tuple[LongArcHypothesisPrior, ...],
    accounting: LongArcPriorMassAccounting,
    config: LongArcHypothesisClosureConfig,
    block_log_evidence: float,
    cumulative_log_evidence: float,
    include_connected_neighborhood_summary: bool,
    development_limitations: tuple[ClosureDevelopmentLimitation, ...],
) -> tuple[
    LongArcPrequentialClosureSummary,
    tuple[LongArcHypothesisPosteriorMass, ...],
]:
    state_rows = tuple(
        LongArcHypothesisPosteriorMass(
            hypothesis_id=hypothesis.hypothesis_id,
            family=hypothesis.family,
            connected_neighborhood_label=hypothesis.connected_neighborhood_label,
            catalog_numbers=hypothesis.catalog_numbers,
            tau_s=hypothesis.tau_s,
            normalized_log_prior_probability=(hypothesis.normalized_log_prior_probability),
            prior_probability=hypothesis.prior_probability,
            prior_probability_representable=(hypothesis.prior_probability_representable),
            posterior_probability=probability,
            cumulative_proper_log_score=cumulative_score,
            nuisance_model_reference_digest=hypothesis.nuisance_model_reference_digest,
            nuisance_state_reference_digest=score.nuisance_state_reference_digest,
            change_point_model_reference_digest=(hypothesis.change_point_model_reference_digest),
            change_point_reference_digest=score.change_point_reference_digest,
            score_reference_digest=score.score_reference_digest,
        )
        for hypothesis, score, probability, cumulative_score in zip(
            hypotheses,
            block.scores,
            posterior,
            cumulative_scores,
            strict=True,
        )
    )
    family_rows = tuple(
        LongArcFamilyPosteriorMass(
            family=family,
            evaluated_state_count=sum(item.family == family for item in hypotheses),
            posterior_probability=math.fsum(
                row.posterior_probability for row in state_rows if row.family == family
            ),
        )
        for family in _FAMILY_ORDER
    )
    neighborhood_rows: tuple[LongArcConnectedNeighborhoodPosteriorMass, ...] = ()
    neighborhood_entropy: float | None = None
    candidate_neighborhood_entropy: float | None = None
    effective_neighborhood_count: float | None = None
    outcome: LongArcClosureOutcomeSummary | None = None
    if include_connected_neighborhood_summary:
        candidate_probability = math.fsum(
            item.posterior_probability for item in state_rows if item.family != "h0-radio-null"
        )
        neighborhood_keys = sorted(
            {(item.family, item.connected_neighborhood_label) for item in hypotheses},
            key=lambda item: (_FAMILY_ORDER.index(item[0]), item[1]),
        )
        neighborhood_rows = tuple(
            LongArcConnectedNeighborhoodPosteriorMass(
                family=family,
                connected_neighborhood_label=label,
                evaluated_state_count=sum(
                    item.family == family and item.connected_neighborhood_label == label
                    for item in hypotheses
                ),
                catalog_numbers=tuple(
                    sorted(
                        {
                            catalog_number
                            for item in hypotheses
                            if item.family == family and item.connected_neighborhood_label == label
                            for catalog_number in item.catalog_numbers
                        }
                    )
                ),
                posterior_probability=(
                    neighborhood_probability := math.fsum(
                        item.posterior_probability
                        for item in state_rows
                        if item.family == family and item.connected_neighborhood_label == label
                    )
                ),
                within_candidate_probability=(
                    neighborhood_probability / candidate_probability
                    if family != "h0-radio-null" and candidate_probability > 0.0
                    else None
                ),
            )
            for family, label in neighborhood_keys
        )
        outcome = _classify_outcome(
            neighborhood_rows=neighborhood_rows,
            family_rows=family_rows,
            accounting=accounting,
            config=config,
            development_limitations=development_limitations,
        )
        candidate_probabilities = tuple(
            item.within_candidate_probability
            for item in neighborhood_rows
            if item.within_candidate_probability is not None
        )
        candidate_neighborhood_entropy = _entropy(candidate_probabilities)
        neighborhood_entropy = _entropy(
            tuple(item.posterior_probability for item in neighborhood_rows)
        )
        effective_neighborhood_count = math.exp(candidate_neighborhood_entropy)
        if not math.isfinite(effective_neighborhood_count):
            raise LongArcHypothesisClosureNumericalError(
                "effective candidate-neighborhood count is not representable"
            )
    return (
        LongArcPrequentialClosureSummary(
            block_index=block_index,
            block_id=block.block_id,
            block_start_utc_ns=block.block_start_utc_ns,
            block_end_utc_ns=block.block_end_utc_ns,
            cumulative_duration_s=(block.block_end_utc_ns - first_start_utc_ns) / 1e9,
            cumulative_observation_count=cumulative_observation_count,
            block_log_predictive_evidence_conditioned_on_evaluated=block_log_evidence,
            cumulative_log_evidence_conditioned_on_evaluated=cumulative_log_evidence,
            family_posterior=family_rows,
            connected_neighborhood_summary_status=(
                "available-final-prefix"
                if include_connected_neighborhood_summary
                else "suppressed-final-prefix-map"
            ),
            connected_neighborhood_posterior=neighborhood_rows,
            hypothesis_entropy_nats=_entropy(posterior),
            family_entropy_nats=_entropy(tuple(item.posterior_probability for item in family_rows)),
            connected_neighborhood_entropy_nats=neighborhood_entropy,
            candidate_connected_neighborhood_entropy_nats=(candidate_neighborhood_entropy),
            effective_candidate_connected_neighborhood_count=(effective_neighborhood_count),
            outcome=outcome,
        ),
        state_rows,
    )


def _classify_outcome(
    *,
    neighborhood_rows: tuple[LongArcConnectedNeighborhoodPosteriorMass, ...],
    family_rows: tuple[LongArcFamilyPosteriorMass, ...],
    accounting: LongArcPriorMassAccounting,
    config: LongArcHypothesisClosureConfig,
    development_limitations: tuple[ClosureDevelopmentLimitation, ...],
) -> LongArcClosureOutcomeSummary:
    h0_radio_or_unassigned_probability = next(
        item.posterior_probability for item in family_rows if item.family == "h0-radio-null"
    )
    candidate_probability = 1.0 - h0_radio_or_unassigned_probability
    candidate_rows = tuple(
        sorted(
            (item for item in neighborhood_rows if item.family != "h0-radio-null"),
            key=lambda item: (
                -(item.within_candidate_probability or 0.0),
                _FAMILY_ORDER.index(item.family),
                item.connected_neighborhood_label,
            ),
        )
    )
    credible: list[LongArcConnectedNeighborhoodPosteriorMass] = []
    accumulated = 0.0
    for item in candidate_rows:
        credible.append(item)
        accumulated += item.within_candidate_probability or 0.0
        if accumulated + 1e-15 >= config.credible_neighborhood_probability:
            break
    if "incomplete-opportunity-inventory" in development_limitations:
        outcome: ClosureOutcome = "unresolved"
        reason: OutcomeReason = "incomplete-opportunity-inventory"
    elif (
        accounting.outside_evaluated_prior_mass
        > config.maximum_outside_prior_mass_for_resolved_outcome
    ):
        outcome = "unresolved"
        reason = "outside-evaluated-prior-mass"
    elif candidate_probability < config.minimum_candidate_posterior_probability:
        outcome = "unresolved"
        reason = "radio-or-unassigned-competitive"
    elif (
        len(credible) == 1
        and (credible[0].within_candidate_probability or 0.0)
        >= config.singleton_minimum_within_candidate_probability
        and len(credible[0].catalog_numbers) > 1
    ):
        outcome = "ambiguity"
        reason = "connected-neighborhood-contains-multiple-catalogues"
    elif (
        len(credible) == 1
        and (credible[0].within_candidate_probability or 0.0)
        >= config.singleton_minimum_within_candidate_probability
        and len(credible[0].catalog_numbers) == 1
    ):
        outcome = "singleton"
        reason = "single-catalogue-connected-neighborhood-meets-policy"
    elif len(credible) > 1:
        outcome = "ambiguity"
        reason = "multiple-connected-neighborhoods-required"
    else:
        outcome = "unresolved"
        reason = "candidate-neighborhood-mass-diffuse"
    return LongArcClosureOutcomeSummary(
        outcome=outcome,
        reason=reason,
        candidate_posterior_probability=candidate_probability,
        h0_radio_or_unassigned_posterior_probability=(h0_radio_or_unassigned_probability),
        outside_evaluated_prior_mass=accounting.outside_evaluated_prior_mass,
        credible_connected_neighborhoods=tuple(credible),
        credible_neighborhood_probability_target=config.credible_neighborhood_probability,
        singleton_minimum_within_candidate_probability=(
            config.singleton_minimum_within_candidate_probability
        ),
        minimum_candidate_posterior_probability=(config.minimum_candidate_posterior_probability),
    )


def _log_sum_exp(values: tuple[float, ...]) -> float:
    maximum = max(values)
    try:
        shifted_sum = math.fsum(math.exp(item - maximum) for item in values)
        result = maximum + math.log(shifted_sum)
    except (OverflowError, ValueError) as error:
        raise LongArcHypothesisClosureNumericalError(
            "prequential log normalization is not representable"
        ) from error
    if not math.isfinite(result):
        raise LongArcHypothesisClosureNumericalError("prequential log normalization is not finite")
    return result


def _normalized_probabilities(
    log_weights: tuple[float, ...],
    log_normalizer: float,
) -> tuple[float, ...]:
    try:
        unnormalized = tuple(math.exp(item - log_normalizer) for item in log_weights)
        total = math.fsum(unnormalized)
    except OverflowError as error:
        raise LongArcHypothesisClosureNumericalError(
            "posterior probabilities are not representable"
        ) from error
    if not math.isfinite(total) or total <= 0.0:
        raise LongArcHypothesisClosureNumericalError(
            "posterior normalization is not finite and positive"
        )
    probabilities = tuple(item / total for item in unnormalized)
    if any(not math.isfinite(item) or item < 0.0 for item in probabilities):
        raise LongArcHypothesisClosureNumericalError("posterior probabilities are invalid")
    return probabilities


def _entropy(probabilities: tuple[float, ...]) -> float:
    entropy = -math.fsum(item * math.log(item) for item in probabilities if item > 0.0)
    if not math.isfinite(entropy) or entropy < -1e-15:
        raise LongArcHypothesisClosureNumericalError("posterior entropy is invalid")
    return max(0.0, entropy)


def _is_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    suffix = value.removeprefix("sha256:")
    return len(suffix) == 64 and all(item in "0123456789abcdef" for item in suffix)
