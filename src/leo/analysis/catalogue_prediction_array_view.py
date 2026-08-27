"""Pure, path-free array port for complete catalogue prediction banks.

The immutable public wire contract remains :class:`CataloguePredictionBankV1`.
Large opened-development runs may authenticate that contract into read-only
array storage, then borrow the resulting arrays through this narrow view.  The
view deliberately contains no filesystem, database, HTTP, or CLI behavior, so
pure analyzers do not depend on a concrete storage adapter.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass, replace
from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray

from leo.contracts.catalogue_association import (
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import Sha256Digest, canonical_json_bytes
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

type CatalogueFieldDelta = Literal[-500, 0, 500]
type CatalogueTauSearchPolicy = Literal[
    "fixed-tau-zero-v1",
    "bounded-profile-minus5-plus5-v1",
]


class CataloguePredictionArrayViewError(ValueError):
    """The borrowed array inventory or its public authority is invalid."""


@dataclass(frozen=True, slots=True)
class CatalogueArrayCandidateAuthority:
    catalog_number: int
    object_name: str
    selected_element_digest: Sha256Digest
    element_epoch_utc_ns: int
    element_age_s_at_reference: float
    eligible_episode_ids: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.catalog_number, bool)
            or not isinstance(self.catalog_number, int)
            or self.catalog_number <= 0
            or not self.object_name
            or not _is_digest(self.selected_element_digest)
            or isinstance(self.element_epoch_utc_ns, bool)
            or not isinstance(self.element_epoch_utc_ns, int)
            or self.element_epoch_utc_ns <= 0
            or not math.isfinite(self.element_age_s_at_reference)
            or self.element_age_s_at_reference < 0.0
            or not self.eligible_episode_ids
            or self.eligible_episode_ids != tuple(sorted(set(self.eligible_episode_ids)))
            or any(not _is_digest(item) for item in self.eligible_episode_ids)
        ):
            raise CataloguePredictionArrayViewError("array-view candidate authority is invalid")


@dataclass(frozen=True, slots=True)
class CatalogueArrayTauAuthority:
    tau_s: float
    log_prior_weight: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.tau_s, bool)
            or not math.isfinite(self.tau_s)
            or not -5.0 <= self.tau_s <= 5.0
            or isinstance(self.log_prior_weight, bool)
            or not math.isfinite(self.log_prior_weight)
        ):
            raise CataloguePredictionArrayViewError("array-view tau authority is invalid")


@dataclass(frozen=True, slots=True)
class CataloguePredictionArrayBankView:
    """Borrowed complete prediction cube with authenticated public metadata."""

    field_delta_s: CatalogueFieldDelta
    support: CataloguePredictionSupportV1
    tle_snapshot: TleSnapshotRefV1
    observer_site: ObserverSiteV1
    nominal_rf_hz: float
    prediction_reference_utc_ns: int
    selection_protocol_digest: Sha256Digest
    selection_policy_digest: Sha256Digest
    tle_membership_authority_digest: Sha256Digest
    verified_tle_members: tuple[CatalogueVerifiedTleMemberV1, ...]
    candidate_universe_digest: Sha256Digest
    tau_search_policy: CatalogueTauSearchPolicy
    propagation_model: str
    candidate_authority: tuple[CatalogueArrayCandidateAuthority, ...]
    tau_authority: tuple[CatalogueArrayTauAuthority, ...]
    observation_ids: tuple[Sha256Digest, ...]
    predicted_cfo_hz: NDArray[np.float64]
    standard_uncertainty_hz: NDArray[np.float64]
    public_bank_content_digest: Sha256Digest
    prediction_inventory_authority_digest: Sha256Digest
    public_content_digest_verified: Literal[True] = True
    response_free: Literal[True] = True
    complete_candidate_tau_inventory: Literal[True] = True

    def __post_init__(self) -> None:
        try:
            support = CataloguePredictionSupportV1.model_validate(
                self.support.model_dump(mode="json")
            )
            snapshot = TleSnapshotRefV1.model_validate(self.tle_snapshot.model_dump(mode="json"))
            site = ObserverSiteV1.model_validate(self.observer_site.model_dump(mode="json"))
            members = tuple(
                CatalogueVerifiedTleMemberV1.model_validate(item.model_dump(mode="json"))
                for item in self.verified_tle_members
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise CataloguePredictionArrayViewError(
                "array-view public authority contracts are invalid"
            ) from error
        object.__setattr__(self, "support", support)
        object.__setattr__(self, "tle_snapshot", snapshot)
        object.__setattr__(self, "observer_site", site)
        object.__setattr__(self, "verified_tle_members", members)
        if (
            self.field_delta_s not in (-500, 0, 500)
            or isinstance(self.nominal_rf_hz, bool)
            or not math.isfinite(self.nominal_rf_hz)
            or self.nominal_rf_hz <= 0.0
            or isinstance(self.prediction_reference_utc_ns, bool)
            or not isinstance(self.prediction_reference_utc_ns, int)
            or self.prediction_reference_utc_ns <= 0
            or not self.propagation_model
        ):
            raise CataloguePredictionArrayViewError("array-view physical authority is invalid")
        expected_reference = min(item.support_center_utc_ns for item in support.observations)
        if self.prediction_reference_utc_ns != expected_reference:
            raise CataloguePredictionArrayViewError(
                "array-view prediction reference differs from response-free support"
            )
        if snapshot.collected_utc_ns >= min(
            item.support_start_utc_ns for item in support.observations
        ):
            raise CataloguePredictionArrayViewError(
                "array-view TLE snapshot is not strictly pre-measurement"
            )
        for value in (
            self.selection_protocol_digest,
            self.selection_policy_digest,
            self.tle_membership_authority_digest,
            self.candidate_universe_digest,
            self.public_bank_content_digest,
            self.prediction_inventory_authority_digest,
        ):
            if not _is_digest(value):
                raise CataloguePredictionArrayViewError("array-view authority must be digest-bound")
        if (
            self.public_content_digest_verified is not True
            or self.response_free is not True
            or self.complete_candidate_tau_inventory is not True
            or self.support.response_fields_excluded is not True
        ):
            raise CataloguePredictionArrayViewError(
                "array view is not an authenticated complete response-free inventory"
            )
        numbers = tuple(item.catalog_number for item in self.candidate_authority)
        if not numbers or numbers != tuple(sorted(set(numbers))):
            raise CataloguePredictionArrayViewError(
                "array-view candidates must be nonempty, unique, and ordered"
            )
        member_keys = tuple(
            (item.catalog_number, item.selected_element_digest, item.element_epoch_utc_ns)
            for item in members
        )
        candidate_keys = tuple(
            (item.catalog_number, item.selected_element_digest, item.element_epoch_utc_ns)
            for item in self.candidate_authority
        )
        if member_keys != candidate_keys:
            raise CataloguePredictionArrayViewError(
                "array-view verified membership differs from candidates"
            )
        if snapshot.object_count < len(members):
            raise CataloguePredictionArrayViewError(
                "array-view verified membership exceeds the TLE snapshot"
            )
        support_episode_ids = set(support.episode_ids)
        for candidate in self.candidate_authority:
            expected_age_s = (
                abs(self.prediction_reference_utc_ns - candidate.element_epoch_utc_ns) / 1e9
            )
            if not math.isclose(
                candidate.element_age_s_at_reference,
                expected_age_s,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise CataloguePredictionArrayViewError(
                    "array-view candidate age differs from its prediction reference"
                )
            if set(candidate.eligible_episode_ids) != support_episode_ids:
                raise CataloguePredictionArrayViewError(
                    "array-view candidates must cover the complete support episode inventory"
                )
        tau_values = tuple(item.tau_s for item in self.tau_authority)
        if not tau_values or tau_values != tuple(sorted(set(tau_values))) or 0.0 not in tau_values:
            raise CataloguePredictionArrayViewError(
                "array-view tau inventory must be unique, ordered, and contain zero"
            )
        if self.tau_search_policy == "fixed-tau-zero-v1" and tau_values != (0.0,):
            raise CataloguePredictionArrayViewError(
                "fixed array-view tau policy requires exact zero"
            )
        if self.tau_search_policy == "bounded-profile-minus5-plus5-v1" and not (
            tau_values[0] == -5.0 and tau_values[-1] == 5.0
        ):
            raise CataloguePredictionArrayViewError(
                "bounded array-view tau policy must close [-5,+5]"
            )
        support_ids = {item.observation_id for item in support.observations}
        if (
            not self.observation_ids
            or self.observation_ids != tuple(sorted(set(self.observation_ids)))
            or set(self.observation_ids) != support_ids
        ):
            raise CataloguePredictionArrayViewError(
                "array-view observation inventory differs from support"
            )
        shape = (len(numbers), len(tau_values), len(self.observation_ids))
        for array, label in (
            (self.predicted_cfo_hz, "prediction"),
            (self.standard_uncertainty_hz, "uncertainty"),
        ):
            if (
                not isinstance(array, np.ndarray)
                or array.shape != shape
                or array.dtype != np.dtype("<f8")
                or array.flags.writeable
            ):
                raise CataloguePredictionArrayViewError(
                    f"array-view {label} cube shape, dtype, or mutability is invalid"
                )
        _validate_finite_cubes(self.predicted_cfo_hz, self.standard_uncertainty_hz)
        expected_inventory_authority = catalogue_prediction_inventory_authority_digest(
            field_delta_s=self.field_delta_s,
            public_bank_content_digest=self.public_bank_content_digest,
            candidate_authority=self.candidate_authority,
            tau_authority=self.tau_authority,
            observation_ids=self.observation_ids,
            predicted_cfo_hz=self.predicted_cfo_hz,
            standard_uncertainty_hz=self.standard_uncertainty_hz,
        )
        if self.prediction_inventory_authority_digest != expected_inventory_authority:
            raise CataloguePredictionArrayViewError(
                "array-view prediction inventory authority differs from its axes or cube bytes"
            )

    @property
    def candidate_catalog_numbers(self) -> tuple[int, ...]:
        return tuple(item.catalog_number for item in self.candidate_authority)

    @property
    def tau_values_s(self) -> tuple[float, ...]:
        return tuple(item.tau_s for item in self.tau_authority)

    @property
    def content_digest(self) -> Sha256Digest:
        """Compatibility alias for the authenticated public wire-bank digest."""

        return self.public_bank_content_digest


def catalogue_prediction_array_view_from_bank(
    bank: CataloguePredictionBankV1,
    *,
    field_delta_s: CatalogueFieldDelta,
) -> CataloguePredictionArrayBankView:
    """Authenticate and materialize a wire bank into the pure array port."""

    try:
        validated = CataloguePredictionBankV1.model_validate(bank.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePredictionArrayViewError("public prediction bank is invalid") from error
    if (
        validated.response_accessed is not False
        or validated.support.response_fields_excluded is not True
        or validated.truncated_candidate_count != 0
        or validated.source_candidate_count != validated.returned_candidate_count
        or validated.returned_candidate_count != len(validated.candidates)
    ):
        raise CataloguePredictionArrayViewError(
            "public prediction bank is incomplete or response-bearing"
        )
    candidates = tuple(sorted(validated.candidates, key=lambda item: item.catalog_number))
    tau_values = tuple(item.tau_s for item in candidates[0].tau_states)
    if any(
        tuple(item.tau_s for item in candidate.tau_states) != tau_values for candidate in candidates
    ):
        raise CataloguePredictionArrayViewError("public candidate tau grids differ")
    observation_ids = tuple(sorted(item.observation_id for item in validated.support.observations))
    shape = (len(candidates), len(tau_values), len(observation_ids))
    predictions = np.empty(shape, dtype=np.dtype("<f8"))
    uncertainties = np.empty(shape, dtype=np.dtype("<f8"))
    for candidate_index, candidate in enumerate(candidates):
        for tau_index, state in enumerate(candidate.tau_states):
            by_observation = {item.observation_id: item for item in state.predictions}
            if set(by_observation) != set(observation_ids):
                raise CataloguePredictionArrayViewError(
                    "public prediction row inventory differs from support"
                )
            predictions[candidate_index, tau_index] = [
                by_observation[item].predicted_cfo_hz for item in observation_ids
            ]
            uncertainties[candidate_index, tau_index] = [
                by_observation[item].standard_uncertainty_hz for item in observation_ids
            ]
    predictions.setflags(write=False)
    uncertainties.setflags(write=False)
    candidate_authority = tuple(
        CatalogueArrayCandidateAuthority(
            catalog_number=item.catalog_number,
            object_name=item.object_name,
            selected_element_digest=item.selected_element_digest,
            element_epoch_utc_ns=item.element_epoch_utc_ns,
            element_age_s_at_reference=item.element_age_s_at_reference,
            eligible_episode_ids=item.eligible_episode_ids,
        )
        for item in candidates
    )
    tau_authority = tuple(
        CatalogueArrayTauAuthority(
            tau_s=item.tau_s,
            log_prior_weight=item.log_prior_weight,
        )
        for item in candidates[0].tau_states
    )
    prediction_authority = catalogue_prediction_inventory_authority_digest(
        field_delta_s=field_delta_s,
        public_bank_content_digest=validated.content_digest,
        candidate_authority=candidate_authority,
        tau_authority=tau_authority,
        observation_ids=observation_ids,
        predicted_cfo_hz=cast(NDArray[np.float64], predictions),
        standard_uncertainty_hz=cast(NDArray[np.float64], uncertainties),
    )
    return CataloguePredictionArrayBankView(
        field_delta_s=field_delta_s,
        support=validated.support,
        tle_snapshot=validated.tle_snapshot,
        observer_site=validated.observer_site,
        nominal_rf_hz=validated.nominal_rf_hz,
        prediction_reference_utc_ns=validated.prediction_reference_utc_ns,
        selection_protocol_digest=validated.selection_protocol_digest,
        selection_policy_digest=validated.selection_policy_digest,
        tle_membership_authority_digest=validated.tle_membership_authority_digest,
        verified_tle_members=validated.verified_tle_members,
        candidate_universe_digest=validated.candidate_universe_digest,
        tau_search_policy=validated.tau_search_policy,
        propagation_model=validated.propagation_model,
        candidate_authority=candidate_authority,
        tau_authority=tau_authority,
        observation_ids=observation_ids,
        predicted_cfo_hz=cast(NDArray[np.float64], predictions),
        standard_uncertainty_hz=cast(NDArray[np.float64], uncertainties),
        public_bank_content_digest=validated.content_digest,
        prediction_inventory_authority_digest=prediction_authority,
    )


def verify_catalogue_prediction_array_bank_view(
    view: CataloguePredictionArrayBankView,
) -> CataloguePredictionArrayBankView:
    """Reconstruct a borrowed view so in-memory field poisoning fails closed."""

    try:
        return replace(view)
    except (AttributeError, TypeError, ValueError) as error:
        raise CataloguePredictionArrayViewError("prediction array view is invalid") from error


def catalogue_prediction_inventory_authority_digest(
    *,
    field_delta_s: CatalogueFieldDelta,
    public_bank_content_digest: Sha256Digest,
    candidate_authority: tuple[CatalogueArrayCandidateAuthority, ...],
    tau_authority: tuple[CatalogueArrayTauAuthority, ...],
    observation_ids: tuple[Sha256Digest, ...],
    predicted_cfo_hz: NDArray[np.float64],
    standard_uncertainty_hz: NDArray[np.float64],
) -> Sha256Digest:
    """Hash the logical prediction inventory without paths or array containers.

    Axis metadata is encoded as canonical JSON.  The two cubes are then hashed
    in declared order as exact little-endian float64 bytes in canonical C axis
    order.  One candidate plane is visited at a time, keeping peak temporary
    memory bounded by ``tau_count * observation_count * 8`` bytes even when a
    borrowed array is strided.
    """

    shape = (
        len(candidate_authority),
        len(tau_authority),
        len(observation_ids),
    )
    cubes = (
        ("predicted_cfo_hz", predicted_cfo_hz),
        ("standard_uncertainty_hz", standard_uncertainty_hz),
    )
    if not _is_digest(public_bank_content_digest):
        raise CataloguePredictionArrayViewError(
            "prediction inventory requires a digest-bound public bank"
        )
    for _label, cube in cubes:
        if not isinstance(cube, np.ndarray) or cube.shape != shape or cube.dtype != np.dtype("<f8"):
            raise CataloguePredictionArrayViewError(
                "prediction inventory cube layout is not canonical"
            )
    header = canonical_json_bytes(
        {
            "schema": "org.leo.analysis.catalogue-prediction-logical-inventory/v1",
            "field_delta_s": field_delta_s,
            "public_bank_content_digest": public_bank_content_digest,
            "candidate_axis": tuple(asdict(item) for item in candidate_authority),
            "tau_axis": tuple(asdict(item) for item in tau_authority),
            "observation_axis": observation_ids,
            "shape": shape,
            "cube_encoding": {
                "axis_order": ("candidate", "tau", "observation"),
                "cube_order": tuple(label for label, _cube in cubes),
                "dtype": "<f8",
                "storage_order": "C",
            },
        }
    )
    digest = hashlib.sha256()
    digest.update(b"org.leo.analysis.catalogue-prediction-logical-inventory/v1\x00")
    digest.update(len(header).to_bytes(8, byteorder="big", signed=False))
    digest.update(header)
    for label, cube in cubes:
        label_bytes = label.encode("ascii")
        digest.update(len(label_bytes).to_bytes(2, byteorder="big", signed=False))
        digest.update(label_bytes)
        digest.update(cube.nbytes.to_bytes(8, byteorder="big", signed=False))
        for candidate_index in range(shape[0]):
            candidate_plane = np.ascontiguousarray(
                cube[candidate_index],
                dtype=np.dtype("<f8"),
            )
            digest.update(memoryview(candidate_plane).cast("B"))
    return f"sha256:{digest.hexdigest()}"


def _validate_finite_cubes(
    predictions: NDArray[np.float64],
    uncertainties: NDArray[np.float64],
) -> None:
    for start in range(0, predictions.shape[0], 8):
        stop = min(start + 8, predictions.shape[0])
        prediction_chunk = predictions[start:stop]
        uncertainty_chunk = uncertainties[start:stop]
        if not np.isfinite(prediction_chunk).all() or not np.isfinite(uncertainty_chunk).all():
            raise CataloguePredictionArrayViewError(
                "array-view prediction cubes contain non-finite values"
            )
        if np.any(uncertainty_chunk < 0.0):
            raise CataloguePredictionArrayViewError("array-view prediction uncertainty is negative")


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None
