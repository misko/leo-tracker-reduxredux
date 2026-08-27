"""Response-free full-Starlink horizon population selection.

The selector authenticates exact TLE snapshot bytes, consumes only the narrow
prediction-support geometry, and returns a complete untruncated candidate
universe plus exact selected-element membership receipts.  Measured CFO,
receiver paths, association scores, and catalogue ranking are outside this
module's input surface.

For one predeclared catalogue-time field, membership is the union of Starlink
objects at or above the geometric horizon at any support start, centre, or end
under every enumerated tau state.  A coarse propagation pass has a bounded
angular margin and can only retain extra candidates; the final decision is made
at the exact deduplicated support/tau instants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from leo.analysis.catalogue_prediction import (
    ExactTauPolicy,
    FrozenCatalogueCandidate,
    FrozenResponseFreeCandidateUniverse,
    SnapshotPayload,
    element_pair_digest,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetError,
    parse_element_set_records,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid
from leo.sky.screening import observe_grid

_ALGORITHM_VERSION = "response-free-starlink-horizon-union-v1"
_NS_PER_S = 1_000_000_000


class CataloguePopulationInputError(ValueError):
    """The response-free authority or selection policy is invalid."""


class CataloguePopulationWorkLimitError(ValueError):
    """The complete population cannot be evaluated inside the declared cap."""


@dataclass(frozen=True, slots=True)
class StarlinkHorizonPopulationPolicy:
    minimum_elevation_deg: float = 0.0
    coarse_spacing_s: float = 0.1
    maximum_coarse_time_count: int = 10_000
    maximum_exact_time_count: int = 200_000
    maximum_coarse_propagated_states: int = 10_000_000
    maximum_exact_propagated_states: int = 20_000_000
    maximum_selected_candidate_count: int = 10_000
    object_name_prefix: Literal["STARLINK"] = "STARLINK"

    def __post_init__(self) -> None:
        if self.minimum_elevation_deg != 0.0:
            raise CataloguePopulationInputError("V1 horizon elevation must equal zero degrees")
        if (
            not math.isfinite(self.coarse_spacing_s)
            or not 0.01 <= self.coarse_spacing_s <= 1.0
            or self.maximum_coarse_time_count < 3
            or self.maximum_exact_time_count < 3
            or self.maximum_coarse_propagated_states < 1
            or self.maximum_exact_propagated_states < 1
            or not 1 <= self.maximum_selected_candidate_count <= 10_000
            or self.object_name_prefix != "STARLINK"
        ):
            raise CataloguePopulationInputError("horizon population policy is invalid")

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(
            {
                "algorithm_version": "starlink-horizon-population-policy-v1",
                "minimum_elevation_deg": self.minimum_elevation_deg,
                "coarse_spacing_s": self.coarse_spacing_s,
                "maximum_coarse_time_count": self.maximum_coarse_time_count,
                "maximum_exact_time_count": self.maximum_exact_time_count,
                "maximum_coarse_propagated_states": (self.maximum_coarse_propagated_states),
                "maximum_exact_propagated_states": self.maximum_exact_propagated_states,
                "maximum_selected_candidate_count": self.maximum_selected_candidate_count,
                "object_name_prefix": self.object_name_prefix,
            }
        )


@dataclass(frozen=True, slots=True)
class ResponseFreeFieldPopulation:
    field_delta_s: int
    selection_protocol_digest: Sha256Digest
    selection_policy_digest: Sha256Digest
    tle_membership_authority_digest: Sha256Digest
    universe: FrozenResponseFreeCandidateUniverse
    verified_tle_members: tuple[CatalogueVerifiedTleMemberV1, ...]
    snapshot_object_count: int
    starlink_object_count: int
    coarse_time_count: int
    exact_time_count: int
    coarse_candidate_count: int
    selected_candidate_count: int
    coarse_propagation_failure_count: int
    coarse_implausible_altitude_count: int
    exact_propagation_failure_count: int
    exact_implausible_altitude_count: int
    propagation_complete_for_association: bool
    content_digest: Sha256Digest
    response_accessed: Literal[False] = field(default=False, init=False)
    candidate_ranking_performed: Literal[False] = field(default=False, init=False)
    candidate_truncation_performed: Literal[False] = field(default=False, init=False)
    algorithm_version: Literal["response-free-starlink-horizon-union-v1"] = field(
        default="response-free-starlink-horizon-union-v1",
        init=False,
    )


def select_response_free_starlink_population(
    support: CataloguePredictionSupportV1,
    snapshot_payload: SnapshotPayload,
    *,
    tle_snapshot: TleSnapshotRefV1,
    observer_site: ObserverSiteV1,
    tau_policy: ExactTauPolicy,
    field_delta_s: int,
    selection_protocol_digest: Sha256Digest,
    policy: StarlinkHorizonPopulationPolicy | None = None,
) -> ResponseFreeFieldPopulation:
    """Select one complete field-specific Starlink horizon-union population."""

    support = _revalidate_support(support)
    tle_snapshot = _revalidate_snapshot(tle_snapshot)
    observer_site = _revalidate_site(observer_site)
    tau_policy = _revalidate_tau(tau_policy)
    policy = _revalidate_policy(policy)
    if (
        not isinstance(field_delta_s, int)
        or isinstance(field_delta_s, bool)
        or field_delta_s not in (-500, 0, 500)
    ):
        raise CataloguePopulationInputError("field delta must be exactly -500, 0, or +500 s")
    if not _is_digest(selection_protocol_digest):
        raise CataloguePopulationInputError("selection protocol must be a tagged SHA-256 digest")
    raw_bytes = _snapshot_bytes(snapshot_payload)
    if sha256_digest(raw_bytes) != tle_snapshot.digest:
        raise CataloguePopulationInputError("TLE snapshot bytes do not match authority")
    try:
        text = raw_bytes.decode("ascii")
        records = parse_element_set_records(text)
        catalogue = parse_element_sets(text)
    except (UnicodeDecodeError, ElementSetError) as error:
        raise CataloguePopulationInputError(
            "authenticated TLE snapshot is not parseable"
        ) from error
    if not (
        len(records)
        == len(catalogue)
        == tle_snapshot.object_count
        == len(catalogue.satellite_numbers)
    ):
        raise CataloguePopulationInputError("snapshot object inventories do not close")
    if any(
        record.satellite_number != number
        for record, number in zip(records, catalogue.satellite_numbers, strict=True)
    ):
        raise CataloguePopulationInputError("textual and propagated TLE inventories disagree")

    exact_time_upper_bound = len(support.observations) * 3 * len(tau_policy.points)
    if exact_time_upper_bound > policy.maximum_exact_time_count:
        raise CataloguePopulationWorkLimitError(
            "exact field-time inventory exceeds the declared materialization cap"
        )
    exact_times_by_episode = _exact_times_by_episode(
        support,
        tau_policy=tau_policy,
        field_delta_s=field_delta_s,
    )
    exact_times = tuple(
        sorted({value for values in exact_times_by_episode.values() for value in values})
    )
    if len(exact_times) < 3:
        raise CataloguePopulationInputError(
            "field selection requires at least three exact instants"
        )
    if tle_snapshot.collected_utc_ns >= exact_times[0]:
        raise CataloguePopulationInputError("TLE snapshot must be causal for the shifted field")
    starlink_indices = np.asarray(
        [
            index
            for index, record in enumerate(records)
            if record.name.upper().startswith(policy.object_name_prefix)
        ],
        dtype=np.int64,
    )
    if starlink_indices.size == 0:
        raise CataloguePopulationInputError("snapshot contains no named Starlink objects")

    coarse_grid = _uniform_grid(
        exact_times[0],
        exact_times[-1],
        policy.coarse_spacing_s,
        maximum_time_count=policy.maximum_coarse_time_count,
    )
    coarse_work = int(starlink_indices.size) * len(coarse_grid)
    if coarse_work > policy.maximum_coarse_propagated_states:
        raise CataloguePopulationWorkLimitError(
            "coarse Starlink population exceeds the declared propagation cap"
        )
    coarse_tracks = observe_grid(
        propagate_grid(catalogue, coarse_grid, indices=starlink_indices.tolist()),
        observer_site,
        coarse_grid,
    )
    margin_deg = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    coarse_plausible = coarse_tracks.usable & (
        np.min(coarse_tracks.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    coarse_local_rows = np.flatnonzero(
        coarse_plausible & (np.max(coarse_tracks.elevation_deg, axis=1) >= -margin_deg)
    )
    exact_work = int(coarse_local_rows.size) * len(exact_times)
    if exact_work > policy.maximum_exact_propagated_states:
        raise CataloguePopulationWorkLimitError(
            "exact Starlink population exceeds the declared propagation cap"
        )
    exact_grid = SamplingGrid(
        utc_ns=exact_times,
        anchor_index=len(exact_times) // 2,
        spacing_s=float(np.median(np.diff(np.asarray(exact_times, dtype=np.int64))) / 1e9),
    )
    catalogue_indices = starlink_indices[coarse_local_rows]
    exact_tracks = observe_grid(
        propagate_grid(catalogue, exact_grid, indices=catalogue_indices.tolist()),
        observer_site,
        exact_grid,
    )
    exact_plausible = exact_tracks.usable & (
        np.min(exact_tracks.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    exact_column = {value: index for index, value in enumerate(exact_times)}
    eligible_by_catalogue_index: dict[int, tuple[str, ...]] = {}
    for local_row, catalogue_index in enumerate(catalogue_indices):
        if not exact_plausible[local_row]:
            continue
        eligible = tuple(
            episode_id
            for episode_id, times in exact_times_by_episode.items()
            if float(
                np.max(
                    exact_tracks.elevation_deg[
                        local_row,
                        [exact_column[value] for value in times],
                    ]
                )
            )
            >= policy.minimum_elevation_deg
        )
        if eligible:
            eligible_by_catalogue_index[int(catalogue_index)] = eligible

    selected_indices = tuple(sorted(eligible_by_catalogue_index))
    if len(selected_indices) > policy.maximum_selected_candidate_count:
        raise CataloguePopulationWorkLimitError(
            "selected Starlink population exceeds the persisted-contract candidate cap"
        )
    element_epochs = catalogue.element_epoch_utc_ns()
    verified_members = tuple(
        CatalogueVerifiedTleMemberV1(
            catalog_number=catalogue.satellite_numbers[index],
            selected_element_digest=element_pair_digest(
                records[index].first_line,
                records[index].second_line,
            ),
            element_epoch_utc_ns=element_epochs[index],
        )
        for index in selected_indices
    )
    membership_authority_digest = canonical_digest(
        {
            "algorithm_version": "response-free-tle-membership-authority-v1",
            "snapshot_digest": tle_snapshot.digest,
            "members": [item.model_dump(mode="json") for item in verified_members],
        }
    )
    selection_policy_digest = canonical_digest(
        {
            "algorithm_version": _ALGORITHM_VERSION,
            "policy_digest": policy.digest,
            "support_digest": support.content_digest,
            "tle_snapshot": tle_snapshot.model_dump(mode="json"),
            "observer_site": observer_site.model_dump(mode="json"),
            "tau_policy": {
                "policy": tau_policy.policy,
                "points": [
                    {"tau_s": item.tau_s, "log_prior_weight": item.log_prior_weight}
                    for item in tau_policy.points
                ],
            },
            "field_delta_s": field_delta_s,
        }
    )
    universe = FrozenResponseFreeCandidateUniverse(
        candidates=tuple(
            FrozenCatalogueCandidate(
                catalog_number=catalogue.satellite_numbers[index],
                eligible_episode_ids=eligible_by_catalogue_index[index],
            )
            for index in selected_indices
        ),
        selection_protocol_digest=selection_protocol_digest,
        selection_policy_digest=selection_policy_digest,
        tle_membership_authority_digest=membership_authority_digest,
        catalogue_field_delta_s=field_delta_s,
        response_fields_excluded=True,
    )
    receipt_payload = {
        "algorithm_version": _ALGORITHM_VERSION,
        "field_delta_s": field_delta_s,
        "selection_protocol_digest": selection_protocol_digest,
        "selection_policy_digest": selection_policy_digest,
        "tle_membership_authority_digest": membership_authority_digest,
        "snapshot_object_count": tle_snapshot.object_count,
        "starlink_object_count": int(starlink_indices.size),
        "coarse_time_count": len(coarse_grid),
        "exact_time_count": len(exact_times),
        "coarse_candidate_count": int(coarse_local_rows.size),
        "selected_candidate_count": len(selected_indices),
        "coarse_propagation_failure_count": int((~coarse_tracks.usable).sum()),
        "coarse_implausible_altitude_count": int((coarse_tracks.usable & ~coarse_plausible).sum()),
        "exact_propagation_failure_count": int((~exact_tracks.usable).sum()),
        "exact_implausible_altitude_count": int((exact_tracks.usable & ~exact_plausible).sum()),
        "propagation_complete_for_association": bool(
            bool(np.all(coarse_tracks.usable)) and bool(np.all(exact_tracks.usable))
        ),
        "members": [item.model_dump(mode="json") for item in verified_members],
        "eligible_episodes": [
            {
                "catalog_number": candidate.catalog_number,
                "eligible_episode_ids": candidate.eligible_episode_ids,
            }
            for candidate in universe.candidates
        ],
        "response_accessed": False,
        "candidate_ranking_performed": False,
        "candidate_truncation_performed": False,
    }
    return ResponseFreeFieldPopulation(
        field_delta_s=field_delta_s,
        selection_protocol_digest=selection_protocol_digest,
        selection_policy_digest=selection_policy_digest,
        tle_membership_authority_digest=membership_authority_digest,
        universe=universe,
        verified_tle_members=verified_members,
        snapshot_object_count=tle_snapshot.object_count,
        starlink_object_count=int(starlink_indices.size),
        coarse_time_count=len(coarse_grid),
        exact_time_count=len(exact_times),
        coarse_candidate_count=int(coarse_local_rows.size),
        selected_candidate_count=len(selected_indices),
        coarse_propagation_failure_count=int((~coarse_tracks.usable).sum()),
        coarse_implausible_altitude_count=int((coarse_tracks.usable & ~coarse_plausible).sum()),
        exact_propagation_failure_count=int((~exact_tracks.usable).sum()),
        exact_implausible_altitude_count=int((exact_tracks.usable & ~exact_plausible).sum()),
        propagation_complete_for_association=bool(
            bool(np.all(coarse_tracks.usable)) and bool(np.all(exact_tracks.usable))
        ),
        content_digest=canonical_digest(receipt_payload),
    )


def _exact_times_by_episode(
    support: CataloguePredictionSupportV1,
    *,
    tau_policy: ExactTauPolicy,
    field_delta_s: int,
) -> dict[str, tuple[int, ...]]:
    field_delta_ns = field_delta_s * _NS_PER_S
    result: dict[str, tuple[int, ...]] = {}
    for episode_id in support.episode_ids:
        times = {
            instant + field_delta_ns + point.tau_ns
            for observation in support.observations
            if observation.episode_id == episode_id
            for instant in (
                observation.support_start_utc_ns,
                observation.support_center_utc_ns,
                observation.support_end_utc_ns,
            )
            for point in tau_policy.points
        }
        if any(value <= 0 for value in times):
            raise CataloguePopulationInputError("shifted field instants must remain positive UTC")
        result[episode_id] = tuple(sorted(times))
    return result


def _uniform_grid(
    start_ns: int,
    stop_ns: int,
    spacing_s: float,
    *,
    maximum_time_count: int,
) -> SamplingGrid:
    if stop_ns <= start_ns:
        raise CataloguePopulationInputError("population field has no positive duration")
    step_ns = round(spacing_s * _NS_PER_S)
    count = max(3, math.ceil((stop_ns - start_ns) / step_ns) + 1)
    if count + 1 > maximum_time_count:
        raise CataloguePopulationWorkLimitError(
            "coarse field-time inventory exceeds the declared materialization cap"
        )
    values = tuple(start_ns + index * step_ns for index in range(count))
    if values[-1] < stop_ns:
        values = (*values, stop_ns)
    return SamplingGrid(values, len(values) // 2, step_ns / _NS_PER_S)


def _snapshot_bytes(payload: SnapshotPayload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        try:
            return payload.encode("ascii")
        except UnicodeEncodeError as error:
            raise CataloguePopulationInputError("TLE snapshot must be ASCII") from error
    raise CataloguePopulationInputError("TLE snapshot payload must be exact bytes or text")


def _revalidate_support(value: CataloguePredictionSupportV1) -> CataloguePredictionSupportV1:
    try:
        result = CataloguePredictionSupportV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePopulationInputError("prediction support is invalid") from error
    if result.response_fields_excluded is not True:
        raise CataloguePopulationInputError("prediction support must exclude response fields")
    return result


def _revalidate_snapshot(value: TleSnapshotRefV1) -> TleSnapshotRefV1:
    try:
        return TleSnapshotRefV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePopulationInputError("TLE snapshot authority is invalid") from error


def _revalidate_site(value: ObserverSiteV1) -> ObserverSiteV1:
    try:
        return ObserverSiteV1.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePopulationInputError("observer site authority is invalid") from error


def _revalidate_tau(value: ExactTauPolicy) -> ExactTauPolicy:
    try:
        return ExactTauPolicy(policy=value.policy, points=tuple(value.points))
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePopulationInputError("tau policy is invalid") from error


def _revalidate_policy(
    value: StarlinkHorizonPopulationPolicy | None,
) -> StarlinkHorizonPopulationPolicy:
    source = StarlinkHorizonPopulationPolicy() if value is None else value
    try:
        return StarlinkHorizonPopulationPolicy(
            minimum_elevation_deg=source.minimum_elevation_deg,
            coarse_spacing_s=source.coarse_spacing_s,
            maximum_coarse_time_count=source.maximum_coarse_time_count,
            maximum_exact_time_count=source.maximum_exact_time_count,
            maximum_coarse_propagated_states=source.maximum_coarse_propagated_states,
            maximum_exact_propagated_states=source.maximum_exact_propagated_states,
            maximum_selected_candidate_count=source.maximum_selected_candidate_count,
            object_name_prefix=source.object_name_prefix,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePopulationInputError("population policy is invalid") from error


def _is_digest(value: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


__all__ = [
    "CataloguePopulationInputError",
    "CataloguePopulationWorkLimitError",
    "ResponseFreeFieldPopulation",
    "StarlinkHorizonPopulationPolicy",
    "select_response_free_starlink_population",
]
