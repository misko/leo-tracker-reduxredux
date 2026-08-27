"""Pure orchestration seams for C2/C3 long-arc checkpoint evidence.

This module converts one already-registered physical CFO graph and one exact,
response-free true-time catalogue bank into the common block-prequential model
inventory introduced for checkpoint C2.  It keeps every candidate and tau
state, adds line/quadratic/cubic radio-only states and an explicit null, and
uses one block covariance policy and one receiver offset/drift nuisance basis
for every family. Radio states add transmitter-polynomial freedom only beyond
that shared receiver basis.

Execution authority, TLE access, candidate population selection, persistence,
figures, and report prose remain outside this module.  C3 closure is performed
by a separate reducer after response-free C1 candidate-identity component labels
are profiled over the complete independent tau-state cross product and propagated
across each candidate's tau states.  A connected neighborhood is a single-linkage
component, not a claim of pairwise indistinguishability.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from typing import Literal, cast

from leo.analysis.catalogue_prediction_array_view import CataloguePredictionArrayBankView
from leo.analysis.research.block_predictive_evidence import (
    BlockPredictiveEvidenceConfig,
    BlockPredictiveEvidenceResult,
    BlockPredictiveObservation,
    CalendarBlockCovariance,
    FamilyPriorWeight,
    FrozenLinearGaussianState,
    FrozenStateObservationModel,
    StateObservationModelProvider,
    block_predictive_evidence_result_payload,
    hypothesis_inventory_digest,
    observation_inventory_digest,
    score_block_predictive_evidence,
)
from leo.analysis.research.long_arc_hypothesis_closure import (
    LongArcChronologicalScoreBlock,
    LongArcHypothesisBlockLogScore,
    LongArcHypothesisClosureConfig,
    LongArcHypothesisClosureResult,
    LongArcHypothesisPrior,
    close_long_arc_hypotheses,
    seal_chronological_score_block,
    seal_long_arc_hypothesis_closure_evidence,
)
from leo.analysis.research.long_arc_hypothesis_closure import (
    observation_inventory_digest as closure_observation_inventory_digest,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    PhysicalEpisodeGraphV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

type StateKind = Literal["null", "catalogue", "radio"]
type C2Family = Literal["null", "catalogue-orbit", "radio-polynomial"]

_C2_C3_BRIDGE_VERSION = "registered-long-arc-c2-to-c3-bridge-v1"
_C2_FAMILIES: tuple[C2Family, C2Family, C2Family] = (
    "null",
    "catalogue-orbit",
    "radio-polynomial",
)


class SatelliteTrackingCheckpointInputError(ValueError):
    """The graph, bank, priors, covariance, or partition is invalid."""


@dataclass(frozen=True, slots=True)
class LongArcBlockEvidenceDesign:
    """Frozen common-evidence design for one opened long arc."""

    covariance: CalendarBlockCovariance
    receiver_nuisance_prior_authority_digest: Sha256Digest
    family_log_weights: tuple[float, float, float] = (0.0, 0.0, 0.0)
    training_block_fraction: float = 0.6
    calendar_block_duration_ns: int = 1_000_000_000
    receiver_offset_prior_sigma_hz: float = 1_000_000.0
    receiver_drift_prior_sigma_hz_per_s: float = 20.0
    radio_structural_parameter_prior_sigmas: tuple[float, float, float] = (
        20_000.0,
        2_000.0,
        200.0,
    )
    minimum_usable_evaluation_observations: int = 2
    minimum_usable_evaluation_blocks: int = 2
    minimum_evaluation_observation_coverage: float = 1.0
    minimum_evaluation_block_coverage: float = 1.0
    maximum_hypothesis_count: int = 25_000
    maximum_state_observation_evaluations: int = 30_000_000
    receiver_nuisance_parameters_calibrated: Literal[False] = field(default=False, init=False)

    def __post_init__(self) -> None:
        if len(self.family_log_weights) != 3 or any(
            not math.isfinite(item) for item in self.family_log_weights
        ):
            raise SatelliteTrackingCheckpointInputError(
                "null/catalogue/radio family weights must be three finite values"
            )
        if (
            not math.isfinite(self.training_block_fraction)
            or not 0.0 < self.training_block_fraction < 1.0
            or isinstance(self.calendar_block_duration_ns, bool)
            or not isinstance(self.calendar_block_duration_ns, int)
            or self.calendar_block_duration_ns <= 0
        ):
            raise SatelliteTrackingCheckpointInputError(
                "training fraction or calendar-block duration is invalid"
            )
        if not _is_digest(self.receiver_nuisance_prior_authority_digest):
            raise SatelliteTrackingCheckpointInputError(
                "receiver nuisance prior authority must be digest-bound"
            )
        if len(self.radio_structural_parameter_prior_sigmas) != 3:
            raise SatelliteTrackingCheckpointInputError(
                "radio structural priors require slope, acceleration, and jerk sigmas"
            )
        sigmas = (
            self.receiver_offset_prior_sigma_hz,
            self.receiver_drift_prior_sigma_hz_per_s,
            *self.radio_structural_parameter_prior_sigmas,
        )
        if any(not math.isfinite(item) or item <= 0.0 for item in sigmas):
            raise SatelliteTrackingCheckpointInputError(
                "all nuisance priors must be proper, finite, and positive"
            )
        integer_controls = (
            self.minimum_usable_evaluation_observations,
            self.minimum_usable_evaluation_blocks,
            self.maximum_hypothesis_count,
            self.maximum_state_observation_evaluations,
        )
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in integer_controls
        ):
            raise SatelliteTrackingCheckpointInputError(
                "coverage minima and work caps must be positive integers"
            )
        for value in (
            self.minimum_evaluation_observation_coverage,
            self.minimum_evaluation_block_coverage,
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise SatelliteTrackingCheckpointInputError("coverage fractions must lie in [0,1]")

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class LongArcStateReceipt:
    state_id: Sha256Digest
    state_kind: StateKind
    family: Literal["null", "catalogue-orbit", "radio-polynomial"]
    catalog_number: int | None
    tau_s: float | None
    polynomial_degree: int | None
    model_authority_digest: Sha256Digest
    receiver_nuisance_basis_digest: Sha256Digest
    structural_parameter_count: int
    receiver_nuisance_parameter_count: Literal[2] = field(default=2, init=False)


@dataclass(frozen=True, slots=True)
class LongArcBlockEvidenceRun:
    graph_content_digest: Sha256Digest
    prediction_bank_content_digest: Sha256Digest
    design_digest: Sha256Digest
    receiver_nuisance_basis_digest: Sha256Digest
    training_observation_ids: tuple[Sha256Digest, ...]
    evaluation_observation_ids: tuple[Sha256Digest, ...]
    state_receipts: tuple[LongArcStateReceipt, ...]
    evidence: BlockPredictiveEvidenceResult
    content_digest: Sha256Digest
    algorithm_version: Literal["registered-long-arc-block-evidence-v1"] = field(
        default="registered-long-arc-block-evidence-v1", init=False
    )
    full_catalogue_tau_inventory_scored: Literal[True] = field(default=True, init=False)
    common_block_covariance_used: Literal[True] = field(default=True, init=False)
    common_receiver_nuisance_basis_used: Literal[True] = field(default=True, init=False)
    receiver_nuisance_parameters_calibrated: Literal[False] = field(default=False, init=False)
    opportunity_inventory_complete: Literal[False] = field(default=False, init=False)
    missing_opportunities_retained: Literal[False] = field(default=False, init=False)
    coverage_conditioned_on_observed_rows: Literal[True] = field(default=True, init=False)
    posterior_claim_abstained: Literal[True] = field(default=True, init=False)
    posterior_probability_calibrated: Literal[False] = field(default=False, init=False)
    empirical_calibration_applied: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class LongArcCatalogueConnectedNeighborhoodReceipt:
    """A C2 catalogue×tau state carrying its profiled C1 candidate component."""

    state_id: Sha256Digest
    catalog_number: int
    tau_s: float
    connected_neighborhood_label: Sha256Digest

    def __post_init__(self) -> None:
        if not _is_digest(self.state_id) or not _is_digest(self.connected_neighborhood_label):
            raise SatelliteTrackingCheckpointInputError(
                "C1 state and connected-neighborhood identities must be digest-bound"
            )
        if (
            isinstance(self.catalog_number, bool)
            or not isinstance(self.catalog_number, int)
            or self.catalog_number <= 0
            or type(self.tau_s) is not float
            or not math.isfinite(self.tau_s)
        ):
            raise SatelliteTrackingCheckpointInputError("C1 catalogue/tau receipt is invalid")


@dataclass(frozen=True, slots=True)
class LongArcCatalogueConnectedNeighborhoodBinding:
    """Digest-closed profiled-tau C1 candidate components for exact C2 states.

    C1 joins two catalogue identities when any independently allowed pair of
    tau states lies within the declared floor after the common offset-plus-ridge-
    drift nuisance projection.  Every catalogue×tau C2 receipt for one candidate
    carries the resulting candidate-level single-linkage component label.
    """

    source_observability_result_digest: Sha256Digest
    source_profiled_tau_atlas_digest: Sha256Digest
    prediction_bank_content_digest: Sha256Digest
    c2_receiver_nuisance_basis_digest: Sha256Digest
    tau_values_s: tuple[float, ...]
    nuisance_model: Literal["offset-plus-ridge-drift-v1"]
    drift_prior_sigma_hz_per_s: float
    reference_measurement_sigma_hz: float
    floor_history_ms: float
    floor_hz: float
    floor_source_digest: Sha256Digest
    floor_calibrated: Literal[False]
    complete_tau_cross_product_evaluated: Literal[True]
    tau_pairing_semantics: Literal["independent-complete-cross-product-minimum-v1"]
    candidate_node_semantics: Literal["one-node-per-catalogue-identity-all-tau-states-unified-v1"]
    threshold_graph_semantics: Literal["edge-if-any-profiled-state-pair-within-floor-v1"]
    identity_gate_applied: Literal[False]
    receipts: tuple[LongArcCatalogueConnectedNeighborhoodReceipt, ...]
    content_digest: Sha256Digest
    response_free: Literal[True] = field(default=True, init=False)

    def __post_init__(self) -> None:
        for value in (
            self.source_observability_result_digest,
            self.source_profiled_tau_atlas_digest,
            self.prediction_bank_content_digest,
            self.c2_receiver_nuisance_basis_digest,
            self.floor_source_digest,
            self.content_digest,
        ):
            if not _is_digest(value):
                raise SatelliteTrackingCheckpointInputError(
                    "C1 connected-neighborhood binding must be digest-bound"
                )
        if not self.receipts:
            raise SatelliteTrackingCheckpointInputError(
                "C1 connected-neighborhood binding cannot be empty"
            )
        if (
            not isinstance(self.tau_values_s, tuple)
            or not self.tau_values_s
            or any(type(item) is not float or not math.isfinite(item) for item in self.tau_values_s)
            or tuple(sorted(set(self.tau_values_s))) != self.tau_values_s
        ):
            raise SatelliteTrackingCheckpointInputError(
                "C1 profiled-tau binding requires one exact ordered finite tau grid"
            )
        if self.nuisance_model != "offset-plus-ridge-drift-v1":
            raise SatelliteTrackingCheckpointInputError(
                "C1 profiled-tau binding requires the offset-plus-ridge-drift nuisance"
            )
        for numeric_value, label in (
            (self.drift_prior_sigma_hz_per_s, "drift prior sigma"),
            (self.reference_measurement_sigma_hz, "reference measurement sigma"),
            (self.floor_hz, "measurement floor"),
        ):
            if (
                type(numeric_value) is not float
                or not math.isfinite(numeric_value)
                or numeric_value <= 0.0
            ):
                raise SatelliteTrackingCheckpointInputError(
                    f"C1 profiled-tau {label} must be an exact positive float"
                )
        if type(self.floor_history_ms) is not float or self.floor_history_ms != 125.0:
            raise SatelliteTrackingCheckpointInputError(
                "C1 profiled-tau binding requires the exact 125 ms floor overlay"
            )
        if self.floor_calibrated is not False or self.identity_gate_applied is not False:
            raise SatelliteTrackingCheckpointInputError(
                "C1 profiled-tau floor must remain uncalibrated and descriptive"
            )
        if self.complete_tau_cross_product_evaluated is not True:
            raise SatelliteTrackingCheckpointInputError(
                "C1 profiled-tau binding requires the complete tau cross product"
            )
        if self.tau_pairing_semantics != "independent-complete-cross-product-minimum-v1":
            raise SatelliteTrackingCheckpointInputError("C1 profiled-tau pairing semantics differ")
        if (
            self.candidate_node_semantics
            != "one-node-per-catalogue-identity-all-tau-states-unified-v1"
            or self.threshold_graph_semantics != "edge-if-any-profiled-state-pair-within-floor-v1"
        ):
            raise SatelliteTrackingCheckpointInputError("C1 profiled-tau graph semantics differ")
        if self.response_free is not True:
            raise SatelliteTrackingCheckpointInputError(
                "C1 connected-neighborhood binding must remain response-free"
            )
        if not isinstance(self.receipts, tuple) or len(
            {item.state_id for item in self.receipts}
        ) != len(self.receipts):
            raise SatelliteTrackingCheckpointInputError(
                "C1 profiled-tau receipts must have unique state identities"
            )
        catalog_numbers = {item.catalog_number for item in self.receipts}
        for catalog_number in catalog_numbers:
            candidate_receipts = tuple(
                item for item in self.receipts if item.catalog_number == catalog_number
            )
            if tuple(sorted(item.tau_s for item in candidate_receipts)) != self.tau_values_s:
                raise SatelliteTrackingCheckpointInputError(
                    "each C1 candidate requires exactly the profiled tau grid"
                )
            if len({item.connected_neighborhood_label for item in candidate_receipts}) != 1:
                raise SatelliteTrackingCheckpointInputError(
                    "C1 profiled candidate component labels must propagate across tau states"
                )


def seal_long_arc_catalogue_connected_neighborhood_binding(
    *,
    source_observability_result_digest: Sha256Digest,
    source_profiled_tau_atlas_digest: Sha256Digest,
    prediction_bank_content_digest: Sha256Digest,
    c2_receiver_nuisance_basis_digest: Sha256Digest,
    tau_values_s: tuple[float, ...],
    nuisance_model: Literal["offset-plus-ridge-drift-v1"],
    drift_prior_sigma_hz_per_s: float,
    reference_measurement_sigma_hz: float,
    floor_history_ms: float,
    floor_hz: float,
    floor_source_digest: Sha256Digest,
    floor_calibrated: Literal[False],
    complete_tau_cross_product_evaluated: Literal[True],
    tau_pairing_semantics: Literal["independent-complete-cross-product-minimum-v1"],
    candidate_node_semantics: Literal["one-node-per-catalogue-identity-all-tau-states-unified-v1"],
    threshold_graph_semantics: Literal["edge-if-any-profiled-state-pair-within-floor-v1"],
    identity_gate_applied: Literal[False],
    receipts: tuple[LongArcCatalogueConnectedNeighborhoodReceipt, ...],
) -> LongArcCatalogueConnectedNeighborhoodBinding:
    """Seal exact profiled-tau candidate labels across the C2 tau inventory."""

    validated = LongArcCatalogueConnectedNeighborhoodBinding(
        source_observability_result_digest=source_observability_result_digest,
        source_profiled_tau_atlas_digest=source_profiled_tau_atlas_digest,
        prediction_bank_content_digest=prediction_bank_content_digest,
        c2_receiver_nuisance_basis_digest=c2_receiver_nuisance_basis_digest,
        tau_values_s=tau_values_s,
        nuisance_model=nuisance_model,
        drift_prior_sigma_hz_per_s=drift_prior_sigma_hz_per_s,
        reference_measurement_sigma_hz=reference_measurement_sigma_hz,
        floor_history_ms=floor_history_ms,
        floor_hz=floor_hz,
        floor_source_digest=floor_source_digest,
        floor_calibrated=floor_calibrated,
        complete_tau_cross_product_evaluated=complete_tau_cross_product_evaluated,
        tau_pairing_semantics=tau_pairing_semantics,
        candidate_node_semantics=candidate_node_semantics,
        threshold_graph_semantics=threshold_graph_semantics,
        identity_gate_applied=identity_gate_applied,
        receipts=receipts,
        # This temporary valid digest permits strict numerical validation before
        # canonical JSON is asked to encode any caller-controlled floats.
        content_digest=source_observability_result_digest,
    )
    body = {
        "source_observability_result_digest": validated.source_observability_result_digest,
        "source_profiled_tau_atlas_digest": validated.source_profiled_tau_atlas_digest,
        "prediction_bank_content_digest": validated.prediction_bank_content_digest,
        "c2_receiver_nuisance_basis_digest": (validated.c2_receiver_nuisance_basis_digest),
        "tau_values_s": validated.tau_values_s,
        "nuisance_model": validated.nuisance_model,
        "drift_prior_sigma_hz_per_s": validated.drift_prior_sigma_hz_per_s,
        "reference_measurement_sigma_hz": validated.reference_measurement_sigma_hz,
        "floor_history_ms": validated.floor_history_ms,
        "floor_hz": validated.floor_hz,
        "floor_source_digest": validated.floor_source_digest,
        "floor_calibrated": validated.floor_calibrated,
        "complete_tau_cross_product_evaluated": (validated.complete_tau_cross_product_evaluated),
        "tau_pairing_semantics": validated.tau_pairing_semantics,
        "candidate_node_semantics": validated.candidate_node_semantics,
        "threshold_graph_semantics": validated.threshold_graph_semantics,
        "identity_gate_applied": validated.identity_gate_applied,
        "receipts": tuple(asdict(item) for item in validated.receipts),
        "response_free": True,
    }
    return replace(validated, content_digest=canonical_digest(body))


def score_registered_long_arc_model_families(
    graph: PhysicalEpisodeGraphV1,
    prediction_bank: CataloguePredictionBankV1 | CataloguePredictionArrayBankView,
    *,
    design: LongArcBlockEvidenceDesign,
) -> LongArcBlockEvidenceRun:
    """Score NULL, every catalogue×tau state, and radio degrees 1/2/3."""

    graph = _revalidate_graph(graph)
    bank = _revalidate_bank(prediction_bank)
    design = _revalidate_design(design)
    expected_support = CataloguePredictionSupportV1.from_graph(graph)
    if bank.support.content_digest != expected_support.content_digest:
        raise SatelliteTrackingCheckpointInputError(
            "prediction bank does not bind the supplied physical graph"
        )
    if len(graph.episodes) != 1:
        raise SatelliteTrackingCheckpointInputError(
            "V1 checkpoint scoring requires one registered physical episode"
        )
    observations = _observations(graph)
    training_ids, evaluation_ids = _block_aligned_partition(
        observations,
        duration_ns=design.calendar_block_duration_ns,
        training_fraction=design.training_block_fraction,
    )
    states, receipts, receiver_nuisance_basis_digest, array_state_axes = _states(
        observations,
        bank,
        design,
    )
    observation_digest = observation_inventory_digest(observations)
    hypothesis_digest = hypothesis_inventory_digest(states)
    config = BlockPredictiveEvidenceConfig(
        training_observation_ids=training_ids,
        evaluation_observation_ids=evaluation_ids,
        expected_observation_inventory_digest=observation_digest,
        expected_hypothesis_inventory_digest=hypothesis_digest,
        family_prior_weights=tuple(
            FamilyPriorWeight(family=family, log_weight=weight)
            for family, weight in zip(
                _C2_FAMILIES,
                design.family_log_weights,
                strict=True,
            )
        ),
        covariance=design.covariance,
        opportunity_inventory_complete=False,
        calendar_block_duration_ns=design.calendar_block_duration_ns,
        minimum_usable_evaluation_observations=(design.minimum_usable_evaluation_observations),
        minimum_usable_evaluation_blocks=design.minimum_usable_evaluation_blocks,
        minimum_evaluation_observation_coverage=(design.minimum_evaluation_observation_coverage),
        minimum_evaluation_block_coverage=design.minimum_evaluation_block_coverage,
        maximum_observation_count=4_096,
        maximum_hypothesis_count=design.maximum_hypothesis_count,
        maximum_parameter_count=5,
        maximum_rows_per_calendar_block=2_048,
        maximum_state_observation_evaluations=(design.maximum_state_observation_evaluations),
    )
    if array_state_axes is None:
        evidence = score_block_predictive_evidence(observations, states, config=config)
    else:
        if not isinstance(bank, CataloguePredictionArrayBankView):
            raise AssertionError("array state axes require an array prediction-bank view")
        evidence = score_block_predictive_evidence(
            observations,
            states,
            config=config,
            external_model_provider=_array_model_provider(
                observations=observations,
                bank=bank,
                state_axes=array_state_axes,
            ),
        )
    bank_content_digest = _prediction_bank_content_digest(bank)
    body = {
        "graph_content_digest": graph.content_digest,
        "prediction_bank_content_digest": bank_content_digest,
        "design_digest": design.content_digest,
        "receiver_nuisance_basis_digest": receiver_nuisance_basis_digest,
        "training_observation_ids": training_ids,
        "evaluation_observation_ids": evaluation_ids,
        "state_receipts": tuple(asdict(item) for item in receipts),
        "evidence_result_digest": evidence.result_digest,
        "algorithm_version": "registered-long-arc-block-evidence-v1",
        "full_catalogue_tau_inventory_scored": True,
        "common_block_covariance_used": True,
        "common_receiver_nuisance_basis_used": True,
        "receiver_nuisance_parameters_calibrated": False,
        "opportunity_inventory_complete": False,
        "missing_opportunities_retained": False,
        "coverage_conditioned_on_observed_rows": True,
        "posterior_claim_abstained": True,
        "posterior_probability_calibrated": False,
        "empirical_calibration_applied": False,
        "identity_claimed": False,
    }
    return LongArcBlockEvidenceRun(
        graph_content_digest=graph.content_digest,
        prediction_bank_content_digest=bank_content_digest,
        design_digest=design.content_digest,
        receiver_nuisance_basis_digest=receiver_nuisance_basis_digest,
        training_observation_ids=training_ids,
        evaluation_observation_ids=evaluation_ids,
        state_receipts=receipts,
        evidence=evidence,
        content_digest=canonical_digest(body),
    )


def long_arc_block_evidence_run_payload(
    result: LongArcBlockEvidenceRun,
) -> dict[str, object]:
    """Return the complete nested result after checking both content digests."""

    block_predictive_evidence_result_payload(result.evidence)
    document = asdict(result)
    claimed = document.pop("content_digest")
    body = {
        "graph_content_digest": result.graph_content_digest,
        "prediction_bank_content_digest": result.prediction_bank_content_digest,
        "design_digest": result.design_digest,
        "receiver_nuisance_basis_digest": result.receiver_nuisance_basis_digest,
        "training_observation_ids": result.training_observation_ids,
        "evaluation_observation_ids": result.evaluation_observation_ids,
        "state_receipts": tuple(asdict(item) for item in result.state_receipts),
        "evidence_result_digest": result.evidence.result_digest,
        "algorithm_version": result.algorithm_version,
        "full_catalogue_tau_inventory_scored": True,
        "common_block_covariance_used": True,
        "common_receiver_nuisance_basis_used": True,
        "receiver_nuisance_parameters_calibrated": False,
        "opportunity_inventory_complete": False,
        "missing_opportunities_retained": False,
        "coverage_conditioned_on_observed_rows": True,
        "posterior_claim_abstained": True,
        "posterior_probability_calibrated": False,
        "empirical_calibration_applied": False,
        "identity_claimed": False,
    }
    if claimed != canonical_digest(body):
        raise SatelliteTrackingCheckpointInputError(
            "long-arc block-evidence run digest does not close"
        )
    return {**document, "content_digest": claimed}


def close_long_arc_block_evidence_run(
    run: LongArcBlockEvidenceRun,
    *,
    sequence_label: str,
    connected_neighborhood_binding: LongArcCatalogueConnectedNeighborhoodBinding,
    closure_config: LongArcHypothesisClosureConfig | None = None,
) -> LongArcHypothesisClosureResult:
    """Map one sealed C2 run into the pure C3 prequential closure reducer.

    C2 training posterior log masses become C3 priors.  Each chronological C2
    evaluation negative log likelihood becomes one C3 proper log score with
    the sign reversed.  The bridge never recomputes a score, reads RF, changes
    a candidate inventory, or creates switch/K2 states.
    """

    if not sequence_label.strip():
        raise SatelliteTrackingCheckpointInputError("C3 closure sequence label cannot be empty")
    _validate_c2_c3_bridge_inputs(run, connected_neighborhood_binding)
    source_states = {item.state_id: item for item in run.evidence.states}
    source_receipts = {item.state_id: item for item in run.state_receipts}
    ordered_receipts = tuple(source_receipts[item.state_id] for item in run.evidence.states)
    neighborhood_by_state = {
        item.state_id: item for item in connected_neighborhood_binding.receipts
    }
    hypotheses = tuple(
        _closure_hypothesis(
            receipt,
            source_states[receipt.state_id].normalized_log_model_mass_after_training,
            neighborhood_by_state,
        )
        for receipt in ordered_receipts
    )
    initial_nuisance_references = {
        receipt.state_id: canonical_digest(
            {
                "bridge_version": _C2_C3_BRIDGE_VERSION,
                "kind": "c2-training-nuisance-posterior-v1",
                "state_id": receipt.state_id,
                "model_authority_digest": receipt.model_authority_digest,
                "training_observation_ids": run.training_observation_ids,
                "training_predictive_negative_log_likelihood": (
                    source_states[receipt.state_id].training_predictive_negative_log_likelihood
                ),
                "training_parameter_posterior_mean": source_states[
                    receipt.state_id
                ].training_parameter_posterior_mean,
                "training_parameter_posterior_covariance": source_states[
                    receipt.state_id
                ].training_parameter_posterior_covariance,
                "normalized_log_model_mass_after_training": source_states[
                    receipt.state_id
                ].normalized_log_model_mass_after_training,
                "covariance_policy_digest": run.evidence.covariance_policy_digest,
            }
        )
        for receipt in ordered_receipts
    }
    nuisance_references = dict(initial_nuisance_references)
    closure_blocks: list[LongArcChronologicalScoreBlock] = []
    for source_block in run.evidence.blocks:
        block_observation_ids = source_block.observation_ids
        block_id = canonical_digest(
            {
                "bridge_version": _C2_C3_BRIDGE_VERSION,
                "source_block_index": source_block.block_index,
                "block_start_utc_ns": source_block.block_start_utc_ns,
                "block_end_utc_ns": source_block.block_end_utc_ns,
                "observation_ids": block_observation_ids,
            }
        )
        inventory_digest = closure_observation_inventory_digest(
            block_id=block_id,
            block_start_utc_ns=source_block.block_start_utc_ns,
            block_end_utc_ns=source_block.block_end_utc_ns,
            observation_ids=block_observation_ids,
        )
        closure_scores = tuple(
            LongArcHypothesisBlockLogScore(
                hypothesis_id=receipt.state_id,
                proper_log_score=-source_score.predictive_negative_log_likelihood,
                score_reference_digest=canonical_digest(
                    {
                        "bridge_version": _C2_C3_BRIDGE_VERSION,
                        "source_block_index": source_block.block_index,
                        "block_start_utc_ns": source_block.block_start_utc_ns,
                        "block_end_utc_ns": source_block.block_end_utc_ns,
                        "observation_inventory_digest": inventory_digest,
                        "state_receipt": asdict(receipt),
                        "source_state_block_score": asdict(source_score),
                        "nuisance_state_reference_digest": nuisance_references[receipt.state_id],
                        "covariance_policy_digest": (run.evidence.covariance_policy_digest),
                    }
                ),
                scored_observation_inventory_digest=inventory_digest,
                nuisance_state_reference_digest=nuisance_references[receipt.state_id],
            )
            for receipt, source_score in zip(
                ordered_receipts,
                source_block.state_scores,
                strict=True,
            )
        )
        closure_block = seal_chronological_score_block(
            block_id=block_id,
            block_start_utc_ns=source_block.block_start_utc_ns,
            block_end_utc_ns=source_block.block_end_utc_ns,
            observation_ids=block_observation_ids,
            scores=closure_scores,
            preceding_blocks=tuple(closure_blocks),
        )
        closure_blocks.append(closure_block)
        nuisance_references = {
            receipt.state_id: canonical_digest(
                {
                    "bridge_version": _C2_C3_BRIDGE_VERSION,
                    "kind": "c2-causal-nuisance-update-reference-v1",
                    "prior_nuisance_state_reference_digest": (
                        nuisance_references[receipt.state_id]
                    ),
                    "score_reference_digest": score.score_reference_digest,
                    "block_digest": closure_block.block_digest,
                }
            )
            for receipt, score in zip(
                ordered_receipts,
                closure_scores,
                strict=True,
            )
        }
    scoring_protocol_digest = canonical_digest(
        {
            "bridge_version": _C2_C3_BRIDGE_VERSION,
            "source_run_content_digest": run.content_digest,
            "source_c2_algorithm_version": run.evidence.algorithm_version,
            "source_hypothesis_inventory_digest": (run.evidence.hypothesis_inventory_digest),
            "source_covariance_policy_digest": run.evidence.covariance_policy_digest,
        }
    )
    prior_policy_digest = canonical_digest(
        {
            "bridge_version": _C2_C3_BRIDGE_VERSION,
            "policy": "c2-normalized-training-log-mass-as-c3-prior-v1",
            "source_design_digest": run.design_digest,
            "training_observation_ids": run.training_observation_ids,
            "state_log_priors": tuple(
                (
                    item.state_id,
                    item.normalized_log_model_mass_after_training,
                )
                for item in run.evidence.states
            ),
            "training_nuisance_reference_digests": tuple(
                initial_nuisance_references[item.state_id] for item in ordered_receipts
            ),
        }
    )
    closure_evidence = seal_long_arc_hypothesis_closure_evidence(
        sequence_label=sequence_label,
        graph_content_digest=run.graph_content_digest,
        scoring_protocol_digest=scoring_protocol_digest,
        prior_policy_digest=prior_policy_digest,
        connected_neighborhood_map_digest=connected_neighborhood_binding.content_digest,
        hypotheses=hypotheses,
        blocks=tuple(closure_blocks),
        development_limitations=("incomplete-opportunity-inventory",),
    )
    if closure_config is None:
        closure_config = LongArcHypothesisClosureConfig(
            maximum_hypotheses=len(hypotheses),
            maximum_blocks=len(closure_blocks),
            maximum_score_cells=len(hypotheses) * len(closure_blocks),
        )
    return close_long_arc_hypotheses(closure_evidence, closure_config)


def _closure_hypothesis(
    receipt: LongArcStateReceipt,
    normalized_log_prior_probability: float,
    neighborhood_by_state: dict[str, LongArcCatalogueConnectedNeighborhoodReceipt],
) -> LongArcHypothesisPrior:
    if receipt.state_kind == "catalogue":
        neighborhood = neighborhood_by_state[receipt.state_id]
        assert receipt.catalog_number is not None
        assert receipt.tau_s is not None
        return LongArcHypothesisPrior(
            hypothesis_id=receipt.state_id,
            family="h1-single-candidate",
            normalized_log_prior_probability=normalized_log_prior_probability,
            connected_neighborhood_label=neighborhood.connected_neighborhood_label,
            catalog_numbers=(receipt.catalog_number,),
            tau_s=(receipt.tau_s,),
            nuisance_model_reference_digest=receipt.model_authority_digest,
        )
    return LongArcHypothesisPrior(
        hypothesis_id=receipt.state_id,
        family="h0-radio-null",
        normalized_log_prior_probability=normalized_log_prior_probability,
        connected_neighborhood_label="h0-radio-null",
        catalog_numbers=(),
        tau_s=(),
        nuisance_model_reference_digest=receipt.model_authority_digest,
    )


def _validate_c2_c3_bridge_inputs(
    run: LongArcBlockEvidenceRun,
    binding: LongArcCatalogueConnectedNeighborhoodBinding,
) -> None:
    try:
        long_arc_block_evidence_run_payload(run)
    except (AttributeError, TypeError, ValueError) as error:
        raise SatelliteTrackingCheckpointInputError(
            "source C2 long-arc run does not digest-close"
        ) from error
    try:
        validated_binding = LongArcCatalogueConnectedNeighborhoodBinding(
            source_observability_result_digest=(binding.source_observability_result_digest),
            source_profiled_tau_atlas_digest=(binding.source_profiled_tau_atlas_digest),
            prediction_bank_content_digest=binding.prediction_bank_content_digest,
            c2_receiver_nuisance_basis_digest=(binding.c2_receiver_nuisance_basis_digest),
            tau_values_s=tuple(binding.tau_values_s),
            nuisance_model=binding.nuisance_model,
            drift_prior_sigma_hz_per_s=binding.drift_prior_sigma_hz_per_s,
            reference_measurement_sigma_hz=binding.reference_measurement_sigma_hz,
            floor_history_ms=binding.floor_history_ms,
            floor_hz=binding.floor_hz,
            floor_source_digest=binding.floor_source_digest,
            floor_calibrated=binding.floor_calibrated,
            complete_tau_cross_product_evaluated=(binding.complete_tau_cross_product_evaluated),
            tau_pairing_semantics=binding.tau_pairing_semantics,
            candidate_node_semantics=binding.candidate_node_semantics,
            threshold_graph_semantics=binding.threshold_graph_semantics,
            identity_gate_applied=binding.identity_gate_applied,
            receipts=tuple(
                LongArcCatalogueConnectedNeighborhoodReceipt(
                    state_id=item.state_id,
                    catalog_number=item.catalog_number,
                    tau_s=item.tau_s,
                    connected_neighborhood_label=item.connected_neighborhood_label,
                )
                for item in binding.receipts
            ),
            content_digest=binding.content_digest,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise SatelliteTrackingCheckpointInputError(
            "C1 profiled-tau connected-neighborhood binding is invalid"
        ) from error
    if validated_binding != binding:
        raise SatelliteTrackingCheckpointInputError(
            "C1 profiled-tau connected-neighborhood binding is invalid"
        )
    binding_body = {
        "source_observability_result_digest": (binding.source_observability_result_digest),
        "source_profiled_tau_atlas_digest": binding.source_profiled_tau_atlas_digest,
        "prediction_bank_content_digest": binding.prediction_bank_content_digest,
        "c2_receiver_nuisance_basis_digest": binding.c2_receiver_nuisance_basis_digest,
        "tau_values_s": binding.tau_values_s,
        "nuisance_model": binding.nuisance_model,
        "drift_prior_sigma_hz_per_s": binding.drift_prior_sigma_hz_per_s,
        "reference_measurement_sigma_hz": binding.reference_measurement_sigma_hz,
        "floor_history_ms": binding.floor_history_ms,
        "floor_hz": binding.floor_hz,
        "floor_source_digest": binding.floor_source_digest,
        "floor_calibrated": binding.floor_calibrated,
        "complete_tau_cross_product_evaluated": (binding.complete_tau_cross_product_evaluated),
        "tau_pairing_semantics": binding.tau_pairing_semantics,
        "candidate_node_semantics": binding.candidate_node_semantics,
        "threshold_graph_semantics": binding.threshold_graph_semantics,
        "identity_gate_applied": binding.identity_gate_applied,
        "receipts": tuple(asdict(item) for item in binding.receipts),
        "response_free": True,
    }
    if binding.content_digest != canonical_digest(binding_body):
        raise SatelliteTrackingCheckpointInputError(
            "C1 connected-neighborhood binding digest does not close"
        )
    if binding.prediction_bank_content_digest != run.prediction_bank_content_digest:
        raise SatelliteTrackingCheckpointInputError(
            "C1 connected-neighborhood binding uses a different prediction bank"
        )
    if binding.c2_receiver_nuisance_basis_digest != run.receiver_nuisance_basis_digest:
        raise SatelliteTrackingCheckpointInputError(
            "C1 profiled-tau binding uses a different C2 receiver nuisance basis"
        )
    if not _is_digest(run.receiver_nuisance_basis_digest):
        raise SatelliteTrackingCheckpointInputError(
            "C2 shared receiver nuisance basis must be digest-bound"
        )
    if (
        run.evidence.opportunity_inventory_complete
        or run.evidence.missing_opportunities_retained
        or not run.evidence.coverage_conditioned_on_observed_rows
        or not run.evidence.abstention_recommended
        or "incomplete-opportunity-inventory" not in run.evidence.abstention_diagnostics
        or run.evidence.evaluation_observation_coverage is not None
        or run.evidence.evaluation_block_coverage is not None
    ):
        raise SatelliteTrackingCheckpointInputError(
            "C2 source must abstain for its incomplete opportunity inventory"
        )
    if not run.evidence.exact_common_observation_inventory:
        raise SatelliteTrackingCheckpointInputError(
            "C2 source does not attest one common observation inventory"
        )
    if (
        not run.evidence.score_before_assimilate
        or not run.evidence.hierarchical_family_state_priors_normalized
    ):
        raise SatelliteTrackingCheckpointInputError("C2 source is not causal or prior-normalized")
    if run.evidence.identity_claimed or run.identity_claimed:
        raise SatelliteTrackingCheckpointInputError(
            "C2 source contains an unsupported identity claim"
        )
    if (
        len(run.training_observation_ids) != run.evidence.training_observation_count
        or len(run.evaluation_observation_ids) != run.evidence.evaluation_observation_count
    ):
        raise SatelliteTrackingCheckpointInputError("C2 run observation receipt counts differ")
    all_observation_ids = (
        *run.training_observation_ids,
        *run.evaluation_observation_ids,
    )
    if any(not _is_digest(item) for item in all_observation_ids) or len(
        set(all_observation_ids)
    ) != len(all_observation_ids):
        raise SatelliteTrackingCheckpointInputError(
            "C2 run observations must be unique digest-bound receipts"
        )
    source_receipt_ids = tuple(item.state_id for item in run.state_receipts)
    source_state_ids = tuple(item.state_id for item in run.evidence.states)
    if (
        not source_receipt_ids
        or len(set(source_receipt_ids)) != len(source_receipt_ids)
        or set(source_receipt_ids) != set(source_state_ids)
    ):
        raise SatelliteTrackingCheckpointInputError(
            "C2 state receipts must match the exact scored inventory"
        )
    receipt_by_id = {item.state_id: item for item in run.state_receipts}
    ordered_receipts = tuple(receipt_by_id[item.state_id] for item in run.evidence.states)
    for receipt, state in zip(ordered_receipts, run.evidence.states, strict=True):
        _validate_state_receipt(
            receipt,
            prediction_bank_content_digest=run.prediction_bank_content_digest,
            receiver_nuisance_basis_digest=run.receiver_nuisance_basis_digest,
            design_digest=run.design_digest,
        )
        if receipt.family != state.family:
            raise SatelliteTrackingCheckpointInputError(
                "C2 state receipt family differs from its score summary"
            )
        log_mass = state.normalized_log_model_mass_after_training
        if not math.isfinite(log_mass) or log_mass > 0.0:
            raise SatelliteTrackingCheckpointInputError(
                "C2 training posterior log masses must be finite and normalized"
            )
        if not math.isclose(
            math.exp(log_mass),
            state.normalized_model_mass_after_training,
            rel_tol=1e-12,
            abs_tol=0.0,
        ):
            raise SatelliteTrackingCheckpointInputError(
                "C2 linear and log training posterior masses differ"
            )
    if not math.isclose(
        _finite_log_sum_exp(
            tuple(item.normalized_log_model_mass_after_training for item in run.evidence.states)
        ),
        0.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise SatelliteTrackingCheckpointInputError(
            "C2 training posterior log masses are not normalized"
        )
    if len(run.evidence.blocks) != run.evidence.evaluation_calendar_block_count:
        raise SatelliteTrackingCheckpointInputError("C2 evaluation block receipt count differs")
    previous_end: int | None = None
    block_observation_ids: list[Sha256Digest] = []
    for block in run.evidence.blocks:
        if block.block_end_utc_ns <= block.block_start_utc_ns or (
            previous_end is not None and block.block_start_utc_ns < previous_end
        ):
            raise SatelliteTrackingCheckpointInputError(
                "C2 evaluation blocks are not chronological and disjoint"
            )
        previous_end = block.block_end_utc_ns
        if (
            len(block.observation_ids) != block.opportunity_count
            or len(set(block.observation_ids)) != len(block.observation_ids)
            or any(not _is_digest(item) for item in block.observation_ids)
        ):
            raise SatelliteTrackingCheckpointInputError(
                "C2 block observation receipts differ from its opportunity count"
            )
        block_observation_ids.extend(block.observation_ids)
        block_score_ids = tuple(item.state_id for item in block.state_scores)
        if block_score_ids != source_state_ids:
            raise SatelliteTrackingCheckpointInputError(
                "C2 block does not score the exact ordered state inventory"
            )
        if any(
            item.family != receipt.family
            or not math.isfinite(item.predictive_negative_log_likelihood)
            or item.usable_observation_count != block.usable_observation_count
            for receipt, item in zip(
                ordered_receipts,
                block.state_scores,
                strict=True,
            )
        ):
            raise SatelliteTrackingCheckpointInputError(
                "C2 block state scores or common row counts differ"
            )
    if tuple(block_observation_ids) != run.evaluation_observation_ids:
        raise SatelliteTrackingCheckpointInputError(
            "C2 evaluation blocks do not bind the exact ordered opportunity inventory"
        )
    block_durations = {
        item.block_end_utc_ns - item.block_start_utc_ns for item in run.evidence.blocks
    }
    if len(block_durations) != 1:
        raise SatelliteTrackingCheckpointInputError(
            "C2 evaluation blocks do not share one calendar duration"
        )
    expected_partition_digest = canonical_digest(
        {
            "algorithm_version": run.evidence.algorithm_version,
            "observation_inventory_digest": run.evidence.observation_inventory_digest,
            "training_observation_ids": run.training_observation_ids,
            "evaluation_observation_ids": run.evaluation_observation_ids,
            "calendar_block_duration_ns": next(iter(block_durations)),
        }
    )
    if run.evidence.observation_partition_digest != expected_partition_digest:
        raise SatelliteTrackingCheckpointInputError(
            "C2 training/evaluation observation partition digest differs"
        )
    catalogue_receipts = tuple(
        item for item in run.state_receipts if item.state_kind == "catalogue"
    )
    binding_ids = tuple(item.state_id for item in binding.receipts)
    if len(set(binding_ids)) != len(binding_ids) or set(binding_ids) != {
        item.state_id for item in catalogue_receipts
    }:
        raise SatelliteTrackingCheckpointInputError(
            "C1 receipts must cover catalogue states exactly one-to-one"
        )
    receipt_by_id = {item.state_id: item for item in catalogue_receipts}
    for neighborhood in binding.receipts:
        source = receipt_by_id[neighborhood.state_id]
        if (
            source.catalog_number != neighborhood.catalog_number
            or source.tau_s != neighborhood.tau_s
        ):
            raise SatelliteTrackingCheckpointInputError(
                "C1 connected-neighborhood receipt catalogue/tau identity differs"
            )


def _validate_state_receipt(
    receipt: LongArcStateReceipt,
    *,
    prediction_bank_content_digest: Sha256Digest,
    receiver_nuisance_basis_digest: Sha256Digest,
    design_digest: Sha256Digest,
) -> None:
    if (
        not _is_digest(receipt.state_id)
        or not _is_digest(receipt.model_authority_digest)
        or receipt.receiver_nuisance_basis_digest != receiver_nuisance_basis_digest
    ):
        raise SatelliteTrackingCheckpointInputError("C2 state receipts must be digest-bound")
    expected_authority: Sha256Digest | None
    if receipt.state_kind == "null":
        expected_authority = canonical_digest(
            {
                "model": "zero-curve-plus-shared-receiver-nuisance-v1",
                "receiver_nuisance_basis_digest": receiver_nuisance_basis_digest,
            }
        )
        valid = (
            receipt.family == "null"
            and receipt.catalog_number is None
            and receipt.tau_s is None
            and receipt.polynomial_degree is None
            and receipt.structural_parameter_count == 0
            and receipt.model_authority_digest == expected_authority
        )
    elif receipt.state_kind == "catalogue":
        expected_authority = (
            _catalogue_model_authority_digest(
                prediction_bank_content_digest=prediction_bank_content_digest,
                receiver_nuisance_basis_digest=receiver_nuisance_basis_digest,
                catalog_number=receipt.catalog_number,
                tau_s=receipt.tau_s,
            )
            if isinstance(receipt.catalog_number, int)
            and not isinstance(receipt.catalog_number, bool)
            and receipt.tau_s is not None
            and math.isfinite(receipt.tau_s)
            else None
        )
        valid = (
            receipt.family == "catalogue-orbit"
            and isinstance(receipt.catalog_number, int)
            and not isinstance(receipt.catalog_number, bool)
            and receipt.catalog_number > 0
            and receipt.tau_s is not None
            and math.isfinite(receipt.tau_s)
            and receipt.polynomial_degree is None
            and receipt.structural_parameter_count == 0
            and receipt.model_authority_digest == expected_authority
        )
    elif receipt.state_kind == "radio":
        expected_authority = canonical_digest(
            {
                "model": "shared-receiver-plus-radio-polynomial-v1",
                "receiver_nuisance_basis_digest": receiver_nuisance_basis_digest,
                "design_digest": design_digest,
                "degree": receipt.polynomial_degree,
            }
        )
        valid = (
            receipt.family == "radio-polynomial"
            and receipt.catalog_number is None
            and receipt.tau_s is None
            and receipt.polynomial_degree in (1, 2, 3)
            and receipt.structural_parameter_count == receipt.polynomial_degree
            and receipt.model_authority_digest == expected_authority
        )
    else:
        valid = False
    if not valid:
        raise SatelliteTrackingCheckpointInputError("C2 state receipt kind and metadata differ")
    expected_state_id = _state_id(
        family=receipt.family,
        model_authority_digest=receipt.model_authority_digest,
        catalog_number=receipt.catalog_number,
        tau_s=receipt.tau_s,
        polynomial_degree=receipt.polynomial_degree,
    )
    if receipt.state_id != expected_state_id:
        raise SatelliteTrackingCheckpointInputError(
            "C2 state receipt identity is not canonical for its declared model"
        )


def _finite_log_sum_exp(values: tuple[float, ...]) -> float:
    if not values or any(not math.isfinite(item) for item in values):
        raise SatelliteTrackingCheckpointInputError(
            "normalized log mass inventory must be finite and nonempty"
        )
    maximum = max(values)
    total = math.fsum(math.exp(item - maximum) for item in values)
    result = maximum + math.log(total)
    if not math.isfinite(result):
        raise SatelliteTrackingCheckpointInputError(
            "normalized log mass inventory is not representable"
        )
    return result


def _observations(
    graph: PhysicalEpisodeGraphV1,
) -> tuple[BlockPredictiveObservation, ...]:
    return tuple(
        BlockPredictiveObservation(
            observation_id=item.observation_id,
            support_start_utc_ns=item.support_start_utc_ns,
            support_center_utc_ns=item.support_center_utc_ns,
            support_end_utc_ns=item.support_end_utc_ns,
            status="usable",
            measured_cfo_hz=item.measured_cfo_hz,
            standard_uncertainty_hz=item.standard_uncertainty_hz,
        )
        for item in sorted(
            graph.observations,
            key=lambda row: (row.support_center_utc_ns, row.observation_id),
        )
    )


def _block_aligned_partition(
    observations: tuple[BlockPredictiveObservation, ...],
    *,
    duration_ns: int,
    training_fraction: float,
) -> tuple[tuple[Sha256Digest, ...], tuple[Sha256Digest, ...]]:
    block_ids = tuple(sorted({item.support_center_utc_ns // duration_ns for item in observations}))
    if len(block_ids) < 4:
        raise SatelliteTrackingCheckpointInputError(
            "block evidence needs at least four calendar blocks"
        )
    training_count = math.floor(len(block_ids) * training_fraction + 0.5)
    training_count = min(max(training_count, 1), len(block_ids) - 1)
    training_blocks = set(block_ids[:training_count])
    training = tuple(
        item.observation_id
        for item in observations
        if item.support_center_utc_ns // duration_ns in training_blocks
    )
    evaluation = tuple(
        item.observation_id
        for item in observations
        if item.support_center_utc_ns // duration_ns not in training_blocks
    )
    if len(training) < 2 or len(evaluation) < 2:
        raise SatelliteTrackingCheckpointInputError(
            "block-aligned partition lacks training or evaluation rows"
        )
    return training, evaluation


def _states(
    observations: tuple[BlockPredictiveObservation, ...],
    bank: CataloguePredictionBankV1 | CataloguePredictionArrayBankView,
    design: LongArcBlockEvidenceDesign,
) -> tuple[
    tuple[FrozenLinearGaussianState, ...],
    tuple[LongArcStateReceipt, ...],
    Sha256Digest,
    dict[Sha256Digest, tuple[int, int]] | None,
]:
    observation_ids = tuple(item.observation_id for item in observations)
    reference_ns = observations[0].support_center_utc_ns
    times_s = tuple((item.support_center_utc_ns - reference_ns) / 1e9 for item in observations)
    states: list[FrozenLinearGaussianState] = []
    receipts: list[LongArcStateReceipt] = []
    array_state_axes: dict[Sha256Digest, tuple[int, int]] | None = (
        {} if isinstance(bank, CataloguePredictionArrayBankView) else None
    )
    shared_sigmas = (
        design.receiver_offset_prior_sigma_hz,
        design.receiver_drift_prior_sigma_hz_per_s,
    )
    receiver_nuisance_basis_digest = canonical_digest(
        {
            "schema": "org.leo.research.shared-receiver-offset-linear-drift/v1",
            "reference_utc_ns": reference_ns,
            "parameter_names": ("receiver_offset_hz", "receiver_linear_drift_hz_per_s"),
            "parameter_prior_sigmas": shared_sigmas,
            "prior_authority_digest": design.receiver_nuisance_prior_authority_digest,
            "parameters_calibrated": False,
            "design_basis": ("1", "seconds-from-reference"),
        }
    )

    null_authority = canonical_digest(
        {
            "model": "zero-curve-plus-shared-receiver-nuisance-v1",
            "receiver_nuisance_basis_digest": receiver_nuisance_basis_digest,
        }
    )
    null_id = _state_id(
        family="null",
        model_authority_digest=null_authority,
        catalog_number=None,
        tau_s=None,
        polynomial_degree=None,
    )
    states.append(
        FrozenLinearGaussianState(
            state_id=null_id,
            family="null",
            model_authority_digest=null_authority,
            log_prior_weight_within_family=0.0,
            parameter_prior_mean=(0.0, 0.0),
            parameter_prior_covariance=_diagonal_prior_covariance(shared_sigmas),
            observation_models=tuple(
                FrozenStateObservationModel(
                    observation_id=observation_id,
                    base_prediction_hz=0.0,
                    design_row=_shared_receiver_design(time_s),
                )
                for observation_id, time_s in zip(observation_ids, times_s, strict=True)
            ),
        )
    )
    receipts.append(
        LongArcStateReceipt(
            state_id=null_id,
            state_kind="null",
            family="null",
            catalog_number=None,
            tau_s=None,
            polynomial_degree=None,
            model_authority_digest=null_authority,
            receiver_nuisance_basis_digest=receiver_nuisance_basis_digest,
            structural_parameter_count=0,
        )
    )

    if isinstance(bank, CataloguePredictionArrayBankView):
        if bank.observation_ids != tuple(sorted(observation_ids)):
            raise SatelliteTrackingCheckpointInputError(
                "array-backed catalogue state does not cover the exact graph inventory"
            )
        assert array_state_axes is not None
        for candidate_index, array_candidate in enumerate(bank.candidate_authority):
            for tau_index, array_tau_state in enumerate(bank.tau_authority):
                model_authority = _catalogue_model_authority_digest(
                    prediction_bank_content_digest=bank.public_bank_content_digest,
                    receiver_nuisance_basis_digest=receiver_nuisance_basis_digest,
                    catalog_number=array_candidate.catalog_number,
                    tau_s=array_tau_state.tau_s,
                )
                state_id = _state_id(
                    family="catalogue-orbit",
                    model_authority_digest=model_authority,
                    catalog_number=array_candidate.catalog_number,
                    tau_s=array_tau_state.tau_s,
                    polynomial_degree=None,
                )
                states.append(
                    FrozenLinearGaussianState(
                        state_id=state_id,
                        family="catalogue-orbit",
                        model_authority_digest=model_authority,
                        log_prior_weight_within_family=array_tau_state.log_prior_weight,
                        parameter_prior_mean=(0.0, 0.0),
                        parameter_prior_covariance=_diagonal_prior_covariance(shared_sigmas),
                        observation_models=(),
                        prediction_inventory_reference_digest=(
                            bank.prediction_inventory_authority_digest
                        ),
                    )
                )
                receipts.append(
                    LongArcStateReceipt(
                        state_id=state_id,
                        state_kind="catalogue",
                        family="catalogue-orbit",
                        catalog_number=array_candidate.catalog_number,
                        tau_s=array_tau_state.tau_s,
                        polynomial_degree=None,
                        model_authority_digest=model_authority,
                        receiver_nuisance_basis_digest=receiver_nuisance_basis_digest,
                        structural_parameter_count=0,
                    )
                )
                array_state_axes[state_id] = (candidate_index, tau_index)
    else:
        for public_candidate in bank.candidates:
            for public_tau_state in public_candidate.tau_states:
                prediction_by_id = {
                    item.observation_id: item for item in public_tau_state.predictions
                }
                if len(prediction_by_id) != len(public_tau_state.predictions) or set(
                    prediction_by_id
                ) != set(observation_ids):
                    raise SatelliteTrackingCheckpointInputError(
                        "catalogue state does not cover the exact graph inventory"
                    )
                model_authority = _catalogue_model_authority_digest(
                    prediction_bank_content_digest=bank.content_digest,
                    receiver_nuisance_basis_digest=receiver_nuisance_basis_digest,
                    catalog_number=public_candidate.catalog_number,
                    tau_s=public_tau_state.tau_s,
                )
                state_id = _state_id(
                    family="catalogue-orbit",
                    model_authority_digest=model_authority,
                    catalog_number=public_candidate.catalog_number,
                    tau_s=public_tau_state.tau_s,
                    polynomial_degree=None,
                )
                states.append(
                    FrozenLinearGaussianState(
                        state_id=state_id,
                        family="catalogue-orbit",
                        model_authority_digest=model_authority,
                        log_prior_weight_within_family=public_tau_state.log_prior_weight,
                        parameter_prior_mean=(0.0, 0.0),
                        parameter_prior_covariance=_diagonal_prior_covariance(shared_sigmas),
                        observation_models=tuple(
                            FrozenStateObservationModel(
                                observation_id=observation_id,
                                base_prediction_hz=(
                                    prediction_by_id[observation_id].predicted_cfo_hz
                                ),
                                design_row=_shared_receiver_design(time_s),
                                prediction_standard_uncertainty_hz=(
                                    prediction_by_id[observation_id].standard_uncertainty_hz
                                ),
                            )
                            for observation_id, time_s in zip(observation_ids, times_s, strict=True)
                        ),
                    )
                )
                receipts.append(
                    LongArcStateReceipt(
                        state_id=state_id,
                        state_kind="catalogue",
                        family="catalogue-orbit",
                        catalog_number=public_candidate.catalog_number,
                        tau_s=public_tau_state.tau_s,
                        polynomial_degree=None,
                        model_authority_digest=model_authority,
                        receiver_nuisance_basis_digest=receiver_nuisance_basis_digest,
                        structural_parameter_count=0,
                    )
                )

    for degree in (1, 2, 3):
        structural_sigmas = design.radio_structural_parameter_prior_sigmas[:degree]
        all_sigmas = (*shared_sigmas, *structural_sigmas)
        radio_authority = canonical_digest(
            {
                "model": "shared-receiver-plus-radio-polynomial-v1",
                "receiver_nuisance_basis_digest": receiver_nuisance_basis_digest,
                "design_digest": design.content_digest,
                "degree": degree,
            }
        )
        state_id = _state_id(
            family="radio-polynomial",
            model_authority_digest=radio_authority,
            catalog_number=None,
            tau_s=None,
            polynomial_degree=degree,
        )
        states.append(
            FrozenLinearGaussianState(
                state_id=state_id,
                family="radio-polynomial",
                model_authority_digest=radio_authority,
                log_prior_weight_within_family=0.0,
                parameter_prior_mean=tuple(0.0 for _ in all_sigmas),
                parameter_prior_covariance=_diagonal_prior_covariance(all_sigmas),
                observation_models=tuple(
                    FrozenStateObservationModel(
                        observation_id=observation_id,
                        base_prediction_hz=0.0,
                        design_row=_radio_design(time_s, degree),
                    )
                    for observation_id, time_s in zip(observation_ids, times_s, strict=True)
                ),
            )
        )
        receipts.append(
            LongArcStateReceipt(
                state_id=state_id,
                state_kind="radio",
                family="radio-polynomial",
                catalog_number=None,
                tau_s=None,
                polynomial_degree=degree,
                model_authority_digest=radio_authority,
                receiver_nuisance_basis_digest=receiver_nuisance_basis_digest,
                structural_parameter_count=degree,
            )
        )
    return (
        tuple(states),
        tuple(receipts),
        receiver_nuisance_basis_digest,
        array_state_axes,
    )


def _array_model_provider(
    *,
    observations: tuple[BlockPredictiveObservation, ...],
    bank: CataloguePredictionArrayBankView,
    state_axes: dict[Sha256Digest, tuple[int, int]],
) -> StateObservationModelProvider:
    array_position = {
        observation_id: index for index, observation_id in enumerate(bank.observation_ids)
    }
    reference_ns = observations[0].support_center_utc_ns
    time_by_id = {
        item.observation_id: (item.support_center_utc_ns - reference_ns) / 1e9
        for item in observations
    }

    def provide(
        state_id: str,
        observation_ids: tuple[str, ...],
    ) -> tuple[FrozenStateObservationModel, ...]:
        candidate_index, tau_index = state_axes[state_id]
        return tuple(
            FrozenStateObservationModel(
                observation_id=observation_id,
                base_prediction_hz=float(
                    bank.predicted_cfo_hz[
                        candidate_index,
                        tau_index,
                        array_position[observation_id],
                    ]
                ),
                design_row=_shared_receiver_design(time_by_id[observation_id]),
                prediction_standard_uncertainty_hz=float(
                    bank.standard_uncertainty_hz[
                        candidate_index,
                        tau_index,
                        array_position[observation_id],
                    ]
                ),
            )
            for observation_id in observation_ids
        )

    return provide


def _shared_receiver_design(time_s: float) -> tuple[float, float]:
    return (1.0, time_s)


def _radio_design(time_s: float, degree: int) -> tuple[float, ...]:
    values = [1.0, time_s, time_s]
    if degree >= 2:
        values.append(time_s**2 / 2.0)
    if degree >= 3:
        values.append(time_s**3 / 6.0)
    return tuple(values)


def _diagonal_prior_covariance(
    sigmas: tuple[float, ...],
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(sigma**2 if row == column else 0.0 for column, sigma in enumerate(sigmas))
        for row in range(len(sigmas))
    )


def _catalogue_model_authority_digest(
    *,
    prediction_bank_content_digest: Sha256Digest,
    receiver_nuisance_basis_digest: Sha256Digest,
    catalog_number: int,
    tau_s: float,
) -> Sha256Digest:
    return canonical_digest(
        {
            "model": "prediction-bank-catalogue-state-plus-shared-receiver-nuisance-v1",
            "prediction_bank_content_digest": prediction_bank_content_digest,
            "receiver_nuisance_basis_digest": receiver_nuisance_basis_digest,
            "catalog_number": catalog_number,
            "tau_s": tau_s,
        }
    )


def _state_id(
    *,
    family: C2Family,
    model_authority_digest: Sha256Digest,
    catalog_number: int | None,
    tau_s: float | None,
    polynomial_degree: int | None,
) -> Sha256Digest:
    return canonical_digest(
        {
            "schema": "org.leo.research.registered-long-arc-state/v1",
            "family": family,
            "model_authority_digest": model_authority_digest,
            "catalog_number": catalog_number,
            "tau_s": tau_s,
            "polynomial_degree": polynomial_degree,
        }
    )


def _revalidate_graph(value: PhysicalEpisodeGraphV1) -> PhysicalEpisodeGraphV1:
    try:
        return PhysicalEpisodeGraphV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise SatelliteTrackingCheckpointInputError("physical episode graph is invalid") from error


def _revalidate_bank(
    value: CataloguePredictionBankV1 | CataloguePredictionArrayBankView,
) -> CataloguePredictionBankV1 | CataloguePredictionArrayBankView:
    if isinstance(value, CataloguePredictionArrayBankView):
        try:
            return replace(value)
        except (AttributeError, TypeError, ValueError) as error:
            raise SatelliteTrackingCheckpointInputError(
                "array-backed catalogue prediction bank is invalid"
            ) from error
    try:
        bank = CataloguePredictionBankV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise SatelliteTrackingCheckpointInputError(
            "catalogue prediction bank is invalid"
        ) from error
    if bank.response_accessed or bank.truncated_candidate_count != 0:
        raise SatelliteTrackingCheckpointInputError(
            "checkpoint scoring requires a complete response-free bank"
        )
    return bank


def _prediction_bank_content_digest(
    bank: CataloguePredictionBankV1 | CataloguePredictionArrayBankView,
) -> Sha256Digest:
    if isinstance(bank, CataloguePredictionArrayBankView):
        return bank.public_bank_content_digest
    return bank.content_digest


def _revalidate_design(value: LongArcBlockEvidenceDesign) -> LongArcBlockEvidenceDesign:
    try:
        return LongArcBlockEvidenceDesign(
            covariance=CalendarBlockCovariance(**asdict(value.covariance)),
            receiver_nuisance_prior_authority_digest=(
                value.receiver_nuisance_prior_authority_digest
            ),
            family_log_weights=cast(tuple[float, float, float], tuple(value.family_log_weights)),
            training_block_fraction=value.training_block_fraction,
            calendar_block_duration_ns=value.calendar_block_duration_ns,
            receiver_offset_prior_sigma_hz=value.receiver_offset_prior_sigma_hz,
            receiver_drift_prior_sigma_hz_per_s=(value.receiver_drift_prior_sigma_hz_per_s),
            radio_structural_parameter_prior_sigmas=cast(
                tuple[float, float, float],
                tuple(value.radio_structural_parameter_prior_sigmas),
            ),
            minimum_usable_evaluation_observations=(value.minimum_usable_evaluation_observations),
            minimum_usable_evaluation_blocks=value.minimum_usable_evaluation_blocks,
            minimum_evaluation_observation_coverage=(value.minimum_evaluation_observation_coverage),
            minimum_evaluation_block_coverage=value.minimum_evaluation_block_coverage,
            maximum_hypothesis_count=value.maximum_hypothesis_count,
            maximum_state_observation_evaluations=(value.maximum_state_observation_evaluations),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise SatelliteTrackingCheckpointInputError(
            "long-arc block-evidence design is invalid"
        ) from error


def _is_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    suffix = value.removeprefix("sha256:")
    return len(suffix) == 64 and all(item in "0123456789abcdef" for item in suffix)


__all__ = [
    "LongArcBlockEvidenceDesign",
    "LongArcBlockEvidenceRun",
    "LongArcCatalogueConnectedNeighborhoodBinding",
    "LongArcCatalogueConnectedNeighborhoodReceipt",
    "LongArcStateReceipt",
    "SatelliteTrackingCheckpointInputError",
    "close_long_arc_block_evidence_run",
    "long_arc_block_evidence_run_payload",
    "score_registered_long_arc_model_families",
    "seal_long_arc_catalogue_connected_neighborhood_binding",
]
