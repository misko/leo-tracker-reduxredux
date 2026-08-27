"""Response-free SGP4 adapter for a frozen catalogue candidate universe.

This module is the narrow numerical seam between the existing pure sky core and
the catalogue-association contracts.  It does **not** select candidates.  The
caller supplies a candidate universe frozen without looking at measured CFO,
and the output is conditional on that universe.

The adapter accepts the exact snapshot bytes rather than a detached parsed
catalogue.  It authenticates those bytes against ``TleSnapshotRefV1.digest``,
parses them locally, and derives ``selected_element_digest`` from the exact
validated line-1/line-2 pair that reaches SGP4.  It also rechecks catalogue
number, parsed element epoch, unique membership, snapshot size, and causal
snapshot time before propagation.

Prediction is support integrated.  For each observation and candidate tau, the
adapter propagates an odd fixed grid across the shifted aperture, fits a local
cubic Doppler polynomial about the shifted support centre, and contracts that
polynomial with the persisted factorial support moments.  Its declared
conditional-diagonal uncertainty combines an externally chosen floor, a simple
element-age growth term, and local cubic approximation residual in quadrature.
It is an explicit first-slice covariance model, not a claim that SGP4 supplies
an orbit covariance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

import numpy as np

from leo.contracts.catalogue_association import (
    CandidateObservationPredictionV1,
    CandidateTauStateV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportObservationV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.sky.doppler import doppler_shift_hz, fit_doppler_polynomial
from leo.sky.frames import WGS84_SEMI_MAJOR_AXIS_KM
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    ElementSetError,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid

_NS_PER_S = 1_000_000_000
_SECONDS_PER_DAY = 86_400.0
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

TauSearchPolicy = Literal["fixed-tau-zero-v1", "bounded-profile-minus5-plus5-v1"]
SnapshotPayload = bytes | str


class CataloguePredictionInputError(ValueError):
    """Frozen prediction inputs are incomplete, inconsistent, or non-causal."""


class CataloguePropagationError(ValueError):
    """A selected candidate could not produce a physically usable prediction."""


class CataloguePredictionWorkLimitError(ValueError):
    """The declared propagation budget is too small for the frozen universe."""


def _require_digest(value: str, label: str) -> None:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise CataloguePredictionInputError(f"{label} must be a tagged SHA-256 digest")


def _positive_int(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CataloguePredictionInputError(f"{label} must be a positive integer")


@dataclass(frozen=True, slots=True)
class KnownSiteRfAuthority:
    """Immutable known-site and nominal-RF authority supplied by the caller."""

    observer_site: ObserverSiteV1
    nominal_rf_hz: float
    content_digest: Sha256Digest

    @classmethod
    def create(
        cls,
        *,
        observer_site: ObserverSiteV1,
        nominal_rf_hz: float,
    ) -> KnownSiteRfAuthority:
        payload = {
            "algorithm_version": "known-site-rf-authority-v1",
            "observer_site": observer_site.model_dump(mode="json"),
            "nominal_rf_hz": nominal_rf_hz,
        }
        return cls(
            observer_site=observer_site,
            nominal_rf_hz=nominal_rf_hz,
            content_digest=canonical_digest(payload),
        )

    def __post_init__(self) -> None:
        try:
            validated_site = ObserverSiteV1.model_validate(
                self.observer_site.model_dump(mode="json")
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise CataloguePredictionInputError("observer-site authority is invalid") from error
        object.__setattr__(self, "observer_site", validated_site)
        if (
            isinstance(self.nominal_rf_hz, bool)
            or not math.isfinite(self.nominal_rf_hz)
            or self.nominal_rf_hz <= 0.0
        ):
            raise CataloguePredictionInputError("nominal RF must be finite and positive")
        _require_digest(self.content_digest, "site/RF authority digest")
        expected = canonical_digest(
            {
                "algorithm_version": "known-site-rf-authority-v1",
                "observer_site": self.observer_site.model_dump(mode="json"),
                "nominal_rf_hz": self.nominal_rf_hz,
            }
        )
        if self.content_digest != expected:
            raise CataloguePredictionInputError("site/RF authority digest does not match content")


@dataclass(frozen=True, slots=True)
class FrozenCatalogueCandidate:
    """One response-free member of an already-selected candidate universe."""

    catalog_number: int
    eligible_episode_ids: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        _positive_int(self.catalog_number, "candidate catalogue number")
        episodes = tuple(sorted(self.eligible_episode_ids))
        if not episodes or len(set(episodes)) != len(episodes):
            raise CataloguePredictionInputError(
                "candidate eligible episodes must be non-empty and unique"
            )
        for episode_id in episodes:
            _require_digest(episode_id, "eligible episode identity")
        object.__setattr__(self, "eligible_episode_ids", episodes)


@dataclass(frozen=True, slots=True)
class FrozenResponseFreeCandidateUniverse:
    """Candidate membership fixed upstream without response access.

    This is a selection *receipt*, not a selector.  Geometry/visibility logic
    belongs upstream and must freeze both digests and membership before this
    adapter is called.
    """

    candidates: tuple[FrozenCatalogueCandidate, ...]
    selection_protocol_digest: Sha256Digest
    selection_policy_digest: Sha256Digest
    tle_membership_authority_digest: Sha256Digest
    response_fields_excluded: Literal[True] = True

    def __post_init__(self) -> None:
        if self.response_fields_excluded is not True:
            raise CataloguePredictionInputError("candidate universe must be response-free")
        _require_digest(self.selection_protocol_digest, "selection protocol digest")
        _require_digest(self.selection_policy_digest, "selection policy digest")
        _require_digest(
            self.tle_membership_authority_digest,
            "TLE membership authority digest",
        )
        candidates = tuple(sorted(self.candidates, key=lambda item: item.catalog_number))
        numbers = tuple(item.catalog_number for item in candidates)
        if len(set(numbers)) != len(numbers):
            raise CataloguePredictionInputError("frozen candidate numbers must be unique")
        object.__setattr__(self, "candidates", candidates)


@dataclass(frozen=True, slots=True)
class TauGridPoint:
    """One exact, prior-weighted orbital-time sensitivity point."""

    tau_s: float
    log_prior_weight: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.tau_s, bool)
            or not math.isfinite(self.tau_s)
            or not -5.0 <= self.tau_s <= 5.0
        ):
            raise CataloguePredictionInputError("tau must be finite and inside [-5,+5] seconds")
        if isinstance(self.log_prior_weight, bool) or not math.isfinite(self.log_prior_weight):
            raise CataloguePredictionInputError("tau log-prior weight must be finite")
        tau_ns = round(self.tau_s * _NS_PER_S)
        canonical_tau_s = tau_ns / _NS_PER_S
        if self.tau_s != canonical_tau_s:
            raise CataloguePredictionInputError("tau must be canonical at UTC-ns resolution")
        object.__setattr__(self, "tau_s", 0.0 if tau_ns == 0 else canonical_tau_s)

    @property
    def tau_ns(self) -> int:
        return int(round(self.tau_s * _NS_PER_S))


@dataclass(frozen=True, slots=True)
class ExactTauPolicy:
    """The exact tau inventory consumed by every selected candidate."""

    policy: TauSearchPolicy
    points: tuple[TauGridPoint, ...]

    @classmethod
    def fixed_zero(cls) -> ExactTauPolicy:
        return cls(policy="fixed-tau-zero-v1", points=(TauGridPoint(0.0, 0.0),))

    def __post_init__(self) -> None:
        if not self.points or len(self.points) > 401:
            raise CataloguePredictionInputError("tau policy must contain between 1 and 401 points")
        points = tuple(sorted(self.points, key=lambda item: item.tau_s))
        tau_values = tuple(item.tau_s for item in points)
        tau_ns_values = tuple(item.tau_ns for item in points)
        if len(set(tau_ns_values)) != len(tau_ns_values):
            raise CataloguePredictionInputError("tau policy points must be unique in UTC ns")
        if self.policy == "fixed-tau-zero-v1":
            if tau_values != (0.0,):
                raise CataloguePredictionInputError("fixed tau policy requires exactly tau=0")
        elif self.policy == "bounded-profile-minus5-plus5-v1":
            if tau_values[0] != -5.0 or tau_values[-1] != 5.0 or 0.0 not in tau_values:
                raise CataloguePredictionInputError(
                    "bounded tau policy must contain exact -5, 0, and +5 second points"
                )
        else:
            raise CataloguePredictionInputError("unknown tau search policy")
        maximum_log_weight = max(item.log_prior_weight for item in points)
        canonical_points: list[TauGridPoint] = []
        for point in points:
            shifted_weight = point.log_prior_weight - maximum_log_weight
            if not math.isfinite(shifted_weight):
                raise CataloguePredictionInputError(
                    "tau log-prior dynamic range is not representable"
                )
            canonical_points.append(
                TauGridPoint(
                    tau_s=point.tau_s,
                    log_prior_weight=0.0 if shifted_weight == 0.0 else shifted_weight,
                )
            )
        object.__setattr__(self, "points", tuple(canonical_points))


@dataclass(frozen=True, slots=True)
class Sgp4SupportPredictionPolicy:
    """Fixed support quadrature, diagonal uncertainty, and work-bound policy."""

    integration_sample_count: int = 7
    standard_uncertainty_floor_hz: float = 1.0
    element_age_growth_hz_per_day: float = 0.0
    fit_residual_multiplier: float = 1.0
    maximum_propagated_states: int = 1_000_000

    def __post_init__(self) -> None:
        if (
            not isinstance(self.integration_sample_count, int)
            or isinstance(self.integration_sample_count, bool)
            or not 5 <= self.integration_sample_count <= 33
            or self.integration_sample_count % 2 == 0
        ):
            raise CataloguePredictionInputError(
                "integration sample count must be an odd integer from 5 through 33"
            )
        for value, label in (
            (self.standard_uncertainty_floor_hz, "uncertainty floor"),
            (self.element_age_growth_hz_per_day, "element-age uncertainty growth"),
            (self.fit_residual_multiplier, "fit-residual multiplier"),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise CataloguePredictionInputError(f"{label} must be finite and nonnegative")
        if self.standard_uncertainty_floor_hz <= 0.0:
            raise CataloguePredictionInputError("uncertainty floor must be positive")
        _positive_int(self.maximum_propagated_states, "maximum propagated states")

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(
            {
                "algorithm_version": "sgp4-support-prediction-policy-v1",
                "integration_sample_count": self.integration_sample_count,
                "standard_uncertainty_floor_hz": self.standard_uncertainty_floor_hz,
                "element_age_growth_hz_per_day": self.element_age_growth_hz_per_day,
                "fit_residual_multiplier": self.fit_residual_multiplier,
                "maximum_propagated_states": self.maximum_propagated_states,
            }
        )


def element_pair_digest(first_line: str, second_line: str) -> Sha256Digest:
    """Digest the exact validated element pair in its propagation form.

    Snapshot envelope bytes (including names, blank lines, and newline style)
    are authenticated separately by ``TleSnapshotRefV1.digest``.  The selected
    element identity is the two 69-column lines, joined by one ASCII newline,
    exactly as the parser supplies them to SGP4.
    """

    try:
        payload = f"{first_line}\n{second_line}".encode("ascii")
    except UnicodeEncodeError as error:
        raise CataloguePredictionInputError("element pair must be ASCII") from error
    return sha256_digest(payload)


def _revalidate_contract_inputs(
    *,
    support: CataloguePredictionSupportV1,
    tle_snapshot: TleSnapshotRefV1,
    verified_tle_members: tuple[CatalogueVerifiedTleMemberV1, ...],
) -> tuple[
    CataloguePredictionSupportV1,
    TleSnapshotRefV1,
    tuple[CatalogueVerifiedTleMemberV1, ...],
]:
    """Close ``model_copy`` validator bypasses before any numerical work."""

    try:
        validated_support = CataloguePredictionSupportV1.model_validate(
            support.model_dump(mode="json")
        )
        validated_snapshot = TleSnapshotRefV1.model_validate(tle_snapshot.model_dump(mode="json"))
        validated_members = tuple(
            CatalogueVerifiedTleMemberV1.model_validate(item.model_dump(mode="json"))
            for item in verified_tle_members
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePredictionInputError(
            "prediction contracts must be valid, closed V1 documents"
        ) from error
    if validated_support.response_fields_excluded is not True:
        raise CataloguePredictionInputError("prediction support must exclude response fields")
    return validated_support, validated_snapshot, validated_members


def _revalidate_adapter_inputs(
    *,
    site_rf_authority: KnownSiteRfAuthority,
    candidate_universe: FrozenResponseFreeCandidateUniverse,
    tau_policy: ExactTauPolicy,
    prediction_policy: Sgp4SupportPredictionPolicy | None,
) -> tuple[
    KnownSiteRfAuthority,
    FrozenResponseFreeCandidateUniverse,
    ExactTauPolicy,
    Sgp4SupportPredictionPolicy,
]:
    """Rebuild frozen dataclasses so low-level mutation cannot bypass preflight."""

    try:
        validated_site_rf = KnownSiteRfAuthority(
            observer_site=site_rf_authority.observer_site,
            nominal_rf_hz=site_rf_authority.nominal_rf_hz,
            content_digest=site_rf_authority.content_digest,
        )
        validated_universe = FrozenResponseFreeCandidateUniverse(
            candidates=tuple(
                FrozenCatalogueCandidate(
                    catalog_number=item.catalog_number,
                    eligible_episode_ids=item.eligible_episode_ids,
                )
                for item in candidate_universe.candidates
            ),
            selection_protocol_digest=candidate_universe.selection_protocol_digest,
            selection_policy_digest=candidate_universe.selection_policy_digest,
            tle_membership_authority_digest=(candidate_universe.tle_membership_authority_digest),
            response_fields_excluded=candidate_universe.response_fields_excluded,
        )
        validated_tau = ExactTauPolicy(
            policy=tau_policy.policy,
            points=tau_policy.points,
        )
        source_policy = (
            Sgp4SupportPredictionPolicy() if prediction_policy is None else prediction_policy
        )
        validated_prediction = Sgp4SupportPredictionPolicy(
            integration_sample_count=source_policy.integration_sample_count,
            standard_uncertainty_floor_hz=source_policy.standard_uncertainty_floor_hz,
            element_age_growth_hz_per_day=source_policy.element_age_growth_hz_per_day,
            fit_residual_multiplier=source_policy.fit_residual_multiplier,
            maximum_propagated_states=source_policy.maximum_propagated_states,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePredictionInputError("adapter policies must be valid and frozen") from error
    return validated_site_rf, validated_universe, validated_tau, validated_prediction


def _authenticate_and_parse_snapshot(
    *,
    snapshot_payload: SnapshotPayload,
    tle_snapshot: TleSnapshotRefV1,
) -> tuple[ElementSetCatalogue, tuple[Sha256Digest, ...]]:
    if isinstance(snapshot_payload, bytes):
        raw_bytes = snapshot_payload
    elif isinstance(snapshot_payload, str):
        try:
            raw_bytes = snapshot_payload.encode("ascii")
        except UnicodeEncodeError as error:
            raise CataloguePredictionInputError("TLE snapshot must be ASCII") from error
    else:
        raise CataloguePredictionInputError("TLE snapshot payload must be exact bytes or text")
    if sha256_digest(raw_bytes) != tle_snapshot.digest:
        raise CataloguePredictionInputError("TLE snapshot bytes do not match the authority digest")
    try:
        snapshot_text = raw_bytes.decode("ascii")
        catalogue = parse_element_sets(snapshot_text)
    except (UnicodeDecodeError, ElementSetError) as error:
        raise CataloguePredictionInputError(
            "authenticated TLE snapshot is not parseable"
        ) from error
    pair_digests = _element_pair_digests(snapshot_text)
    if len(pair_digests) != len(catalogue):
        raise CataloguePredictionInputError("parsed TLE element-pair inventory is inconsistent")
    return catalogue, pair_digests


def _element_pair_digests(snapshot_text: str) -> tuple[Sha256Digest, ...]:
    # This mirrors parse_element_sets' accepted 3LE/2LE envelope grammar.  The
    # parser has already validated every pair's width, checksum, and identity.
    lines = [line.rstrip() for line in snapshot_text.splitlines() if line.strip()]
    result: list[Sha256Digest] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith(("1 ", "2 ")):
            index += 1
        if index + 1 >= len(lines):
            raise CataloguePredictionInputError("TLE snapshot ends mid-record")
        result.append(element_pair_digest(lines[index], lines[index + 1]))
        index += 2
    return tuple(result)


def build_sgp4_catalogue_prediction_bank(
    support: CataloguePredictionSupportV1,
    snapshot_payload: SnapshotPayload,
    *,
    tle_snapshot: TleSnapshotRefV1,
    site_rf_authority: KnownSiteRfAuthority,
    candidate_universe: FrozenResponseFreeCandidateUniverse,
    verified_tle_members: tuple[CatalogueVerifiedTleMemberV1, ...],
    tau_policy: ExactTauPolicy,
    prediction_policy: Sgp4SupportPredictionPolicy | None = None,
) -> CataloguePredictionBankV1:
    """Predict the complete frozen candidate universe without response access.

    All structural, chronology, membership, and work-bound checks finish before
    the first SGP4 state is materialized.  The function never builds or changes
    candidate membership; ``source_candidate_count`` therefore equals the
    returned count and truncation is always zero.
    """

    support, tle_snapshot, verified_tle_members = _revalidate_contract_inputs(
        support=support,
        tle_snapshot=tle_snapshot,
        verified_tle_members=verified_tle_members,
    )
    site_rf_authority, candidate_universe, tau_policy, policy = _revalidate_adapter_inputs(
        site_rf_authority=site_rf_authority,
        candidate_universe=candidate_universe,
        tau_policy=tau_policy,
        prediction_policy=prediction_policy,
    )
    catalogue, selected_element_digests = _authenticate_and_parse_snapshot(
        snapshot_payload=snapshot_payload,
        tle_snapshot=tle_snapshot,
    )
    _validate_snapshot_and_catalogue(
        support=support,
        catalogue=catalogue,
        tle_snapshot=tle_snapshot,
    )
    member_by_number, index_by_number, epoch_by_number = _validate_frozen_membership(
        catalogue=catalogue,
        candidate_universe=candidate_universe,
        verified_tle_members=verified_tle_members,
        selected_element_digests=selected_element_digests,
    )
    observations_by_episode = _support_observations_by_episode(support)
    _preflight_candidate_coverage(
        candidate_universe=candidate_universe,
        observations_by_episode=observations_by_episode,
    )
    _preflight_shifted_instants(
        candidate_universe=candidate_universe,
        observations_by_episode=observations_by_episode,
        tau_policy=tau_policy,
    )
    _preflight_work_bound(
        candidate_universe=candidate_universe,
        observations_by_episode=observations_by_episode,
        tau_policy=tau_policy,
        prediction_policy=policy,
    )

    reference_utc_ns = min(item.support_center_utc_ns for item in support.observations)
    candidates: list[CatalogueCandidatePredictionV1] = []
    for selected in candidate_universe.candidates:
        member = member_by_number[selected.catalog_number]
        observations = tuple(
            observation
            for episode_id in selected.eligible_episode_ids
            for observation in observations_by_episode[episode_id]
        )
        tau_states = tuple(
            _predict_candidate_tau_state(
                catalogue=catalogue,
                catalogue_index=index_by_number[selected.catalog_number],
                observations=observations,
                tau_point=point,
                element_epoch_utc_ns=epoch_by_number[selected.catalog_number],
                nominal_rf_hz=site_rf_authority.nominal_rf_hz,
                observer_site=site_rf_authority.observer_site,
                prediction_policy=policy,
            )
            for point in tau_policy.points
        )
        object_name = catalogue.names[index_by_number[selected.catalog_number]][:128]
        candidates.append(
            CatalogueCandidatePredictionV1(
                catalog_number=selected.catalog_number,
                object_name=object_name,
                selected_element_digest=member.selected_element_digest,
                element_epoch_utc_ns=member.element_epoch_utc_ns,
                element_age_s_at_reference=(
                    abs(reference_utc_ns - member.element_epoch_utc_ns) / _NS_PER_S
                ),
                eligible_episode_ids=selected.eligible_episode_ids,
                tau_states=tau_states,
            )
        )

    propagation_configuration_digest = canonical_digest(
        {
            "algorithm_version": "sgp4-wgs72-local-cubic-diagonal-v1",
            "site_rf_authority_digest": site_rf_authority.content_digest,
            "prediction_policy_digest": policy.digest,
        }
    )
    propagation_model = (
        "sgp4-wgs72-local-cubic-diagonal-v1-"
        f"{propagation_configuration_digest.removeprefix('sha256:')}"
    )
    return CataloguePredictionBankV1.create(
        support=support,
        tle_snapshot=tle_snapshot,
        observer_site=site_rf_authority.observer_site,
        nominal_rf_hz=site_rf_authority.nominal_rf_hz,
        selection_protocol_digest=candidate_universe.selection_protocol_digest,
        selection_policy_digest=candidate_universe.selection_policy_digest,
        tle_membership_authority_digest=(candidate_universe.tle_membership_authority_digest),
        verified_tle_members=verified_tle_members,
        propagation_model=propagation_model,
        candidates=tuple(candidates),
        source_candidate_count=len(candidate_universe.candidates),
        tau_search_policy=tau_policy.policy,
    )


def _validate_snapshot_and_catalogue(
    *,
    support: CataloguePredictionSupportV1,
    catalogue: ElementSetCatalogue,
    tle_snapshot: TleSnapshotRefV1,
) -> None:
    if not isinstance(catalogue, ElementSetCatalogue):
        raise CataloguePredictionInputError("catalogue must be parsed before prediction")
    catalogue_size = len(catalogue)
    if not (
        catalogue_size
        == len(catalogue.names)
        == len(catalogue.satellite_numbers)
        == len(catalogue.satellites)
    ):
        raise CataloguePredictionInputError("parsed catalogue columns have inconsistent lengths")
    if tle_snapshot.object_count != catalogue_size:
        raise CataloguePredictionInputError(
            "snapshot object count must exactly match the parsed catalogue"
        )
    if len(set(catalogue.satellite_numbers)) != catalogue_size:
        raise CataloguePredictionInputError(
            "parsed catalogue must contain exactly one element per catalogue number"
        )
    if tle_snapshot.collected_utc_ns >= min(
        item.support_start_utc_ns for item in support.observations
    ):
        raise CataloguePredictionInputError(
            "catalogue TLE snapshot must be strictly pre-measurement"
        )
    if any(
        int(satellite.satnum) != catalog_number
        for catalog_number, satellite in zip(
            catalogue.satellite_numbers,
            catalogue.satellites,
            strict=True,
        )
    ):
        raise CataloguePredictionInputError(
            "parsed satellite identity disagrees with catalogue inventory"
        )


def _validate_frozen_membership(
    *,
    catalogue: ElementSetCatalogue,
    candidate_universe: FrozenResponseFreeCandidateUniverse,
    verified_tle_members: tuple[CatalogueVerifiedTleMemberV1, ...],
    selected_element_digests: tuple[Sha256Digest, ...],
) -> tuple[
    dict[int, CatalogueVerifiedTleMemberV1],
    dict[int, int],
    dict[int, int],
]:
    selected_numbers = tuple(item.catalog_number for item in candidate_universe.candidates)
    members = tuple(sorted(verified_tle_members, key=lambda item: item.catalog_number))
    member_numbers = tuple(item.catalog_number for item in members)
    if member_numbers != selected_numbers or len(set(member_numbers)) != len(member_numbers):
        raise CataloguePredictionInputError(
            "verified TLE membership must exactly cover the frozen candidate universe"
        )
    indices_by_number: dict[int, list[int]] = {}
    for index, catalog_number in enumerate(catalogue.satellite_numbers):
        indices_by_number.setdefault(catalog_number, []).append(index)
    selected_index_by_number: dict[int, int] = {}
    for catalog_number in selected_numbers:
        indices = indices_by_number.get(catalog_number, [])
        if len(indices) != 1:
            raise CataloguePredictionInputError(
                "each frozen candidate must resolve to exactly one parsed element"
            )
        selected_index_by_number[catalog_number] = indices[0]
    parsed_epochs = catalogue.element_epoch_utc_ns()
    member_by_number = {item.catalog_number: item for item in members}
    epoch_by_number = {
        number: parsed_epochs[index] for number, index in selected_index_by_number.items()
    }
    if any(
        member_by_number[number].element_epoch_utc_ns != epoch_by_number[number]
        for number in selected_numbers
    ):
        raise CataloguePredictionInputError(
            "verified member epoch disagrees with the parsed element epoch"
        )
    if any(
        member_by_number[number].selected_element_digest
        != selected_element_digests[selected_index_by_number[number]]
        for number in selected_numbers
    ):
        raise CataloguePredictionInputError(
            "verified selected-element digest disagrees with the exact propagated line pair"
        )
    return member_by_number, selected_index_by_number, epoch_by_number


def _support_observations_by_episode(
    support: CataloguePredictionSupportV1,
) -> dict[str, tuple[CataloguePredictionSupportObservationV1, ...]]:
    return {
        episode_id: tuple(item for item in support.observations if item.episode_id == episode_id)
        for episode_id in support.episode_ids
    }


def _preflight_candidate_coverage(
    *,
    candidate_universe: FrozenResponseFreeCandidateUniverse,
    observations_by_episode: dict[str, tuple[CataloguePredictionSupportObservationV1, ...]],
) -> None:
    known_episodes = set(observations_by_episode)
    for candidate in candidate_universe.candidates:
        if not set(candidate.eligible_episode_ids) <= known_episodes:
            raise CataloguePredictionInputError(
                "frozen candidate names an unknown prediction-support episode"
            )
        observation_count = sum(
            len(observations_by_episode[episode_id])
            for episode_id in candidate.eligible_episode_ids
        )
        if observation_count < 2:
            raise CataloguePredictionInputError(
                "each candidate must predict at least two support observations"
            )


def _preflight_shifted_instants(
    *,
    candidate_universe: FrozenResponseFreeCandidateUniverse,
    observations_by_episode: dict[str, tuple[CataloguePredictionSupportObservationV1, ...]],
    tau_policy: ExactTauPolicy,
) -> None:
    selected_episodes = {
        episode_id
        for candidate in candidate_universe.candidates
        for episode_id in candidate.eligible_episode_ids
    }
    if not selected_episodes:
        return
    observations = tuple(
        observation
        for episode_id in selected_episodes
        for observation in observations_by_episode[episode_id]
    )
    earliest_shifted = min(item.support_start_utc_ns for item in observations) + min(
        item.tau_ns for item in tau_policy.points
    )
    latest_shifted = max(item.support_end_utc_ns for item in observations) + max(
        item.tau_ns for item in tau_policy.points
    )
    if earliest_shifted <= 0 or latest_shifted > np.iinfo(np.int64).max:
        raise CataloguePredictionInputError(
            "all tau-shifted support instants must fit positive signed UTC ns"
        )


def _preflight_work_bound(
    *,
    candidate_universe: FrozenResponseFreeCandidateUniverse,
    observations_by_episode: dict[str, tuple[CataloguePredictionSupportObservationV1, ...]],
    tau_policy: ExactTauPolicy,
    prediction_policy: Sgp4SupportPredictionPolicy,
) -> None:
    # Each observation contributes at most sample_count uniform knots plus its
    # support centre.  This conservative integer bound is evaluated without
    # constructing any time grid or propagation array.
    work_upper_bound = 0
    per_observation = prediction_policy.integration_sample_count + 1
    for candidate in candidate_universe.candidates:
        observation_count = sum(
            len(observations_by_episode[episode_id])
            for episode_id in candidate.eligible_episode_ids
        )
        work_upper_bound += observation_count * per_observation * len(tau_policy.points)
        if work_upper_bound > prediction_policy.maximum_propagated_states:
            raise CataloguePredictionWorkLimitError(
                "frozen candidate prediction exceeds the declared propagation-work cap "
                f"({work_upper_bound} > {prediction_policy.maximum_propagated_states})"
            )


def _integration_knots(
    observation: CataloguePredictionSupportObservationV1,
    sample_count: int,
) -> tuple[int, ...]:
    span_ns = observation.support_end_utc_ns - observation.support_start_utc_ns
    knots = {
        observation.support_start_utc_ns + span_ns * index // (sample_count - 1)
        for index in range(sample_count)
    }
    knots.add(observation.support_center_utc_ns)
    return tuple(sorted(knots))


def _predict_candidate_tau_state(
    *,
    catalogue: ElementSetCatalogue,
    catalogue_index: int,
    observations: tuple[CataloguePredictionSupportObservationV1, ...],
    tau_point: TauGridPoint,
    element_epoch_utc_ns: int,
    nominal_rf_hz: float,
    observer_site: ObserverSiteV1,
    prediction_policy: Sgp4SupportPredictionPolicy,
) -> CandidateTauStateV1:
    knots_by_observation = {
        item.observation_id: tuple(
            instant + tau_point.tau_ns
            for instant in _integration_knots(
                item,
                prediction_policy.integration_sample_count,
            )
        )
        for item in observations
    }
    all_instants = set(instant for knots in knots_by_observation.values() for instant in knots)
    if not all_instants or min(all_instants) <= 0:
        raise CataloguePredictionInputError("tau-shifted prediction instant must be positive")
    # SamplingGrid needs at least three instants.  Ultra-short valid supports
    # can collapse to two distinct nanoseconds; extra propagation-only knots do
    # not change the lower-order local fit used for that support.
    while len(all_instants) < 3:
        candidate = max(all_instants) + 1
        all_instants.add(candidate)
    ordered_instants = tuple(sorted(all_instants))
    positive_spacings = tuple(
        right - left
        for left, right in zip(ordered_instants, ordered_instants[1:], strict=False)
        if right > left
    )
    shifted_reference = min(item.support_center_utc_ns for item in observations) + tau_point.tau_ns
    grid = SamplingGrid(
        utc_ns=ordered_instants,
        anchor_index=ordered_instants.index(shifted_reference),
        spacing_s=min(positive_spacings) / _NS_PER_S,
    )
    propagated = propagate_grid(catalogue, grid, indices=(catalogue_index,))
    if propagated.error_code.shape != (1, len(grid)) or not bool(propagated.usable[0]):
        raise CataloguePropagationError("selected candidate failed SGP4 propagation")
    altitude_km = np.linalg.norm(propagated.position_teme_km[0], axis=1) - WGS84_SEMI_MAJOR_AXIS_KM
    if np.any(~np.isfinite(altitude_km)) or np.any(altitude_km <= MINIMUM_PLAUSIBLE_ALTITUDE_KM):
        raise CataloguePropagationError("selected candidate has an implausible propagated altitude")
    tracks = observe_grid(propagated, observer_site, grid)
    range_rate = np.asarray(tracks.range_rate_km_s[0], dtype=np.float64)
    if range_rate.shape != (len(grid),) or not np.isfinite(range_rate).all():
        raise CataloguePropagationError("selected candidate produced invalid range rate")
    shift_hz = np.asarray(doppler_shift_hz(nominal_rf_hz, range_rate), dtype=np.float64)
    index_by_instant = {instant: index for index, instant in enumerate(ordered_instants)}

    predictions: list[CandidateObservationPredictionV1] = []
    for observation in observations:
        knots = knots_by_observation[observation.observation_id]
        reference_utc_ns = observation.support_center_utc_ns + tau_point.tau_ns
        offsets_s = np.asarray(
            [(instant - reference_utc_ns) / _NS_PER_S for instant in knots],
            dtype=np.float64,
        )
        local_shift_hz = np.asarray(
            [shift_hz[index_by_instant[instant]] for instant in knots],
            dtype=np.float64,
        )
        polynomial = fit_doppler_polynomial(
            offsets_s,
            local_shift_hz,
            downlink_frequency_hz=nominal_rf_hz,
            reference_utc_ns=reference_utc_ns,
            degree=3,
        )
        moment_zero, moment_one, moment_two, moment_three = observation.factorial_support_moments_s
        integrated_hz = (
            polynomial.frequency_at_reference_hz * moment_zero
            + polynomial.slope_hz_s * moment_one
            + polynomial.acceleration_hz_s2 * moment_two
            + polynomial.jerk_hz_s3 * moment_three
        )
        age_days = abs(reference_utc_ns - element_epoch_utc_ns) / (_NS_PER_S * _SECONDS_PER_DAY)
        standard_uncertainty_hz = math.hypot(
            prediction_policy.standard_uncertainty_floor_hz,
            prediction_policy.element_age_growth_hz_per_day * age_days,
            prediction_policy.fit_residual_multiplier * polynomial.residual_rms_hz,
        )
        if not math.isfinite(integrated_hz) or not math.isfinite(standard_uncertainty_hz):
            raise CataloguePropagationError("support-integrated prediction is not finite")
        predictions.append(
            CandidateObservationPredictionV1(
                observation_id=observation.observation_id,
                predicted_cfo_hz=integrated_hz,
                standard_uncertainty_hz=standard_uncertainty_hz,
            )
        )
    return CandidateTauStateV1(
        tau_s=tau_point.tau_s,
        log_prior_weight=tau_point.log_prior_weight,
        predictions=tuple(sorted(predictions, key=lambda item: item.observation_id)),
    )
