"""Fail-closed orchestration for one opened long-arc development analysis.

The runner first builds every response-free field population and SGP4 bank,
then consumes CFO response through predeclared chronological partitions.  It
uses the covariance-aware single-episode baseline for catalogue ranking and an
equal-row polynomial radio null for comparison.  The two wrong-epoch fields
are observations only: no threshold, p-value, veto, or identity claim is
created here.

This module is a numerical runner, not execution authority.  A separately
frozen amendment must bind its exact bytes, inputs, and output paths before it
is called on the registered opened arcs.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

from leo.analysis.catalogue_population import (
    ResponseFreeFieldPopulation,
    StarlinkHorizonPopulationPolicy,
    select_response_free_starlink_population,
)
from leo.analysis.catalogue_prediction import (
    ExactTauPolicy,
    KnownSiteRfAuthority,
    Sgp4SupportPredictionPolicy,
    SnapshotPayload,
    TauGridPoint,
    build_sgp4_catalogue_prediction_bank,
)
from leo.analysis.nearest_neighbour_association import (
    NearestNeighbourAssociationConfig,
    NearestNeighbourAssociationResult,
    NearestNeighbourHypothesisScore,
    associate_single_episode_nearest_neighbour,
)
from leo.analysis.research.radio_polynomial_null import (
    RadioPolynomialNullConfig,
    RadioPolynomialNullResult,
    score_radio_polynomial_null,
)
from leo.contracts.catalogue_association import (
    CandidateTauStateV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1

_ALGORITHM_VERSION = "opened-long-arc-catalogue-development-runner-v1"


def _execution_tau_policy() -> ExactTauPolicy:
    return ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=tuple(TauGridPoint(-5.0 + index * 0.25, 0.0) for index in range(41)),
    )


class LongArcRunnerInputError(ValueError):
    """The graph, frozen design, authority, or generated inventory is invalid."""


@dataclass(frozen=True, slots=True)
class LongArcExecutionDesign:
    selection_protocol_digest: Sha256Digest
    nominal_rf_hz: float = 11_440_312_498.0
    catalogue_fields_s: tuple[int, int, int] = (-500, 0, 500)
    main_training_fraction: float = 0.6
    rolling_training_fractions: tuple[float, float, float] = (0.4, 0.6, 0.8)
    rolling_next_fraction: float = 0.2
    nuisance_offset_prior_sigma_hz: float = 1_000_000.0
    calendar_block_duration_s: float = 1.0
    tau_policy: ExactTauPolicy = field(default_factory=_execution_tau_policy)
    population_policy: StarlinkHorizonPopulationPolicy = field(
        default_factory=StarlinkHorizonPopulationPolicy
    )
    prediction_policy: Sgp4SupportPredictionPolicy = field(
        default_factory=Sgp4SupportPredictionPolicy
    )

    def __post_init__(self) -> None:
        if self.catalogue_fields_s != (-500, 0, 500):
            raise LongArcRunnerInputError("catalogue fields must equal -500, 0, and +500 s")
        if (
            self.main_training_fraction,
            self.rolling_training_fractions,
            self.rolling_next_fraction,
        ) != (0.6, (0.4, 0.6, 0.8), 0.2):
            raise LongArcRunnerInputError("chronological fractions do not match V1")
        if (
            not math.isfinite(self.nominal_rf_hz)
            or self.nominal_rf_hz <= 0.0
            or not math.isfinite(self.nuisance_offset_prior_sigma_hz)
            or self.nuisance_offset_prior_sigma_hz <= 0.0
            or not math.isfinite(self.calendar_block_duration_s)
            or self.calendar_block_duration_s <= 0.0
        ):
            raise LongArcRunnerInputError("runner RF, nuisance, or block controls are invalid")
        if not _is_digest(self.selection_protocol_digest):
            raise LongArcRunnerInputError("selection protocol must be a tagged SHA-256 digest")
        if self.tau_policy.policy != "bounded-profile-minus5-plus5-v1" or tuple(
            item.tau_s for item in self.tau_policy.points
        ) != tuple(-5.0 + index * 0.25 for index in range(41)):
            raise LongArcRunnerInputError("tau policy must be the exact 41-state [-5,+5] grid")


@dataclass(frozen=True, slots=True)
class LongArcCandidateInventoryRow:
    catalog_number: int
    object_name: str
    selected_element_digest: Sha256Digest
    element_epoch_utc_ns: int
    element_age_s_at_reference: float


@dataclass(frozen=True, slots=True)
class LongArcFieldBankReceipt:
    field_delta_s: int
    population_receipt_digest: Sha256Digest
    selection_policy_digest: Sha256Digest
    candidate_universe_digest: Sha256Digest
    prediction_bank_digest: Sha256Digest
    candidate_count: int
    candidates: tuple[LongArcCandidateInventoryRow, ...]
    propagation_complete_for_association: Literal[True] = True


@dataclass(frozen=True, slots=True)
class LongArcCalendarBlockScore:
    block_start_utc_ns: int
    observation_count: int
    residual_rms_hz: float


@dataclass(frozen=True, slots=True)
class LongArcFieldPartitionScore:
    field_delta_s: int
    association: NearestNeighbourAssociationResult
    catalogue_future_pooled_rms_hz: float
    catalogue_future_equal_calendar_block_rms_hz: float
    catalogue_future_calendar_blocks: tuple[LongArcCalendarBlockScore, ...]


@dataclass(frozen=True, slots=True)
class LongArcWrongEpochObservation:
    field_delta_s: Literal[-500, 500]
    true_training_winner_catalog_number: int | None
    wrong_field_training_winner_catalog_number: int | None
    true_winner_future_pooled_rms_hz: float
    wrong_field_winner_future_pooled_rms_hz: float
    true_winner_future_equal_calendar_block_rms_hz: float
    wrong_field_winner_future_equal_calendar_block_rms_hz: float
    future_equal_calendar_block_rms_difference_hz: float
    future_equal_calendar_block_rms_ratio: float | None
    future_negative_log_score_difference: float
    future_mean_normalized_innovation_squared_ratio: float | None
    observe_only: Literal[True] = True


@dataclass(frozen=True, slots=True)
class LongArcOrbitRadioComparison:
    polynomial_degree: int
    orbit_future_pooled_rms_hz: float
    radio_future_pooled_rms_hz: float
    orbit_future_equal_calendar_block_rms_hz: float
    radio_future_equal_calendar_block_rms_hz: float
    radio_minus_orbit_future_equal_calendar_block_rms_hz: float
    radio_over_orbit_future_equal_calendar_block_rms_ratio: float | None
    radio_minus_orbit_predictive_negative_log_likelihood: float
    threshold_applied: Literal[False] = False


@dataclass(frozen=True, slots=True)
class LongArcPartitionResult:
    label: str
    training_fraction: float
    evaluation_end_fraction: float
    training_observation_ids: tuple[Sha256Digest, ...]
    evaluation_observation_ids: tuple[Sha256Digest, ...]
    field_scores: tuple[LongArcFieldPartitionScore, ...]
    radio_polynomial_null: RadioPolynomialNullResult
    wrong_epoch_observations: tuple[LongArcWrongEpochObservation, ...]
    orbit_radio_comparisons: tuple[LongArcOrbitRadioComparison, ...]
    partition_rounding: Literal["nearest-integer-half-up-v1"] = "nearest-integer-half-up-v1"


@dataclass(frozen=True, slots=True)
class LongArcDevelopmentRunResult:
    arc_id: str
    graph_content_digest: Sha256Digest
    prediction_support_digest: Sha256Digest
    tle_snapshot_digest: Sha256Digest
    field_banks: tuple[LongArcFieldBankReceipt, ...]
    partitions: tuple[LongArcPartitionResult, ...]
    result_digest: Sha256Digest
    algorithm_version: Literal["opened-long-arc-catalogue-development-runner-v1"] = field(
        default="opened-long-arc-catalogue-development-runner-v1", init=False
    )
    all_response_free_banks_built_before_response_scoring: Literal[True] = field(
        default=True, init=False
    )
    wrong_epoch_is_observe_only: Literal[True] = field(default=True, init=False)
    numerical_thresholds_applied: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)
    secure_norad_claimed: Literal[False] = field(default=False, init=False)
    positioning_validation_claimed: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class _FieldBank:
    population: ResponseFreeFieldPopulation
    bank: CataloguePredictionBankV1


@dataclass(frozen=True, slots=True)
class _Partition:
    label: str
    training_fraction: float
    evaluation_end_fraction: float
    training_ids: tuple[Sha256Digest, ...]
    evaluation_ids: tuple[Sha256Digest, ...]


def run_long_arc_development_analysis(
    *,
    arc_id: str,
    graph: PhysicalEpisodeGraphV1,
    prediction_support: CataloguePredictionSupportV1,
    snapshot_payload: SnapshotPayload,
    tle_snapshot: TleSnapshotRefV1,
    observer_site: ObserverSiteV1,
    design: LongArcExecutionDesign,
) -> LongArcDevelopmentRunResult:
    """Build all response-free banks, then score frozen chronological partitions."""

    graph = _revalidate_graph(graph)
    prediction_support = _revalidate_support(prediction_support)
    tle_snapshot = _revalidate_snapshot(tle_snapshot)
    observer_site = _revalidate_site(observer_site)
    design = _revalidate_design(design)
    expected_support = CataloguePredictionSupportV1.from_graph(graph)
    if prediction_support.content_digest != expected_support.content_digest:
        raise LongArcRunnerInputError("prediction support does not bind the response graph")
    if len(graph.episodes) != 1:
        raise LongArcRunnerInputError("V1 opened-long-arc runner requires one physical episode")

    # This entire phase consumes only the narrow response-free support port.
    field_banks = tuple(
        _build_field_bank(
            prediction_support=prediction_support,
            snapshot_payload=snapshot_payload,
            tle_snapshot=tle_snapshot,
            observer_site=observer_site,
            design=design,
            field_delta_s=field_delta_s,
        )
        for field_delta_s in design.catalogue_fields_s
    )
    if tuple(item.population.field_delta_s for item in field_banks) != (-500, 0, 500):
        raise LongArcRunnerInputError("response-free field-bank inventory is incomplete")

    partitions = tuple(
        _score_partition(graph=graph, field_banks=field_banks, design=design, partition=item)
        for item in _partitions(graph, design)
    )
    field_receipts = tuple(_field_receipt(item) for item in field_banks)
    digest = canonical_digest(
        {
            "algorithm_version": _ALGORITHM_VERSION,
            "arc_id": arc_id,
            "graph_content_digest": graph.content_digest,
            "prediction_support_digest": prediction_support.content_digest,
            "tle_snapshot_digest": tle_snapshot.digest,
            "field_banks": [asdict(item) for item in field_receipts],
            "partitions": [asdict(item) for item in partitions],
            "all_response_free_banks_built_before_response_scoring": True,
            "wrong_epoch_is_observe_only": True,
            "numerical_thresholds_applied": False,
            "identity_claimed": False,
            "secure_norad_claimed": False,
            "positioning_validation_claimed": False,
        }
    )
    return LongArcDevelopmentRunResult(
        arc_id=arc_id,
        graph_content_digest=graph.content_digest,
        prediction_support_digest=prediction_support.content_digest,
        tle_snapshot_digest=tle_snapshot.digest,
        field_banks=field_receipts,
        partitions=partitions,
        result_digest=digest,
    )


def long_arc_development_result_payload(
    result: LongArcDevelopmentRunResult,
) -> dict[str, object]:
    """Return the complete digest-closed, JSON-compatible result document."""

    document = asdict(result)
    claimed_digest = document.pop("result_digest")
    if claimed_digest != canonical_digest(document):
        raise LongArcRunnerInputError("long-arc result digest does not match complete content")
    return {**document, "result_digest": claimed_digest}


def _build_field_bank(
    *,
    prediction_support: CataloguePredictionSupportV1,
    snapshot_payload: SnapshotPayload,
    tle_snapshot: TleSnapshotRefV1,
    observer_site: ObserverSiteV1,
    design: LongArcExecutionDesign,
    field_delta_s: int,
) -> _FieldBank:
    population = select_response_free_starlink_population(
        prediction_support,
        snapshot_payload,
        tle_snapshot=tle_snapshot,
        observer_site=observer_site,
        tau_policy=design.tau_policy,
        field_delta_s=field_delta_s,
        selection_protocol_digest=design.selection_protocol_digest,
        policy=design.population_policy,
    )
    if not population.propagation_complete_for_association:
        raise LongArcRunnerInputError(
            f"field {field_delta_s:+d} s population had an incomplete propagation inventory"
        )
    if population.selected_candidate_count == 0:
        raise LongArcRunnerInputError(
            f"field {field_delta_s:+d} s has no horizon-visible Starlink candidate"
        )
    bank = build_sgp4_catalogue_prediction_bank(
        prediction_support,
        snapshot_payload,
        tle_snapshot=tle_snapshot,
        site_rf_authority=KnownSiteRfAuthority.create(
            observer_site=observer_site,
            nominal_rf_hz=design.nominal_rf_hz,
        ),
        candidate_universe=population.universe,
        verified_tle_members=population.verified_tle_members,
        tau_policy=design.tau_policy,
        prediction_policy=design.prediction_policy,
        catalogue_field_delta_s=field_delta_s,
    )
    if bank.returned_candidate_count != population.selected_candidate_count:
        raise LongArcRunnerInputError("field population and prediction bank counts disagree")
    return _FieldBank(population=population, bank=bank)


def _partitions(
    graph: PhysicalEpisodeGraphV1,
    design: LongArcExecutionDesign,
) -> tuple[_Partition, ...]:
    rows = tuple(sorted(graph.observations, key=lambda item: item.support_center_utc_ns))
    count = len(rows)
    main_cut = _fraction_index(count, design.main_training_fraction)
    result = [
        _Partition(
            label="main-60-to-100",
            training_fraction=design.main_training_fraction,
            evaluation_end_fraction=1.0,
            training_ids=tuple(item.observation_id for item in rows[:main_cut]),
            evaluation_ids=tuple(item.observation_id for item in rows[main_cut:]),
        )
    ]
    for fraction in design.rolling_training_fractions:
        start = _fraction_index(count, fraction)
        evaluation_end = min(1.0, fraction + design.rolling_next_fraction)
        stop = _fraction_index(count, evaluation_end)
        result.append(
            _Partition(
                label=(f"rolling-{round(fraction * 100):02d}-to-{round(evaluation_end * 100):02d}"),
                training_fraction=fraction,
                evaluation_end_fraction=evaluation_end,
                training_ids=tuple(item.observation_id for item in rows[:start]),
                evaluation_ids=tuple(item.observation_id for item in rows[start:stop]),
            )
        )
    for item in result:
        if len(item.training_ids) < 4 or not item.evaluation_ids:
            raise LongArcRunnerInputError("chronological partition lacks required support")
    return tuple(result)


def _score_partition(
    *,
    graph: PhysicalEpisodeGraphV1,
    field_banks: tuple[_FieldBank, ...],
    design: LongArcExecutionDesign,
    partition: _Partition,
) -> LongArcPartitionResult:
    selected_ids = partition.training_ids + partition.evaluation_ids
    projected_graph = _project_graph(graph, selected_ids)
    projected_banks = tuple(
        (
            item.population.field_delta_s,
            _project_bank(item.bank, projected_graph),
        )
        for item in field_banks
    )
    field_scores = tuple(
        _field_partition_score(
            field_delta_s=field_delta_s,
            graph=projected_graph,
            bank=bank,
            partition=partition,
            design=design,
        )
        for field_delta_s, bank in projected_banks
    )
    radio_null = score_radio_polynomial_null(
        projected_graph,
        RadioPolynomialNullConfig(
            training_observation_ids=partition.training_ids,
            evaluation_observation_ids=partition.evaluation_ids,
            calendar_block_duration_s=design.calendar_block_duration_s,
        ),
    )
    true_score = next(item for item in field_scores if item.field_delta_s == 0)
    wrong = tuple(
        _wrong_epoch_observation(true_score, item)
        for item in field_scores
        if item.field_delta_s != 0
    )
    comparisons = _orbit_radio_comparisons(true_score, radio_null)
    return LongArcPartitionResult(
        label=partition.label,
        training_fraction=partition.training_fraction,
        evaluation_end_fraction=partition.evaluation_end_fraction,
        training_observation_ids=partition.training_ids,
        evaluation_observation_ids=partition.evaluation_ids,
        field_scores=field_scores,
        radio_polynomial_null=radio_null,
        wrong_epoch_observations=wrong,
        orbit_radio_comparisons=comparisons,
    )


def _field_partition_score(
    *,
    field_delta_s: int,
    graph: PhysicalEpisodeGraphV1,
    bank: CataloguePredictionBankV1,
    partition: _Partition,
    design: LongArcExecutionDesign,
) -> LongArcFieldPartitionScore:
    association = associate_single_episode_nearest_neighbour(
        graph,
        bank,
        config=NearestNeighbourAssociationConfig(
            training_observation_ids=partition.training_ids,
            evaluation_observation_ids=partition.evaluation_ids,
            expected_selection_protocol_digest=bank.selection_protocol_digest,
            expected_selection_policy_digest=bank.selection_policy_digest,
            nuisance_offset_prior_sigma_hz=design.nuisance_offset_prior_sigma_hz,
        ),
    )
    winner = _best_catalogue_training_score(association)
    if winner.catalog_number is None or winner.selected_tau_s is None:
        raise LongArcRunnerInputError("best catalogue score lacks candidate or tau")
    candidate = next(
        (item for item in bank.candidates if item.catalog_number == winner.catalog_number),
        None,
    )
    if candidate is None:
        raise LongArcRunnerInputError("best catalogue score is absent from prediction bank")
    state = next(
        (item for item in candidate.tau_states if item.tau_s == winner.selected_tau_s),
        None,
    )
    if state is None:
        raise LongArcRunnerInputError("best catalogue tau is absent from prediction bank")
    observation_by_id = {item.observation_id: item for item in graph.observations}
    prediction_by_id = {item.observation_id: item for item in state.predictions}
    offset_hz = winner.frozen_training_offset_mean_hz
    blocks: dict[int, list[float]] = {}
    block_ns = round(design.calendar_block_duration_s * 1e9)
    residuals: list[float] = []
    for observation_id in partition.evaluation_ids:
        observation = observation_by_id[observation_id]
        prediction = prediction_by_id[observation_id]
        residual = observation.measured_cfo_hz - prediction.predicted_cfo_hz - offset_hz
        residuals.append(residual)
        block_start = observation.support_center_utc_ns // block_ns * block_ns
        blocks.setdefault(block_start, []).append(residual)
    block_scores = tuple(
        LongArcCalendarBlockScore(
            block_start_utc_ns=block_start,
            observation_count=len(values),
            residual_rms_hz=_rms(values),
        )
        for block_start, values in sorted(blocks.items())
    )
    pooled = _rms(residuals)
    equal_block = math.sqrt(
        math.fsum(item.residual_rms_hz**2 for item in block_scores) / len(block_scores)
    )
    if not math.isclose(
        pooled,
        winner.heldout_innovation.prior_centered_innovation_rms_hz,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise LongArcRunnerInputError("future residual RMS disagrees with frozen association score")
    return LongArcFieldPartitionScore(
        field_delta_s=field_delta_s,
        association=association,
        catalogue_future_pooled_rms_hz=pooled,
        catalogue_future_equal_calendar_block_rms_hz=equal_block,
        catalogue_future_calendar_blocks=block_scores,
    )


def _project_graph(
    graph: PhysicalEpisodeGraphV1,
    observation_ids: tuple[Sha256Digest, ...],
) -> PhysicalEpisodeGraphV1:
    selected = set(observation_ids)
    observations = tuple(item for item in graph.observations if item.observation_id in selected)
    if len(observations) != len(observation_ids):
        raise LongArcRunnerInputError("partition references an unknown graph observation")
    episode = graph.episodes[0]
    projected_episode = PhysicalCfoEpisodeV1(
        episode_id=episode.episode_id,
        dwell_id=episode.dwell_id,
        lane_id=episode.lane_id,
        order_index=episode.order_index,
        continuity_component_id=episode.continuity_component_id,
        observation_ids=tuple(
            item.observation_id
            for item in sorted(observations, key=lambda row: row.support_center_utc_ns)
        ),
        replica_group_id=episode.replica_group_id,
        exclusion_group_ids=episode.exclusion_group_ids,
    )
    return PhysicalEpisodeGraphV1.create(
        observations=observations,
        episodes=(projected_episode,),
    )


def _project_bank(
    bank: CataloguePredictionBankV1,
    graph: PhysicalEpisodeGraphV1,
) -> CataloguePredictionBankV1:
    support = CataloguePredictionSupportV1.from_graph(graph)
    observation_ids = {item.observation_id for item in support.observations}
    reference_utc_ns = min(item.support_center_utc_ns for item in support.observations)
    candidates = tuple(
        CatalogueCandidatePredictionV1(
            catalog_number=candidate.catalog_number,
            object_name=candidate.object_name,
            selected_element_digest=candidate.selected_element_digest,
            element_epoch_utc_ns=candidate.element_epoch_utc_ns,
            element_age_s_at_reference=(
                abs(reference_utc_ns - candidate.element_epoch_utc_ns) / 1e9
            ),
            eligible_episode_ids=candidate.eligible_episode_ids,
            tau_states=tuple(
                CandidateTauStateV1(
                    tau_s=state.tau_s,
                    log_prior_weight=state.log_prior_weight,
                    predictions=tuple(
                        item for item in state.predictions if item.observation_id in observation_ids
                    ),
                )
                for state in candidate.tau_states
            ),
        )
        for candidate in bank.candidates
    )
    return CataloguePredictionBankV1.create(
        support=support,
        tle_snapshot=bank.tle_snapshot,
        observer_site=bank.observer_site,
        nominal_rf_hz=bank.nominal_rf_hz,
        selection_protocol_digest=bank.selection_protocol_digest,
        selection_policy_digest=bank.selection_policy_digest,
        tle_membership_authority_digest=bank.tle_membership_authority_digest,
        verified_tle_members=bank.verified_tle_members,
        propagation_model=bank.propagation_model,
        candidates=candidates,
        source_candidate_count=bank.source_candidate_count,
        tau_search_policy=bank.tau_search_policy,
    )


def _field_receipt(field_bank: _FieldBank) -> LongArcFieldBankReceipt:
    return LongArcFieldBankReceipt(
        field_delta_s=field_bank.population.field_delta_s,
        population_receipt_digest=field_bank.population.content_digest,
        selection_policy_digest=field_bank.population.selection_policy_digest,
        candidate_universe_digest=field_bank.bank.candidate_universe_digest,
        prediction_bank_digest=field_bank.bank.content_digest,
        candidate_count=field_bank.bank.returned_candidate_count,
        candidates=tuple(
            LongArcCandidateInventoryRow(
                catalog_number=item.catalog_number,
                object_name=item.object_name,
                selected_element_digest=item.selected_element_digest,
                element_epoch_utc_ns=item.element_epoch_utc_ns,
                element_age_s_at_reference=item.element_age_s_at_reference,
            )
            for item in field_bank.bank.candidates
        ),
    )


def _wrong_epoch_observation(
    true_field: LongArcFieldPartitionScore,
    wrong_field: LongArcFieldPartitionScore,
) -> LongArcWrongEpochObservation:
    true_winner = _best_catalogue_training_score(true_field.association)
    wrong_winner = _best_catalogue_training_score(wrong_field.association)
    true_pooled_rms = true_field.catalogue_future_pooled_rms_hz
    wrong_pooled_rms = wrong_field.catalogue_future_pooled_rms_hz
    true_equal_rms = true_field.catalogue_future_equal_calendar_block_rms_hz
    wrong_equal_rms = wrong_field.catalogue_future_equal_calendar_block_rms_hz
    true_nis = true_winner.heldout_innovation.mean_normalized_innovation_squared
    wrong_nis = wrong_winner.heldout_innovation.mean_normalized_innovation_squared
    field_delta = wrong_field.field_delta_s
    if field_delta == -500:
        literal_delta: Literal[-500, 500] = -500
    elif field_delta == 500:
        literal_delta = 500
    else:
        raise LongArcRunnerInputError("wrong-epoch comparison field is not predeclared")
    return LongArcWrongEpochObservation(
        field_delta_s=literal_delta,
        true_training_winner_catalog_number=true_winner.catalog_number,
        wrong_field_training_winner_catalog_number=wrong_winner.catalog_number,
        true_winner_future_pooled_rms_hz=true_pooled_rms,
        wrong_field_winner_future_pooled_rms_hz=wrong_pooled_rms,
        true_winner_future_equal_calendar_block_rms_hz=true_equal_rms,
        wrong_field_winner_future_equal_calendar_block_rms_hz=wrong_equal_rms,
        future_equal_calendar_block_rms_difference_hz=wrong_equal_rms - true_equal_rms,
        future_equal_calendar_block_rms_ratio=_safe_ratio(wrong_equal_rms, true_equal_rms),
        future_negative_log_score_difference=(
            wrong_winner.heldout_predictive_negative_log_score
            - true_winner.heldout_predictive_negative_log_score
        ),
        future_mean_normalized_innovation_squared_ratio=_safe_ratio(wrong_nis, true_nis),
    )


def _orbit_radio_comparisons(
    true_field: LongArcFieldPartitionScore,
    radio_null: RadioPolynomialNullResult,
) -> tuple[LongArcOrbitRadioComparison, ...]:
    orbit = _best_catalogue_training_score(true_field.association)
    orbit_pooled_rms = true_field.catalogue_future_pooled_rms_hz
    orbit_equal_rms = true_field.catalogue_future_equal_calendar_block_rms_hz
    orbit_nll = orbit.heldout_predictive_negative_log_score
    return tuple(
        LongArcOrbitRadioComparison(
            polynomial_degree=item.degree,
            orbit_future_pooled_rms_hz=orbit_pooled_rms,
            radio_future_pooled_rms_hz=item.evaluation_pooled_rms_hz,
            orbit_future_equal_calendar_block_rms_hz=orbit_equal_rms,
            radio_future_equal_calendar_block_rms_hz=(item.evaluation_equal_calendar_block_rms_hz),
            radio_minus_orbit_future_equal_calendar_block_rms_hz=(
                item.evaluation_equal_calendar_block_rms_hz - orbit_equal_rms
            ),
            radio_over_orbit_future_equal_calendar_block_rms_ratio=_safe_ratio(
                item.evaluation_equal_calendar_block_rms_hz,
                orbit_equal_rms,
            ),
            radio_minus_orbit_predictive_negative_log_likelihood=(
                item.evaluation_predictive_negative_log_likelihood - orbit_nll
            ),
        )
        for item in radio_null.scores
    )


def _best_catalogue_training_score(
    result: NearestNeighbourAssociationResult,
) -> NearestNeighbourHypothesisScore:
    for item in result.scores:
        if item.kind == "catalogue-candidate":
            return item
    raise LongArcRunnerInputError("field association has no catalogue-candidate score")


def _revalidate_graph(value: PhysicalEpisodeGraphV1) -> PhysicalEpisodeGraphV1:
    try:
        return PhysicalEpisodeGraphV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise LongArcRunnerInputError("response graph is invalid") from error


def _revalidate_support(value: CataloguePredictionSupportV1) -> CataloguePredictionSupportV1:
    try:
        return CataloguePredictionSupportV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise LongArcRunnerInputError("prediction support is invalid") from error


def _revalidate_snapshot(value: TleSnapshotRefV1) -> TleSnapshotRefV1:
    try:
        return TleSnapshotRefV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise LongArcRunnerInputError("TLE snapshot authority is invalid") from error


def _revalidate_site(value: ObserverSiteV1) -> ObserverSiteV1:
    try:
        return ObserverSiteV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise LongArcRunnerInputError("observer site authority is invalid") from error


def _revalidate_design(value: LongArcExecutionDesign) -> LongArcExecutionDesign:
    try:
        return LongArcExecutionDesign(
            selection_protocol_digest=value.selection_protocol_digest,
            nominal_rf_hz=value.nominal_rf_hz,
            catalogue_fields_s=value.catalogue_fields_s,
            main_training_fraction=value.main_training_fraction,
            rolling_training_fractions=value.rolling_training_fractions,
            rolling_next_fraction=value.rolling_next_fraction,
            nuisance_offset_prior_sigma_hz=value.nuisance_offset_prior_sigma_hz,
            calendar_block_duration_s=value.calendar_block_duration_s,
            tau_policy=ExactTauPolicy(
                policy=value.tau_policy.policy, points=value.tau_policy.points
            ),
            population_policy=StarlinkHorizonPopulationPolicy(
                minimum_elevation_deg=value.population_policy.minimum_elevation_deg,
                coarse_spacing_s=value.population_policy.coarse_spacing_s,
                maximum_coarse_time_count=value.population_policy.maximum_coarse_time_count,
                maximum_exact_time_count=value.population_policy.maximum_exact_time_count,
                maximum_coarse_propagated_states=(
                    value.population_policy.maximum_coarse_propagated_states
                ),
                maximum_exact_propagated_states=(
                    value.population_policy.maximum_exact_propagated_states
                ),
                maximum_selected_candidate_count=(
                    value.population_policy.maximum_selected_candidate_count
                ),
                object_name_prefix=value.population_policy.object_name_prefix,
            ),
            prediction_policy=Sgp4SupportPredictionPolicy(
                integration_sample_count=value.prediction_policy.integration_sample_count,
                standard_uncertainty_floor_hz=(
                    value.prediction_policy.standard_uncertainty_floor_hz
                ),
                element_age_growth_hz_per_day=(
                    value.prediction_policy.element_age_growth_hz_per_day
                ),
                fit_residual_multiplier=value.prediction_policy.fit_residual_multiplier,
                maximum_propagated_states=value.prediction_policy.maximum_propagated_states,
            ),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise LongArcRunnerInputError("execution design is invalid") from error


def _fraction_index(count: int, fraction: float) -> int:
    value = math.floor(count * fraction + 0.5)
    if not 0 < value <= count:
        raise LongArcRunnerInputError("chronological fraction produces an empty partition")
    return value


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0.0:
        return None
    value = numerator / denominator
    if not math.isfinite(value):
        raise LongArcRunnerInputError("diagnostic ratio is not finite")
    return value


def _rms(values: list[float]) -> float:
    if not values:
        raise LongArcRunnerInputError("cannot summarize an empty residual inventory")
    result = math.sqrt(math.fsum(item * item for item in values) / len(values))
    if not math.isfinite(result):
        raise LongArcRunnerInputError("residual RMS is not finite")
    return result


def _is_digest(value: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


__all__ = [
    "LongArcCalendarBlockScore",
    "LongArcCandidateInventoryRow",
    "LongArcDevelopmentRunResult",
    "LongArcExecutionDesign",
    "LongArcFieldBankReceipt",
    "LongArcFieldPartitionScore",
    "LongArcOrbitRadioComparison",
    "LongArcPartitionResult",
    "LongArcRunnerInputError",
    "LongArcWrongEpochObservation",
    "long_arc_development_result_payload",
    "run_long_arc_development_analysis",
]
