"""Immutable contracts for bounded catalogue-conditioned satellite association.

The physical episode graph is deliberately TLE-blind.  Catalogue predictions
enter through a separate response-free bank, and the association result remains
candidate-only even when one mode has most of the modeled probability mass.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.contracts.standard_pipeline import StandardScientificStatus

BoundedName = Annotated[str, StringConstraints(min_length=1, max_length=128)]
MachineName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9._-]*$"),
]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


def _validate_support_interval_and_moments(
    *,
    start_utc_ns: int,
    center_utc_ns: int,
    end_utc_ns: int,
    moments: tuple[float, float, float, float],
) -> None:
    if not start_utc_ns <= center_utc_ns < end_utc_ns:
        raise ValueError("support center must lie in the half-open support interval")
    lower_offset_s = (start_utc_ns - center_utc_ns) / 1e9
    upper_offset_s = (end_utc_ns - center_utc_ns) / 1e9
    maximum_offset_s = max(abs(lower_offset_s), abs(upper_offset_s))
    _, _, second_factorial_moment, third_factorial_moment = moments
    raw_second_moment = 2.0 * second_factorial_moment
    raw_third_moment = 6.0 * third_factorial_moment
    maximum_second_moment = -lower_offset_s * upper_offset_s
    second_tolerance = 1e-12 * max(abs(maximum_second_moment), abs(raw_second_moment), 1e-30)
    third_tolerance = 1e-12 * max(maximum_offset_s**3, abs(raw_third_moment), 1e-45)
    if raw_second_moment > maximum_second_moment + second_tolerance:
        raise ValueError("second support moment is impossible for the declared interval")
    if abs(raw_third_moment) > maximum_offset_s**3 + third_tolerance:
        raise ValueError("third support moment is impossible for the declared interval")
    if abs(raw_third_moment) > maximum_offset_s * raw_second_moment + third_tolerance:
        raise ValueError("third support moment is inconsistent with the second moment")
    if lower_offset_s < 0.0:
        lower_third_moment = (
            lower_offset_s * raw_second_moment - raw_second_moment**2 / lower_offset_s
        )
        upper_third_moment = (
            upper_offset_s * raw_second_moment - raw_second_moment**2 / upper_offset_s
        )
        hausdorff_tolerance = 1e-12 * max(
            abs(lower_third_moment),
            abs(upper_third_moment),
            abs(raw_third_moment),
            maximum_offset_s**3,
            1e-45,
        )
        if not (
            lower_third_moment - hausdorff_tolerance
            <= raw_third_moment
            <= upper_third_moment + hausdorff_tolerance
        ):
            raise ValueError("third moment violates the bounded support moment sequence")


class SupportIntegratedCfoObservationV1(ContractModel):
    """One support-centred CFO observation from one canonical source group."""

    schema_version: Literal[1] = 1
    observation_id: Sha256Digest
    source_group_id: Sha256Digest
    episode_id: Sha256Digest
    receiver_path_id: Sha256Digest
    hardware_epoch_id: MachineName
    raw_recording_authority_digest: Sha256Digest
    recording_manifest_digest: Sha256Digest
    stream_id: MachineName
    source_binding_digest: Sha256Digest
    source_sample_start: Annotated[int, Field(ge=0)]
    source_sample_end: Annotated[int, Field(gt=0)]
    support_start_utc_ns: Annotated[int, Field(gt=0)]
    support_center_utc_ns: Annotated[int, Field(gt=0)]
    support_end_utc_ns: Annotated[int, Field(gt=0)]
    measured_cfo_hz: float
    standard_uncertainty_hz: Annotated[float, Field(gt=0)]
    factorial_support_moments_s: Annotated[tuple[float, float, float, float], Field()]

    @field_validator(
        "measured_cfo_hz",
        "standard_uncertainty_hz",
    )
    @classmethod
    def _finite_scalars(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("CFO observation values must be finite")
        return value

    @field_validator("factorial_support_moments_s")
    @classmethod
    def _finite_support_moments(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("support moments must be finite")
        if not math.isclose(value[0], 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("zeroth support moment must equal one")
        if not math.isclose(value[1], 0.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("support-centred first moment must equal zero")
        if value[2] < 0:
            raise ValueError("second factorial support moment cannot be negative")
        return value

    @model_validator(mode="after")
    def _support_is_half_open_and_contains_center(self) -> Self:
        if self.source_sample_end <= self.source_sample_start:
            raise ValueError("source sample span must be non-empty")
        _validate_support_interval_and_moments(
            start_utc_ns=self.support_start_utc_ns,
            center_utc_ns=self.support_center_utc_ns,
            end_utc_ns=self.support_end_utc_ns,
            moments=self.factorial_support_moments_s,
        )
        return self


class PhysicalCfoEpisodeV1(ContractModel):
    """One TLE-blind physical episode after alias and fragment collapse."""

    schema_version: Literal[1] = 1
    episode_id: Sha256Digest
    dwell_id: Sha256Digest
    lane_id: Sha256Digest
    order_index: Annotated[int, Field(ge=0)]
    continuity_component_id: Sha256Digest
    observation_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=2, max_length=4_096)]
    replica_group_id: Sha256Digest | None = None
    exclusion_group_ids: Annotated[tuple[Sha256Digest, ...], Field(max_length=64)] = ()

    @model_validator(mode="after")
    def _inventories_are_unique(self) -> Self:
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("episode observations must be unique")
        if self.exclusion_group_ids != tuple(sorted(set(self.exclusion_group_ids))):
            raise ValueError("episode exclusion groups must be unique and ordered")
        return self


class PhysicalEpisodeGraphV1(ContractModel):
    """Exact TLE-blind observation and episode inventory consumed by association."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["physical-episode-graph-v1"] = "physical-episode-graph-v1"
    observations: Annotated[
        tuple[SupportIntegratedCfoObservationV1, ...], Field(min_length=2, max_length=32_768)
    ]
    episodes: Annotated[tuple[PhysicalCfoEpisodeV1, ...], Field(min_length=1, max_length=256)]
    tle_blind: Literal[True] = True
    source_groups_collapsed: Literal[True] = True
    observation_error_model: Literal[
        "independent-diagonal-after-nonoverlapping-source-collapse-v1"
    ] = "independent-diagonal-after-nonoverlapping-source-collapse-v1"
    content_digest: Sha256Digest

    @classmethod
    def create(
        cls,
        *,
        observations: tuple[SupportIntegratedCfoObservationV1, ...],
        episodes: tuple[PhysicalCfoEpisodeV1, ...],
    ) -> PhysicalEpisodeGraphV1:
        observation_by_id = {item.observation_id: item for item in observations}
        ordered_episodes = tuple(
            sorted(episodes, key=lambda item: (item.lane_id, item.order_index, item.episode_id))
        )
        ordered_observations = tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.episode_id,
                    item.support_center_utc_ns,
                    item.observation_id,
                ),
            )
        )
        if len(observation_by_id) != len(observations):
            raise ValueError("physical graph observation identities must be unique")
        payload = {
            "schema_version": 1,
            "algorithm_version": "physical-episode-graph-v1",
            "observations": [item.model_dump(mode="json") for item in ordered_observations],
            "episodes": [item.model_dump(mode="json") for item in ordered_episodes],
            "tle_blind": True,
            "source_groups_collapsed": True,
            "observation_error_model": (
                "independent-diagonal-after-nonoverlapping-source-collapse-v1"
            ),
        }
        return cls.model_validate({**payload, "content_digest": canonical_digest(payload)})

    @model_validator(mode="after")
    def _graph_is_closed_and_canonical(self) -> Self:
        if self.observations != tuple(
            sorted(
                self.observations,
                key=lambda item: (
                    item.episode_id,
                    item.support_center_utc_ns,
                    item.observation_id,
                ),
            )
        ):
            raise ValueError("physical graph observations must be canonically ordered")
        if self.episodes != tuple(
            sorted(
                self.episodes,
                key=lambda item: (item.lane_id, item.order_index, item.episode_id),
            )
        ):
            raise ValueError("physical graph episodes must be canonically ordered")
        observation_by_id = {item.observation_id: item for item in self.observations}
        if len(observation_by_id) != len(self.observations):
            raise ValueError("physical graph observation identities must be unique")
        source_groups = tuple(item.source_group_id for item in self.observations)
        if len(set(source_groups)) != len(source_groups):
            raise ValueError("one canonical observation is required per source group")
        episode_ids = tuple(item.episode_id for item in self.episodes)
        if len(set(episode_ids)) != len(episode_ids):
            raise ValueError("physical graph episode identities must be unique")
        lane_orders = tuple((item.lane_id, item.order_index) for item in self.episodes)
        if len(set(lane_orders)) != len(lane_orders):
            raise ValueError("episode order indices must be unique within each lane")

        referenced: list[str] = []
        episode_support_bounds: dict[str, tuple[int, int]] = {}
        episode_by_id = {item.episode_id: item for item in self.episodes}
        for episode in self.episodes:
            if any(item not in observation_by_id for item in episode.observation_ids):
                raise ValueError("episode references an unknown observation")
            rows = tuple(observation_by_id[item] for item in episode.observation_ids)
            if any(item.episode_id != episode.episode_id for item in rows):
                raise ValueError("observation episode identity disagrees with episode inventory")
            if len({item.receiver_path_id for item in rows}) != 1:
                raise ValueError("one physical episode must remain path-local")
            if len({item.hardware_epoch_id for item in rows}) != 1:
                raise ValueError("one physical episode must remain hardware-epoch local")
            if tuple(item.observation_id for item in rows) != tuple(
                item.observation_id
                for item in sorted(
                    rows,
                    key=lambda item: (item.support_center_utc_ns, item.observation_id),
                )
            ):
                raise ValueError("episode observations must be time ordered")
            episode_support_bounds[episode.episode_id] = (
                min(item.support_start_utc_ns for item in rows),
                max(item.support_end_utc_ns for item in rows),
            )
            referenced.extend(episode.observation_ids)
        if set(referenced) != set(observation_by_id) or len(referenced) != len(observation_by_id):
            raise ValueError("episodes must partition the physical observation inventory")

        replica_members: dict[str, set[str]] = {}
        exclusion_members: dict[str, set[str]] = {}
        for episode in self.episodes:
            if episode.replica_group_id is not None:
                replica_members.setdefault(episode.replica_group_id, set()).add(episode.episode_id)
            for group_id in episode.exclusion_group_ids:
                exclusion_members.setdefault(group_id, set()).add(episode.episode_id)
        for replica in replica_members.values():
            for exclusion in exclusion_members.values():
                if len(replica & exclusion) > 1:
                    raise ValueError("replica and exclusion constraints conflict")
        if set(episode_by_id) != set(episode_ids):
            raise ValueError("episode inventory is inconsistent")
        episodes_by_lane: dict[str, list[PhysicalCfoEpisodeV1]] = {}
        for episode in self.episodes:
            episodes_by_lane.setdefault(episode.lane_id, []).append(episode)
        for lane_episodes in episodes_by_lane.values():
            if tuple(item.order_index for item in lane_episodes) != tuple(
                range(len(lane_episodes))
            ):
                raise ValueError("episode order must be contiguous within each lane")
            if any(
                episode_support_bounds[right.episode_id][0]
                < episode_support_bounds[left.episode_id][1]
                for left, right in zip(lane_episodes, lane_episodes[1:], strict=False)
            ):
                raise ValueError("episode order must follow nonoverlapping support chronology")
        by_source: dict[tuple[str, str], list[SupportIntegratedCfoObservationV1]] = {}
        for observation in self.observations:
            by_source.setdefault(
                (observation.raw_recording_authority_digest, observation.stream_id), []
            ).append(observation)
        for source_rows in by_source.values():
            ordered = sorted(
                source_rows,
                key=lambda item: (
                    item.source_sample_start,
                    item.source_sample_end,
                    item.observation_id,
                ),
            )
            if any(
                right.source_sample_start < left.source_sample_end
                for left, right in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError(
                    "diagonal observation-error model rejects overlapping source spans"
                )
            if any(
                right.support_start_utc_ns < left.support_end_utc_ns
                for left, right in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError(
                    "source sample order must follow nonoverlapping support chronology"
                )
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("physical episode graph digest does not match content")
        return self


class CataloguePredictionSupportObservationV1(ContractModel):
    """Response-free observation geometry exposed to the TLE predictor."""

    schema_version: Literal[1] = 1
    observation_id: Sha256Digest
    episode_id: Sha256Digest
    support_start_utc_ns: Annotated[int, Field(gt=0)]
    support_center_utc_ns: Annotated[int, Field(gt=0)]
    support_end_utc_ns: Annotated[int, Field(gt=0)]
    factorial_support_moments_s: Annotated[tuple[float, float, float, float], Field()]

    @field_validator("factorial_support_moments_s")
    @classmethod
    def _moments_are_finite_and_centred(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("prediction-support moments must be finite")
        if not math.isclose(value[0], 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("prediction-support zeroth moment must equal one")
        if not math.isclose(value[1], 0.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("prediction support must be centred")
        if value[2] < 0:
            raise ValueError("prediction-support second moment cannot be negative")
        return value

    @model_validator(mode="after")
    def _support_is_valid(self) -> Self:
        _validate_support_interval_and_moments(
            start_utc_ns=self.support_start_utc_ns,
            center_utc_ns=self.support_center_utc_ns,
            end_utc_ns=self.support_end_utc_ns,
            moments=self.factorial_support_moments_s,
        )
        return self


class CataloguePredictionSupportV1(ContractModel):
    """Narrow response-free port for catalogue propagation."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["catalogue-prediction-support-v1"] = (
        "catalogue-prediction-support-v1"
    )
    episode_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=256)]
    observations: Annotated[
        tuple[CataloguePredictionSupportObservationV1, ...],
        Field(min_length=2, max_length=32_768),
    ]
    response_fields_excluded: Literal[True] = True
    content_digest: Sha256Digest

    @classmethod
    def from_graph(cls, graph: PhysicalEpisodeGraphV1) -> CataloguePredictionSupportV1:
        payload = {
            "schema_version": 1,
            "algorithm_version": "catalogue-prediction-support-v1",
            "episode_ids": sorted(item.episode_id for item in graph.episodes),
            "observations": [
                {
                    "schema_version": 1,
                    "observation_id": item.observation_id,
                    "episode_id": item.episode_id,
                    "support_start_utc_ns": item.support_start_utc_ns,
                    "support_center_utc_ns": item.support_center_utc_ns,
                    "support_end_utc_ns": item.support_end_utc_ns,
                    "factorial_support_moments_s": item.factorial_support_moments_s,
                }
                for item in graph.observations
            ],
            "response_fields_excluded": True,
        }
        return cls.model_validate({**payload, "content_digest": canonical_digest(payload)})

    @model_validator(mode="after")
    def _inventory_is_closed(self) -> Self:
        if self.episode_ids != tuple(sorted(set(self.episode_ids))):
            raise ValueError("prediction-support episodes must be unique and ordered")
        observation_ids = tuple(item.observation_id for item in self.observations)
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("prediction-support observations must be unique")
        if self.observations != tuple(
            sorted(
                self.observations,
                key=lambda item: (
                    item.episode_id,
                    item.support_center_utc_ns,
                    item.observation_id,
                ),
            )
        ):
            raise ValueError("prediction-support observations must be canonically ordered")
        if any(item.episode_id not in self.episode_ids for item in self.observations):
            raise ValueError("prediction-support observation names an unknown episode")
        if {item.episode_id for item in self.observations} != set(self.episode_ids):
            raise ValueError("every prediction-support episode needs observations")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("prediction-support digest does not match content")
        return self


class CandidateObservationPredictionV1(ContractModel):
    schema_version: Literal[1] = 1
    observation_id: Sha256Digest
    predicted_cfo_hz: float
    standard_uncertainty_hz: Annotated[float, Field(ge=0)] = 0.0

    @field_validator("predicted_cfo_hz", "standard_uncertainty_hz")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("candidate prediction values must be finite")
        return value


class CandidateTauStateV1(ContractModel):
    schema_version: Literal[1] = 1
    tau_s: Annotated[float, Field(ge=-5.0, le=5.0)]
    log_prior_weight: float
    predictions: Annotated[
        tuple[CandidateObservationPredictionV1, ...], Field(min_length=2, max_length=32_768)
    ]

    @field_validator("tau_s", "log_prior_weight")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("candidate tau values must be finite")
        return value

    @model_validator(mode="after")
    def _predictions_are_canonical(self) -> Self:
        identities = tuple(item.observation_id for item in self.predictions)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("candidate predictions must be unique and ordered")
        return self


class CatalogueVerifiedTleMemberV1(ContractModel):
    """Authority-verified identity and epoch for one element in the frozen snapshot."""

    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(gt=0)]
    selected_element_digest: Sha256Digest
    element_epoch_utc_ns: Annotated[int, Field(gt=0)]


class CatalogueCandidatePredictionV1(ContractModel):
    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(gt=0)]
    object_name: BoundedName
    selected_element_digest: Sha256Digest
    element_epoch_utc_ns: Annotated[int, Field(gt=0)]
    element_age_s_at_reference: Annotated[float, Field(ge=0)]
    eligible_episode_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=256)]
    tau_states: Annotated[tuple[CandidateTauStateV1, ...], Field(min_length=1, max_length=401)]

    @field_validator("element_age_s_at_reference")
    @classmethod
    def _finite_age(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("element age must be finite")
        return value

    @model_validator(mode="after")
    def _states_are_complete_and_canonical(self) -> Self:
        if self.eligible_episode_ids != tuple(sorted(set(self.eligible_episode_ids))):
            raise ValueError("eligible episode identities must be unique and ordered")
        tau_values = tuple(item.tau_s for item in self.tau_states)
        if tau_values != tuple(sorted(set(tau_values))):
            raise ValueError("candidate tau states must be unique and ordered")
        if not any(item == 0.0 for item in tau_values):
            raise ValueError("every candidate must retain the exact tau=0 primary state")
        prediction_inventories = {
            tuple(item.observation_id for item in state.predictions) for state in self.tau_states
        }
        if len(prediction_inventories) != 1:
            raise ValueError("all tau states must predict the same observation inventory")
        return self


def _candidate_universe_digest(
    *,
    support: CataloguePredictionSupportV1,
    tle_snapshot: TleSnapshotRefV1,
    observer_site: ObserverSiteV1,
    nominal_rf_hz: float,
    prediction_reference_utc_ns: int,
    selection_protocol_digest: Sha256Digest,
    selection_policy_digest: Sha256Digest,
    tle_membership_authority_digest: Sha256Digest,
    verified_tle_members: tuple[CatalogueVerifiedTleMemberV1, ...],
    tau_search_policy: str,
    source_candidate_count: int,
    candidates: tuple[CatalogueCandidatePredictionV1, ...],
) -> Sha256Digest:
    return canonical_digest(
        {
            "support_digest": support.content_digest,
            "tle_snapshot": tle_snapshot.model_dump(mode="json"),
            "observer_site": observer_site.model_dump(mode="json"),
            "nominal_rf_hz": nominal_rf_hz,
            "prediction_reference_utc_ns": prediction_reference_utc_ns,
            "selection_protocol_digest": selection_protocol_digest,
            "selection_policy_digest": selection_policy_digest,
            "tle_membership_authority_digest": tle_membership_authority_digest,
            "verified_tle_members": [item.model_dump(mode="json") for item in verified_tle_members],
            "tau_search_policy": tau_search_policy,
            "source_candidate_count": source_candidate_count,
            "returned_candidate_count": len(candidates),
            "members": [
                {
                    "catalog_number": item.catalog_number,
                    "object_name": item.object_name,
                    "selected_element_digest": item.selected_element_digest,
                    "element_epoch_utc_ns": item.element_epoch_utc_ns,
                    "eligible_episode_ids": item.eligible_episode_ids,
                }
                for item in candidates
            ],
        }
    )


class CataloguePredictionBankV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["support-integrated-tle-bank-v1"] = "support-integrated-tle-bank-v1"
    support: CataloguePredictionSupportV1
    tle_snapshot: TleSnapshotRefV1
    observer_site: ObserverSiteV1
    nominal_rf_hz: Annotated[float, Field(gt=0)]
    prediction_reference_utc_ns: Annotated[int, Field(gt=0)]
    selection_protocol_digest: Sha256Digest
    selection_policy_digest: Sha256Digest
    tle_membership_authority_digest: Sha256Digest
    verified_tle_members: Annotated[
        tuple[CatalogueVerifiedTleMemberV1, ...], Field(max_length=10_000)
    ]
    candidate_universe_digest: Sha256Digest
    population_conditioning: Literal["frozen-response-free-universe-v1"] = (
        "frozen-response-free-universe-v1"
    )
    tau_search_policy: Literal["fixed-tau-zero-v1", "bounded-profile-minus5-plus5-v1"] = (
        "fixed-tau-zero-v1"
    )
    propagation_model: MachineName
    prediction_error_model: Literal["independent-diagonal-conditional-on-candidate-v1"] = (
        "independent-diagonal-conditional-on-candidate-v1"
    )
    source_candidate_count: Annotated[int, Field(ge=0)]
    returned_candidate_count: Annotated[int, Field(ge=0, le=10_000)]
    truncated_candidate_count: Annotated[int, Field(ge=0)]
    candidates: Annotated[tuple[CatalogueCandidatePredictionV1, ...], Field(max_length=10_000)]
    response_accessed: Literal[False] = False
    content_digest: Sha256Digest

    @classmethod
    def create(
        cls,
        *,
        support: CataloguePredictionSupportV1,
        tle_snapshot: TleSnapshotRefV1,
        observer_site: ObserverSiteV1,
        nominal_rf_hz: float,
        selection_protocol_digest: Sha256Digest,
        selection_policy_digest: Sha256Digest,
        tle_membership_authority_digest: Sha256Digest,
        verified_tle_members: tuple[CatalogueVerifiedTleMemberV1, ...],
        propagation_model: str,
        candidates: tuple[CatalogueCandidatePredictionV1, ...],
        source_candidate_count: int | None = None,
        tau_search_policy: Literal[
            "fixed-tau-zero-v1", "bounded-profile-minus5-plus5-v1"
        ] = "fixed-tau-zero-v1",
    ) -> CataloguePredictionBankV1:
        ordered = tuple(sorted(candidates, key=lambda item: item.catalog_number))
        ordered_members = tuple(
            sorted(
                verified_tle_members,
                key=lambda item: (
                    item.catalog_number,
                    item.selected_element_digest,
                    item.element_epoch_utc_ns,
                ),
            )
        )
        source_count = len(ordered) if source_candidate_count is None else source_candidate_count
        prediction_reference_utc_ns = min(
            item.support_center_utc_ns for item in support.observations
        )
        universe_digest = _candidate_universe_digest(
            support=support,
            tle_snapshot=tle_snapshot,
            observer_site=observer_site,
            nominal_rf_hz=nominal_rf_hz,
            prediction_reference_utc_ns=prediction_reference_utc_ns,
            selection_protocol_digest=selection_protocol_digest,
            selection_policy_digest=selection_policy_digest,
            tle_membership_authority_digest=tle_membership_authority_digest,
            verified_tle_members=ordered_members,
            tau_search_policy=tau_search_policy,
            source_candidate_count=source_count,
            candidates=ordered,
        )
        payload = {
            "schema_version": 1,
            "algorithm_version": "support-integrated-tle-bank-v1",
            "support": support.model_dump(mode="json"),
            "tle_snapshot": tle_snapshot.model_dump(mode="json"),
            "observer_site": observer_site.model_dump(mode="json"),
            "nominal_rf_hz": nominal_rf_hz,
            "prediction_reference_utc_ns": prediction_reference_utc_ns,
            "selection_protocol_digest": selection_protocol_digest,
            "selection_policy_digest": selection_policy_digest,
            "tle_membership_authority_digest": tle_membership_authority_digest,
            "verified_tle_members": [item.model_dump(mode="json") for item in ordered_members],
            "candidate_universe_digest": universe_digest,
            "population_conditioning": "frozen-response-free-universe-v1",
            "tau_search_policy": tau_search_policy,
            "propagation_model": propagation_model,
            "prediction_error_model": "independent-diagonal-conditional-on-candidate-v1",
            "source_candidate_count": source_count,
            "returned_candidate_count": len(ordered),
            "truncated_candidate_count": source_count - len(ordered),
            "candidates": [item.model_dump(mode="json") for item in ordered],
            "response_accessed": False,
        }
        return cls.model_validate({**payload, "content_digest": canonical_digest(payload)})

    @model_validator(mode="after")
    def _bank_is_closed_and_canonical(self) -> Self:
        if (
            self.returned_candidate_count + self.truncated_candidate_count
            != self.source_candidate_count
            or len(self.candidates) != self.returned_candidate_count
        ):
            raise ValueError("candidate bank accounting is inconsistent")
        numbers = tuple(item.catalog_number for item in self.candidates)
        if numbers != tuple(sorted(set(numbers))):
            raise ValueError("catalogue candidates must be unique and ordered")
        verified_member_keys = tuple(
            (
                item.catalog_number,
                item.selected_element_digest,
                item.element_epoch_utc_ns,
            )
            for item in self.verified_tle_members
        )
        if verified_member_keys != tuple(sorted(set(verified_member_keys))):
            raise ValueError("verified TLE members must be unique and ordered")
        candidate_member_keys = {
            (
                item.catalog_number,
                item.selected_element_digest,
                item.element_epoch_utc_ns,
            )
            for item in self.candidates
        }
        if set(verified_member_keys) != candidate_member_keys:
            raise ValueError(
                "verified TLE membership inventory must exactly cover candidate elements"
            )
        if self.tle_snapshot.object_count < len(self.verified_tle_members):
            raise ValueError("verified TLE membership exceeds the snapshot object count")
        if not math.isfinite(self.nominal_rf_hz):
            raise ValueError("nominal RF must be finite")
        if self.candidate_universe_digest != _candidate_universe_digest(
            support=self.support,
            tle_snapshot=self.tle_snapshot,
            observer_site=self.observer_site,
            nominal_rf_hz=self.nominal_rf_hz,
            prediction_reference_utc_ns=self.prediction_reference_utc_ns,
            selection_protocol_digest=self.selection_protocol_digest,
            selection_policy_digest=self.selection_policy_digest,
            tle_membership_authority_digest=self.tle_membership_authority_digest,
            verified_tle_members=self.verified_tle_members,
            tau_search_policy=self.tau_search_policy,
            source_candidate_count=self.source_candidate_count,
            candidates=self.candidates,
        ):
            raise ValueError("candidate universe digest does not match frozen membership")
        expected_reference = min(item.support_center_utc_ns for item in self.support.observations)
        if self.prediction_reference_utc_ns != expected_reference:
            raise ValueError("prediction reference must be derived from response-free support")
        if self.tle_snapshot.collected_utc_ns >= min(
            item.support_start_utc_ns for item in self.support.observations
        ):
            raise ValueError("catalogue TLE snapshot must be strictly pre-measurement")
        support_episode_ids = set(self.support.episode_ids)
        support_observations_by_episode = {
            episode_id: tuple(
                sorted(
                    item.observation_id
                    for item in self.support.observations
                    if item.episode_id == episode_id
                )
            )
            for episode_id in self.support.episode_ids
        }
        for candidate in self.candidates:
            expected_age = (
                abs(self.prediction_reference_utc_ns - candidate.element_epoch_utc_ns) / 1e9
            )
            if not math.isclose(
                candidate.element_age_s_at_reference,
                expected_age,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise ValueError("candidate element age does not match prediction reference")
            if not set(candidate.eligible_episode_ids) <= support_episode_ids:
                raise ValueError("candidate names an unknown prediction-support episode")
            expected = tuple(
                sorted(
                    observation_id
                    for episode_id in candidate.eligible_episode_ids
                    for observation_id in support_observations_by_episode[episode_id]
                )
            )
            if any(
                tuple(item.observation_id for item in state.predictions) != expected
                for state in candidate.tau_states
            ):
                raise ValueError("candidate predictions do not cover exact response-free support")
            tau_values = tuple(item.tau_s for item in candidate.tau_states)
            if self.tau_search_policy == "fixed-tau-zero-v1" and tau_values != (0.0,):
                raise ValueError("fixed-tau policy requires exactly the tau=0 state")
            if self.tau_search_policy == "bounded-profile-minus5-plus5-v1" and not (
                tau_values[0] == -5.0 and tau_values[-1] == 5.0 and 0.0 in tau_values
            ):
                raise ValueError("bounded tau profile must close the exact [-5,+5] support")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("candidate bank digest does not match content")
        return self


class CatalogueAssociationConfigV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["rao-blackwellized-exact-k012-v1"] = (
        "rao-blackwellized-exact-k012-v1"
    )
    maximum_active_satellites: Annotated[int, Field(ge=0, le=2)] = 2
    active_count_log_weights: Annotated[tuple[float, float, float], Field()]
    assigned_episode_log_weight: float = 0.0
    unassigned_episode_log_weight: float = 0.0
    same_state_log_weight: float = 0.0
    handoff_log_weight: Annotated[float, Field(le=0.0)] = 0.0
    component_offset_prior_sigma_hz: Annotated[float, Field(gt=0)]
    hardware_drift_prior_sigma_hz_per_s: Annotated[float, Field(gt=0)]
    null_model: Literal["zero-curve-component-offset-hardware-drift-v1"] = (
        "zero-curve-component-offset-hardware-drift-v1"
    )
    maximum_evaluated_hypotheses: Annotated[int, Field(ge=1, le=10_000_000)]
    reported_hypothesis_limit: Annotated[int, Field(ge=1, le=10_000)]
    maximum_normal_condition_number: Annotated[float, Field(gt=1.0)] = 1e15

    @field_validator(
        "active_count_log_weights",
    )
    @classmethod
    def _finite_tuple(cls, value: tuple[float, float, float]) -> tuple[float, float, float]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("association log weights must be finite")
        return value

    @field_validator(
        "assigned_episode_log_weight",
        "unassigned_episode_log_weight",
        "same_state_log_weight",
        "handoff_log_weight",
        "component_offset_prior_sigma_hz",
        "hardware_drift_prior_sigma_hz_per_s",
        "maximum_normal_condition_number",
    )
    @classmethod
    def _finite_scalar(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("association configuration values must be finite")
        return value

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class EpisodeCatalogueAssignmentV1(ContractModel):
    schema_version: Literal[1] = 1
    episode_id: Sha256Digest
    catalog_number: Annotated[int | None, Field(gt=0)]


class CatalogueTauChoiceV1(ContractModel):
    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(gt=0)]
    tau_s: Annotated[float, Field(ge=-5.0, le=5.0)]


class ComponentOffsetEstimateV1(ContractModel):
    schema_version: Literal[1] = 1
    continuity_component_id: Sha256Digest
    mean_hz: float
    standard_uncertainty_hz: Annotated[float, Field(ge=0)]

    @field_validator("mean_hz", "standard_uncertainty_hz")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("component offset estimates must be finite")
        return value


class HardwareDriftEstimateV1(ContractModel):
    schema_version: Literal[1] = 1
    hardware_epoch_id: MachineName
    reference_utc_ns: Annotated[int, Field(gt=0)]
    mean_hz_per_s: float
    standard_uncertainty_hz_per_s: Annotated[float, Field(ge=0)]

    @field_validator("mean_hz_per_s", "standard_uncertainty_hz_per_s")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("hardware drift estimates must be finite")
        return value


class CatalogueAssociationModeV1(ContractModel):
    schema_version: Literal[1] = 1
    rank: Annotated[int, Field(ge=1)]
    active_catalog_numbers: Annotated[tuple[int, ...], Field(max_length=2)]
    assignments: Annotated[tuple[EpisodeCatalogueAssignmentV1, ...], Field(min_length=1)]
    tau_choices: Annotated[tuple[CatalogueTauChoiceV1, ...], Field(max_length=2)]
    data_negative_log_evidence: float
    active_count_negative_log_prior: Annotated[float, Field(ge=0.0)]
    active_set_negative_log_prior: Annotated[float, Field(ge=0.0)]
    assignment_negative_log_prior: Annotated[float, Field(ge=0.0)]
    tau_negative_log_prior: Annotated[float, Field(ge=0.0)]
    total_negative_log_joint: float
    log_posterior_probability: Annotated[float, Field(le=0.0)]
    posterior_probability: Probability
    component_offsets: tuple[ComponentOffsetEstimateV1, ...]
    hardware_drifts: tuple[HardwareDriftEstimateV1, ...]
    handoff_count: Annotated[int, Field(ge=0)]
    tau_boundary_hit: bool
    candidate_only: Literal[True] = True

    @field_validator(
        "data_negative_log_evidence",
        "active_count_negative_log_prior",
        "active_set_negative_log_prior",
        "assignment_negative_log_prior",
        "tau_negative_log_prior",
        "total_negative_log_joint",
        "log_posterior_probability",
        "posterior_probability",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("association mode scores must be finite")
        return value

    @model_validator(mode="after")
    def _mode_is_canonical(self) -> Self:
        if self.active_catalog_numbers != tuple(sorted(set(self.active_catalog_numbers))):
            raise ValueError("active catalogue identities must be unique and ordered")
        if any(item <= 0 for item in self.active_catalog_numbers):
            raise ValueError("active catalogue identities must be positive")
        episode_ids = tuple(item.episode_id for item in self.assignments)
        if len(set(episode_ids)) != len(episode_ids):
            raise ValueError("mode episode assignments must be unique")
        assigned = {
            item.catalog_number for item in self.assignments if item.catalog_number is not None
        }
        if assigned != set(self.active_catalog_numbers):
            raise ValueError("every active catalogue identity must be assigned")
        if tuple(item.catalog_number for item in self.tau_choices) != self.active_catalog_numbers:
            raise ValueError("tau choices must match the active catalogue inventory")
        expected_boundary_hit = any(
            math.isclose(abs(item.tau_s), 5.0, rel_tol=0.0, abs_tol=1e-12)
            for item in self.tau_choices
        )
        if self.tau_boundary_hit != expected_boundary_hit:
            raise ValueError("tau-boundary flag does not match the selected tau states")
        expected_probability = math.exp(self.log_posterior_probability)
        if not math.isclose(
            self.posterior_probability,
            expected_probability,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise ValueError("mode probability disagrees with its log posterior")
        score_sum = (
            self.data_negative_log_evidence
            + self.active_count_negative_log_prior
            + self.active_set_negative_log_prior
            + self.assignment_negative_log_prior
            + self.tau_negative_log_prior
        )
        if not math.isclose(
            self.total_negative_log_joint,
            score_sum,
            rel_tol=1e-12,
            abs_tol=1e-10,
        ):
            raise ValueError("association mode score decomposition is inconsistent")
        component_ids = tuple(item.continuity_component_id for item in self.component_offsets)
        if component_ids != tuple(sorted(set(component_ids))):
            raise ValueError("component-offset estimates must be unique and ordered")
        hardware_ids = tuple(item.hardware_epoch_id for item in self.hardware_drifts)
        if hardware_ids != tuple(sorted(set(hardware_ids))):
            raise ValueError("hardware-drift estimates must be unique and ordered")
        return self


class ActiveCountPosteriorV1(ContractModel):
    schema_version: Literal[1] = 1
    active_count: Annotated[int, Field(ge=0, le=2)]
    posterior_probability: Probability


class CataloguePresencePosteriorV1(ContractModel):
    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(gt=0)]
    posterior_probability: Probability


class EpisodeAssignmentProbabilityV1(ContractModel):
    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(gt=0)]
    posterior_probability: Probability


class EpisodeAssignmentPosteriorV1(ContractModel):
    schema_version: Literal[1] = 1
    episode_id: Sha256Digest
    unassigned_probability: Probability
    catalogue_probabilities: tuple[EpisodeAssignmentProbabilityV1, ...]

    @model_validator(mode="after")
    def _probabilities_close(self) -> Self:
        numbers = tuple(item.catalog_number for item in self.catalogue_probabilities)
        if numbers != tuple(sorted(set(numbers))):
            raise ValueError("episode catalogue probabilities must be unique and ordered")
        total = self.unassigned_probability + sum(
            item.posterior_probability for item in self.catalogue_probabilities
        )
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("episode assignment probabilities must sum to one")
        return self


class CatalogueAssociationResultV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["rao-blackwellized-exact-k012-v1"] = (
        "rao-blackwellized-exact-k012-v1"
    )
    graph_digest: Sha256Digest
    prediction_bank_digest: Sha256Digest
    candidate_universe_digest: Sha256Digest
    selection_protocol_digest: Sha256Digest
    tle_membership_authority_digest: Sha256Digest
    tau_search_policy: Literal["fixed-tau-zero-v1", "bounded-profile-minus5-plus5-v1"]
    config_digest: Sha256Digest
    observation_error_model: Literal["independent-diagonal-after-nonoverlapping-source-collapse-v1"]
    prediction_error_model: Literal["independent-diagonal-conditional-on-candidate-v1"]
    null_model: Literal["zero-curve-component-offset-hardware-drift-v1"]
    evaluated_hypothesis_count: Annotated[int, Field(ge=1)]
    reported_hypothesis_count: Annotated[int, Field(ge=1)]
    unreported_hypothesis_count: Annotated[int, Field(ge=0)]
    reported_posterior_mass: Probability
    unreported_posterior_mass: Probability
    hypotheses: Annotated[tuple[CatalogueAssociationModeV1, ...], Field(min_length=1)]
    active_count_posterior: tuple[ActiveCountPosteriorV1, ...]
    catalogue_presence_posterior: tuple[CataloguePresencePosteriorV1, ...]
    episode_assignment_posterior: tuple[EpisodeAssignmentPosteriorV1, ...]
    status: StandardScientificStatus
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1_024)]
    tau_boundary_abstention: bool
    search_complete: Literal[True] = True
    candidate_only: Literal[True] = True
    universe_conditional: Literal[True] = True
    identity_claimed: Literal[False] = False
    navigation_fix_claimed: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _result_is_closed(self) -> Self:
        if (
            self.reported_hypothesis_count + self.unreported_hypothesis_count
            != self.evaluated_hypothesis_count
            or len(self.hypotheses) != self.reported_hypothesis_count
        ):
            raise ValueError("association hypothesis accounting is inconsistent")
        if not math.isclose(
            self.reported_posterior_mass + self.unreported_posterior_mass,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("reported and unreported posterior mass must sum to one")
        if self.unreported_posterior_mass > (
            self.unreported_hypothesis_count * self.hypotheses[-1].posterior_probability + 1e-9
        ):
            raise ValueError("unreported posterior mass violates reported rank ordering")
        if tuple(item.rank for item in self.hypotheses) != tuple(
            range(1, len(self.hypotheses) + 1)
        ):
            raise ValueError("reported association hypotheses must have consecutive ranks")
        probabilities = tuple(item.posterior_probability for item in self.hypotheses)
        if any(right > left for left, right in zip(probabilities, probabilities[1:], strict=False)):
            raise ValueError("reported hypotheses must be ordered by posterior probability")
        if any(
            right.total_negative_log_joint < left.total_negative_log_joint
            and not math.isclose(
                right.total_negative_log_joint,
                left.total_negative_log_joint,
                rel_tol=1e-12,
                abs_tol=1e-10,
            )
            for left, right in zip(self.hypotheses, self.hypotheses[1:], strict=False)
        ):
            raise ValueError("reported hypotheses must be ordered by negative log joint")
        if not math.isclose(
            sum(probabilities),
            self.reported_posterior_mass,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("reported hypothesis mass disagrees with mode probabilities")
        probability_normalizers = tuple(
            item.log_posterior_probability + item.total_negative_log_joint
            for item in self.hypotheses
        )
        if any(
            not math.isclose(
                item,
                probability_normalizers[0],
                rel_tol=1e-12,
                abs_tol=1e-10,
            )
            for item in probability_normalizers[1:]
        ):
            raise ValueError("mode probabilities are inconsistent with hypothesis scores")
        structural_keys = tuple(
            (
                item.active_catalog_numbers,
                tuple(
                    (assignment.episode_id, assignment.catalog_number)
                    for assignment in item.assignments
                ),
                tuple((choice.catalog_number, choice.tau_s) for choice in item.tau_choices),
            )
            for item in self.hypotheses
        )
        if len(set(structural_keys)) != len(structural_keys):
            raise ValueError("reported structural hypotheses must be unique")
        expected_tau_abstention = self.hypotheses[0].tau_boundary_hit
        if self.tau_boundary_abstention != expected_tau_abstention:
            raise ValueError("result tau-boundary abstention disagrees with rank-one mode")
        if self.tau_boundary_abstention and self.status is StandardScientificStatus.COMPLETE:
            raise ValueError("a tau-boundary result must abstain from complete status")
        assignment_inventories = {
            tuple(item.episode_id for item in mode.assignments) for mode in self.hypotheses
        }
        if len(assignment_inventories) != 1:
            raise ValueError("reported modes must share one episode inventory")
        component_inventories = {
            tuple(item.continuity_component_id for item in mode.component_offsets)
            for mode in self.hypotheses
        }
        hardware_inventories = {
            tuple(item.hardware_epoch_id for item in mode.hardware_drifts)
            for mode in self.hypotheses
        }
        if len(component_inventories) != 1 or len(hardware_inventories) != 1:
            raise ValueError("reported modes must share one nuisance inventory")
        active_counts = tuple(item.active_count for item in self.active_count_posterior)
        if active_counts != tuple(range(len(active_counts))):
            raise ValueError("active-count posterior must be contiguous from zero")
        if not math.isclose(
            sum(item.posterior_probability for item in self.active_count_posterior),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("active-count posterior must sum to one")
        if any(
            len(mode.active_catalog_numbers) >= len(self.active_count_posterior)
            for mode in self.hypotheses
        ):
            raise ValueError("active-count posterior does not cover reported hypotheses")
        catalogue_numbers = tuple(item.catalog_number for item in self.catalogue_presence_posterior)
        if catalogue_numbers != tuple(sorted(set(catalogue_numbers))):
            raise ValueError("catalogue-presence posterior must be unique and ordered")
        catalogue_inventory = set(catalogue_numbers)
        if any(
            not set(mode.active_catalog_numbers) <= catalogue_inventory for mode in self.hypotheses
        ):
            raise ValueError("catalogue posterior does not cover reported hypotheses")
        episode_posterior_ids = tuple(item.episode_id for item in self.episode_assignment_posterior)
        if len(set(episode_posterior_ids)) != len(episode_posterior_ids):
            raise ValueError("episode-assignment posterior identities must be unique")
        mode_episode_ids = next(iter(assignment_inventories))
        if episode_posterior_ids != mode_episode_ids:
            raise ValueError("episode posterior inventory disagrees with reported modes")
        if any(
            tuple(item.catalog_number for item in episode.catalogue_probabilities)
            != catalogue_numbers
            for episode in self.episode_assignment_posterior
        ):
            raise ValueError("episode posterior catalogue inventory is incomplete")
        expected_active_count = sum(
            item.active_count * item.posterior_probability for item in self.active_count_posterior
        )
        if not math.isclose(
            sum(item.posterior_probability for item in self.catalogue_presence_posterior),
            expected_active_count,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("catalogue presence does not match expected active count")
        presence_by_catalogue = {
            item.catalog_number: item.posterior_probability
            for item in self.catalogue_presence_posterior
        }
        for catalogue_number, presence in presence_by_catalogue.items():
            assignments = tuple(
                next(
                    item.posterior_probability
                    for item in episode.catalogue_probabilities
                    if item.catalog_number == catalogue_number
                )
                for episode in self.episode_assignment_posterior
            )
            if (
                any(item > presence + 1e-9 for item in assignments)
                or presence > sum(assignments) + 1e-9
            ):
                raise ValueError("catalogue presence is inconsistent with episode assignments")
        self._validate_reported_marginal_bounds(catalogue_numbers, episode_posterior_ids)
        if self.unreported_hypothesis_count == 0:
            self._validate_complete_marginals(catalogue_numbers, episode_posterior_ids)
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("catalogue association result digest does not match content")
        return self

    def _validate_reported_marginal_bounds(
        self,
        catalogue_numbers: tuple[int, ...],
        episode_ids: tuple[str, ...],
    ) -> None:
        reported_active = [0.0] * len(self.active_count_posterior)
        reported_presence = {item: 0.0 for item in catalogue_numbers}
        reported_episode = {
            episode_id: {None: 0.0, **{item: 0.0 for item in catalogue_numbers}}
            for episode_id in episode_ids
        }
        for mode in self.hypotheses:
            reported_active[len(mode.active_catalog_numbers)] += mode.posterior_probability
            for number in mode.active_catalog_numbers:
                reported_presence[number] += mode.posterior_probability
            for assignment in mode.assignments:
                reported_episode[assignment.episode_id][assignment.catalog_number] += (
                    mode.posterior_probability
                )

        def within_unreported_bound(value: float, lower: float) -> bool:
            return lower - 1e-9 <= value <= lower + self.unreported_posterior_mass + 1e-9

        if any(
            not within_unreported_bound(
                item.posterior_probability,
                reported_active[item.active_count],
            )
            for item in self.active_count_posterior
        ):
            raise ValueError("active-count posterior violates reported-mode mass bounds")
        if any(
            not within_unreported_bound(
                item.posterior_probability,
                reported_presence[item.catalog_number],
            )
            for item in self.catalogue_presence_posterior
        ):
            raise ValueError("catalogue posterior violates reported-mode mass bounds")
        for episode in self.episode_assignment_posterior:
            if not within_unreported_bound(
                episode.unassigned_probability,
                reported_episode[episode.episode_id][None],
            ) or any(
                not within_unreported_bound(
                    item.posterior_probability,
                    reported_episode[episode.episode_id][item.catalog_number],
                )
                for item in episode.catalogue_probabilities
            ):
                raise ValueError("episode posterior violates reported-mode mass bounds")

    def _validate_complete_marginals(
        self,
        catalogue_numbers: tuple[int, ...],
        episode_ids: tuple[str, ...],
    ) -> None:
        derived_active = [0.0] * len(self.active_count_posterior)
        derived_presence = {item: 0.0 for item in catalogue_numbers}
        derived_episode = {
            episode_id: {None: 0.0, **{item: 0.0 for item in catalogue_numbers}}
            for episode_id in episode_ids
        }
        for mode in self.hypotheses:
            derived_active[len(mode.active_catalog_numbers)] += mode.posterior_probability
            for number in mode.active_catalog_numbers:
                derived_presence[number] += mode.posterior_probability
            for assignment in mode.assignments:
                derived_episode[assignment.episode_id][assignment.catalog_number] += (
                    mode.posterior_probability
                )
        if any(
            not math.isclose(
                expected.posterior_probability,
                derived_active[expected.active_count],
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            for expected in self.active_count_posterior
        ):
            raise ValueError("active-count posterior disagrees with complete mode inventory")
        if any(
            not math.isclose(
                expected.posterior_probability,
                derived_presence[expected.catalog_number],
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            for expected in self.catalogue_presence_posterior
        ):
            raise ValueError("catalogue posterior disagrees with complete mode inventory")
        for episode in self.episode_assignment_posterior:
            if not math.isclose(
                episode.unassigned_probability,
                derived_episode[episode.episode_id][None],
                rel_tol=0.0,
                abs_tol=1e-9,
            ) or any(
                not math.isclose(
                    item.posterior_probability,
                    derived_episode[episode.episode_id][item.catalog_number],
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                for item in episode.catalogue_probabilities
            ):
                raise ValueError(
                    "episode assignment posterior disagrees with complete mode inventory"
                )
