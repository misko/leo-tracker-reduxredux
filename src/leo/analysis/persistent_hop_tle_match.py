"""Causal, candidate-only TLE matching for one long-scan CFO track.

The physical track is frozen before this module receives it.  Candidate
population uses only its time support, all nominal and wrong-time prediction
banks are built before response scoring, and catalogue/tau/offset fitting uses
only a chronological prefix.  The future suffix is scored once without refit.

This is deliberately an abstaining matcher.  It can name a leading Starlink
catalogue candidate, but it never turns one 300-second scan into a secure
identity claim.  Recurrence across independent scans is a separate gate.
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
    associate_single_episode_nearest_neighbour,
)
from leo.analysis.research.radio_polynomial_null import (
    RadioPolynomialNullConfig,
    RadioPolynomialNullResult,
    score_radio_polynomial_null,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1

_ALGORITHM_VERSION = "persistent-hop-causal-heldout-tle-match-v1"


class PersistentHopTleMatchInputError(ValueError):
    """The physical track or matching authority is incomplete or incoherent."""


def _default_tau_policy() -> ExactTauPolicy:
    return ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=tuple(TauGridPoint(float(value), 0.0) for value in range(-5, 6)),
    )


def _default_population_policy() -> StarlinkHorizonPopulationPolicy:
    return StarlinkHorizonPopulationPolicy(
        coarse_spacing_s=1.0,
        maximum_coarse_time_count=10_000,
        maximum_coarse_propagated_states=10_000_000,
        maximum_exact_propagated_states=20_000_000,
    )


def _default_prediction_policy() -> Sgp4SupportPredictionPolicy:
    return Sgp4SupportPredictionPolicy(
        standard_uncertainty_floor_hz=400.0,
        element_age_growth_hz_per_day=1_000.0,
        maximum_propagated_states=10_000_000,
    )


@dataclass(frozen=True, slots=True)
class PersistentHopTleMatchConfig:
    """Bounded work and explicit nuisance policy for one tracklet."""

    selection_protocol_digest: Sha256Digest
    nominal_rf_hz: float
    catalogue_fields_s: tuple[int, int, int] = (-500, 0, 500)
    maximum_support_observations: int = 128
    minimum_support_observations: int = 20
    minimum_support_span_s: float = 20.0
    training_fraction: float = 0.6
    nuisance_offset_prior_sigma_hz: float = 1_000_000.0
    calendar_block_duration_s: float = 5.0
    tau_policy: ExactTauPolicy = field(default_factory=_default_tau_policy)
    population_policy: StarlinkHorizonPopulationPolicy = field(
        default_factory=_default_population_policy
    )
    prediction_policy: Sgp4SupportPredictionPolicy = field(
        default_factory=_default_prediction_policy
    )

    def __post_init__(self) -> None:
        if self.catalogue_fields_s != (-500, 0, 500):
            raise PersistentHopTleMatchInputError(
                "catalogue controls must equal -500, 0, and +500 seconds"
            )
        if (
            not self.selection_protocol_digest.startswith("sha256:")
            or len(self.selection_protocol_digest) != 71
        ):
            raise PersistentHopTleMatchInputError("selection protocol digest is invalid")
        if (
            not math.isfinite(self.nominal_rf_hz)
            or self.nominal_rf_hz <= 0.0
            or not 5 <= self.minimum_support_observations <= self.maximum_support_observations
            or self.maximum_support_observations > 1_024
            or not math.isfinite(self.minimum_support_span_s)
            or self.minimum_support_span_s <= 0.0
            or not math.isclose(self.training_fraction, 0.6, rel_tol=0.0, abs_tol=1e-12)
            or not math.isfinite(self.nuisance_offset_prior_sigma_hz)
            or self.nuisance_offset_prior_sigma_hz <= 0.0
            or not math.isfinite(self.calendar_block_duration_s)
            or self.calendar_block_duration_s <= 0.0
        ):
            raise PersistentHopTleMatchInputError("TLE match controls are invalid")

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class PersistentHopTleFieldMatch:
    field_delta_s: int
    population_receipt_digest: Sha256Digest
    selection_policy_digest: Sha256Digest
    candidate_universe_digest: Sha256Digest
    prediction_bank_digest: Sha256Digest
    candidate_count: int
    association: NearestNeighbourAssociationResult


@dataclass(frozen=True, slots=True)
class PersistentHopTleMatchResult:
    source_graph_digest: Sha256Digest
    scored_graph_digest: Sha256Digest
    tle_snapshot_digest: Sha256Digest
    config_digest: Sha256Digest
    source_observation_count: int
    scored_observation_count: int
    support_span_s: float
    field_matches: tuple[PersistentHopTleFieldMatch, ...]
    radio_polynomial_null: RadioPolynomialNullResult
    leading_catalog_number: int | None
    leading_candidate_persisted_on_heldout: bool
    abstention_recommended: bool
    abstention_reasons: tuple[str, ...]
    content_digest: Sha256Digest
    algorithm_version: Literal["persistent-hop-causal-heldout-tle-match-v1"] = field(
        default="persistent-hop-causal-heldout-tle-match-v1", init=False
    )
    all_banks_built_before_response_scoring: Literal[True] = field(default=True, init=False)
    wrong_time_controls_are_observe_only: Literal[True] = field(default=True, init=False)
    candidate_only: Literal[True] = field(default=True, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class _FieldBank:
    population: ResponseFreeFieldPopulation
    bank: CataloguePredictionBankV1


def match_persistent_hop_track_to_tles(
    graph: PhysicalEpisodeGraphV1,
    snapshot_payload: SnapshotPayload,
    *,
    tle_snapshot: TleSnapshotRefV1,
    observer_site: ObserverSiteV1,
    config: PersistentHopTleMatchConfig,
) -> PersistentHopTleMatchResult:
    """Match one frozen tracklet with chronological and wrong-time controls."""

    graph = _revalidate_graph(graph)
    tle_snapshot = _revalidate_snapshot(tle_snapshot)
    observer_site = _revalidate_site(observer_site)
    if len(graph.episodes) != 1:
        raise PersistentHopTleMatchInputError("TLE matcher requires exactly one tracklet episode")
    scored_graph = _time_balanced_graph(graph, config.maximum_support_observations)
    rows = tuple(sorted(scored_graph.observations, key=lambda item: item.support_center_utc_ns))
    span_s = (rows[-1].support_end_utc_ns - rows[0].support_start_utc_ns) / 1e9
    if len(rows) < config.minimum_support_observations or span_s < config.minimum_support_span_s:
        raise PersistentHopTleMatchInputError(
            "tracklet lacks the minimum support needed for causal TLE matching"
        )
    support = CataloguePredictionSupportV1.from_graph(scored_graph)

    # Freeze every response-free candidate universe and prediction bank before
    # the first measured CFO is passed to an association routine.
    field_banks = tuple(
        _build_field_bank(
            support=support,
            snapshot_payload=snapshot_payload,
            tle_snapshot=tle_snapshot,
            observer_site=observer_site,
            config=config,
            field_delta_s=field_delta_s,
        )
        for field_delta_s in config.catalogue_fields_s
    )

    training_count = max(4, int(math.floor(len(rows) * config.training_fraction)))
    training_count = min(training_count, len(rows) - 1)
    training_ids = tuple(item.observation_id for item in rows[:training_count])
    evaluation_ids = tuple(item.observation_id for item in rows[training_count:])
    field_matches = tuple(
        _score_field(
            item,
            graph=scored_graph,
            training_ids=training_ids,
            evaluation_ids=evaluation_ids,
            config=config,
        )
        for item in field_banks
    )
    radio_null = score_radio_polynomial_null(
        scored_graph,
        RadioPolynomialNullConfig(
            training_observation_ids=training_ids,
            evaluation_observation_ids=evaluation_ids,
            calendar_block_duration_s=config.calendar_block_duration_s,
        ),
    )

    nominal = next(item for item in field_matches if item.field_delta_s == 0)
    association = nominal.association
    leading_catalog_number = (
        association.training_nearest_catalog_number
        if association.training_nearest_kind == "catalogue-candidate"
        else None
    )
    persisted = (
        leading_catalog_number is not None
        and association.heldout_nearest_kind == "catalogue-candidate"
        and association.heldout_nearest_catalog_number == leading_catalog_number
    )
    reasons: list[str] = list(association.abstention_diagnostics)
    if leading_catalog_number is None:
        reasons.append("restricted-null-led-training")
    if not persisted:
        reasons.append("catalogue-leader-did-not-persist-on-heldout")

    nominal_training_winner = association.scores[0]
    best_radio_nll = min(
        item.evaluation_predictive_negative_log_likelihood for item in radio_null.scores
    )
    if best_radio_nll <= nominal_training_winner.heldout_predictive_negative_log_score:
        reasons.append("radio-polynomial-null-not-worse-on-heldout")
    for field_match in field_matches:
        if field_match.field_delta_s == 0:
            continue
        wrong_winner = field_match.association.scores[0]
        if (
            wrong_winner.heldout_predictive_negative_log_score
            <= nominal_training_winner.heldout_predictive_negative_log_score
        ):
            reasons.append(
                f"wrong-time-{field_match.field_delta_s:+d}s-not-worse-on-heldout"
            )
    reasons = sorted(set(reasons))

    payload = {
        "algorithm_version": _ALGORITHM_VERSION,
        "source_graph_digest": graph.content_digest,
        "scored_graph_digest": scored_graph.content_digest,
        "tle_snapshot_digest": tle_snapshot.digest,
        "config_digest": config.digest,
        "source_observation_count": len(graph.observations),
        "scored_observation_count": len(rows),
        "support_span_s": span_s,
        "field_population_receipts": [
            {
                "field_delta_s": item.field_delta_s,
                "population_receipt_digest": item.population_receipt_digest,
                "selection_policy_digest": item.selection_policy_digest,
                "candidate_universe_digest": item.candidate_universe_digest,
                "prediction_bank_digest": item.prediction_bank_digest,
                "candidate_count": item.candidate_count,
                "association_partition_digest": item.association.observation_partition_digest,
            }
            for item in field_matches
        ],
        "radio_null_partition_digest": radio_null.observation_partition_digest,
        "leading_catalog_number": leading_catalog_number,
        "leading_candidate_persisted_on_heldout": persisted,
        "abstention_recommended": bool(reasons),
        "abstention_reasons": reasons,
        "all_banks_built_before_response_scoring": True,
        "wrong_time_controls_are_observe_only": True,
        "candidate_only": True,
        "identity_claimed": False,
    }
    return PersistentHopTleMatchResult(
        source_graph_digest=graph.content_digest,
        scored_graph_digest=scored_graph.content_digest,
        tle_snapshot_digest=tle_snapshot.digest,
        config_digest=config.digest,
        source_observation_count=len(graph.observations),
        scored_observation_count=len(rows),
        support_span_s=span_s,
        field_matches=field_matches,
        radio_polynomial_null=radio_null,
        leading_catalog_number=leading_catalog_number,
        leading_candidate_persisted_on_heldout=persisted,
        abstention_recommended=bool(reasons),
        abstention_reasons=tuple(reasons),
        content_digest=canonical_digest(payload),
    )


def _build_field_bank(
    *,
    support: CataloguePredictionSupportV1,
    snapshot_payload: SnapshotPayload,
    tle_snapshot: TleSnapshotRefV1,
    observer_site: ObserverSiteV1,
    config: PersistentHopTleMatchConfig,
    field_delta_s: int,
) -> _FieldBank:
    population = select_response_free_starlink_population(
        support,
        snapshot_payload,
        tle_snapshot=tle_snapshot,
        observer_site=observer_site,
        tau_policy=config.tau_policy,
        field_delta_s=field_delta_s,
        selection_protocol_digest=config.selection_protocol_digest,
        policy=config.population_policy,
    )
    if not population.propagation_complete_for_association:
        raise PersistentHopTleMatchInputError("catalogue population propagation is incomplete")
    if population.selected_candidate_count == 0:
        raise PersistentHopTleMatchInputError(
            f"field {field_delta_s:+d} s has no horizon-visible Starlink candidate"
        )
    bank = build_sgp4_catalogue_prediction_bank(
        support,
        snapshot_payload,
        tle_snapshot=tle_snapshot,
        site_rf_authority=KnownSiteRfAuthority.create(
            observer_site=observer_site,
            nominal_rf_hz=config.nominal_rf_hz,
        ),
        candidate_universe=population.universe,
        verified_tle_members=population.verified_tle_members,
        tau_policy=config.tau_policy,
        prediction_policy=config.prediction_policy,
        catalogue_field_delta_s=field_delta_s,
    )
    return _FieldBank(population=population, bank=bank)


def _score_field(
    field: _FieldBank,
    *,
    graph: PhysicalEpisodeGraphV1,
    training_ids: tuple[Sha256Digest, ...],
    evaluation_ids: tuple[Sha256Digest, ...],
    config: PersistentHopTleMatchConfig,
) -> PersistentHopTleFieldMatch:
    association = associate_single_episode_nearest_neighbour(
        graph,
        field.bank,
        config=NearestNeighbourAssociationConfig(
            training_observation_ids=training_ids,
            evaluation_observation_ids=evaluation_ids,
            expected_selection_protocol_digest=field.bank.selection_protocol_digest,
            expected_selection_policy_digest=field.bank.selection_policy_digest,
            nuisance_offset_prior_sigma_hz=config.nuisance_offset_prior_sigma_hz,
        ),
    )
    return PersistentHopTleFieldMatch(
        field_delta_s=field.population.field_delta_s,
        population_receipt_digest=field.population.content_digest,
        selection_policy_digest=field.population.selection_policy_digest,
        candidate_universe_digest=field.bank.candidate_universe_digest,
        prediction_bank_digest=field.bank.content_digest,
        candidate_count=field.bank.returned_candidate_count,
        association=association,
    )


def _time_balanced_graph(
    graph: PhysicalEpisodeGraphV1,
    maximum_observation_count: int,
) -> PhysicalEpisodeGraphV1:
    rows = tuple(sorted(graph.observations, key=lambda item: item.support_center_utc_ns))
    if len(rows) <= maximum_observation_count:
        return graph
    indexes = tuple(
        round(index * (len(rows) - 1) / (maximum_observation_count - 1))
        for index in range(maximum_observation_count)
    )
    if len(set(indexes)) != maximum_observation_count:
        raise PersistentHopTleMatchInputError("time-balanced support selection was not unique")
    selected = tuple(rows[index] for index in indexes)
    episode = graph.episodes[0]
    selected_ids = tuple(item.observation_id for item in selected)
    return PhysicalEpisodeGraphV1.create(
        observations=selected,
        episodes=(
            PhysicalCfoEpisodeV1(
                episode_id=episode.episode_id,
                dwell_id=episode.dwell_id,
                lane_id=episode.lane_id,
                order_index=episode.order_index,
                continuity_component_id=episode.continuity_component_id,
                observation_ids=selected_ids,
                replica_group_id=episode.replica_group_id,
                exclusion_group_ids=episode.exclusion_group_ids,
            ),
        ),
    )


def _revalidate_graph(value: PhysicalEpisodeGraphV1) -> PhysicalEpisodeGraphV1:
    try:
        return PhysicalEpisodeGraphV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise PersistentHopTleMatchInputError("physical episode graph is invalid") from error


def _revalidate_snapshot(value: TleSnapshotRefV1) -> TleSnapshotRefV1:
    try:
        return TleSnapshotRefV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise PersistentHopTleMatchInputError("TLE snapshot authority is invalid") from error


def _revalidate_site(value: ObserverSiteV1) -> ObserverSiteV1:
    try:
        return ObserverSiteV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise PersistentHopTleMatchInputError("observer-site authority is invalid") from error


__all__ = [
    "PersistentHopTleFieldMatch",
    "PersistentHopTleMatchConfig",
    "PersistentHopTleMatchInputError",
    "PersistentHopTleMatchResult",
    "match_persistent_hop_track_to_tles",
]
