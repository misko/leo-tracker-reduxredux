"""Compact, read-only storage for a complete catalogue prediction bank.

The public :class:`CataloguePredictionBankV1` wire contract is deliberately
unchanged.  This module is an execution-only representation for banks whose
candidate/tau/observation prediction inventory is too large to retain as
millions of Python/Pydantic objects.  Authority and candidate metadata remain
ordinary immutable contracts; the two dense float64 prediction cubes live in
digest-bound ``.npy`` files and are opened with read-only memory mapping.

``content_digest`` is always the exact digest of the corresponding public V1
bank, not a digest of this compact wrapper.  ``compact_content_digest`` binds
the wrapper metadata and array-file hashes separately.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray

from leo.analysis.catalogue_prediction_array_view import (
    CatalogueArrayCandidateAuthority,
    CatalogueArrayTauAuthority,
    CataloguePredictionArrayBankView,
    CataloguePredictionArrayViewError,
    catalogue_prediction_inventory_authority_digest,
)
from leo.contracts.catalogue_association import (
    CandidateObservationPredictionV1,
    CandidateTauStateV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1

type CompactTauSearchPolicy = Literal[
    "fixed-tau-zero-v1",
    "bounded-profile-minus5-plus5-v1",
]


class CompactCataloguePredictionBankError(ValueError):
    """Compact metadata, storage, or public-bank lineage failed closed."""


@dataclass(frozen=True, slots=True)
class CompactTauStateMetadata:
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
            raise CompactCataloguePredictionBankError("compact tau metadata is invalid")


@dataclass(frozen=True, slots=True)
class CompactCandidateMetadata:
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
            raise CompactCataloguePredictionBankError("compact candidate metadata is invalid")


@dataclass(frozen=True, slots=True)
class CompactCandidatePredictionView:
    """A borrowed read-only candidate slice; valid while its iterator is open."""

    candidate_index: int
    metadata: CompactCandidateMetadata
    tau_states: tuple[CompactTauStateMetadata, ...]
    observation_ids: tuple[Sha256Digest, ...]
    predicted_cfo_hz: NDArray[np.float64]
    standard_uncertainty_hz: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class CompactCataloguePredictionBank:
    """Digest-closed execution handle for one complete public V1 bank."""

    field_delta_s: Literal[-500, 0, 500]
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
    tau_search_policy: CompactTauSearchPolicy
    propagation_model: str
    candidate_metadata: tuple[CompactCandidateMetadata, ...]
    tau_states: tuple[CompactTauStateMetadata, ...]
    observation_ids: tuple[Sha256Digest, ...]
    prediction_shape: tuple[int, int, int]
    source_candidate_count: int
    returned_candidate_count: int
    predicted_cfo_array_path: str
    standard_uncertainty_array_path: str
    predicted_cfo_array_sha256: Sha256Digest
    standard_uncertainty_array_sha256: Sha256Digest
    content_digest: Sha256Digest
    compact_content_digest: Sha256Digest = field(init=False)
    algorithm_version: Literal["compact-catalogue-prediction-bank-v1"] = field(
        default="compact-catalogue-prediction-bank-v1", init=False
    )
    public_contract_algorithm_version: Literal["support-integrated-tle-bank-v1"] = field(
        default="support-integrated-tle-bank-v1", init=False
    )
    public_contract_schema_version: Literal[1] = field(default=1, init=False)
    public_candidate_schema_version: Literal[1] = field(default=1, init=False)
    public_tau_state_schema_version: Literal[1] = field(default=1, init=False)
    public_prediction_schema_version: Literal[1] = field(default=1, init=False)
    population_conditioning: Literal["frozen-response-free-universe-v1"] = field(
        default="frozen-response-free-universe-v1", init=False
    )
    prediction_error_model: Literal["independent-diagonal-conditional-on-candidate-v1"] = field(
        default="independent-diagonal-conditional-on-candidate-v1", init=False
    )
    response_accessed: Literal[False] = field(default=False, init=False)
    truncated_candidate_count: Literal[0] = field(default=0, init=False)
    complete_tau_inventory: Literal[True] = field(default=True, init=False)
    arrays_read_only: Literal[True] = field(default=True, init=False)
    public_contract_materialized: Literal[False] = field(default=False, init=False)

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
            raise CompactCataloguePredictionBankError(
                "compact bank authority contracts are invalid"
            ) from error
        object.__setattr__(self, "support", support)
        object.__setattr__(self, "tle_snapshot", snapshot)
        object.__setattr__(self, "observer_site", site)
        object.__setattr__(self, "verified_tle_members", members)
        if self.field_delta_s not in (-500, 0, 500):
            raise CompactCataloguePredictionBankError("compact field delta is invalid")
        if (
            isinstance(self.nominal_rf_hz, bool)
            or not math.isfinite(self.nominal_rf_hz)
            or self.nominal_rf_hz <= 0.0
            or not self.propagation_model
        ):
            raise CompactCataloguePredictionBankError("compact RF/model metadata is invalid")
        expected_reference_utc_ns = min(
            item.support_center_utc_ns for item in self.support.observations
        )
        if (
            isinstance(self.prediction_reference_utc_ns, bool)
            or not isinstance(self.prediction_reference_utc_ns, int)
            or self.prediction_reference_utc_ns != expected_reference_utc_ns
        ):
            raise CompactCataloguePredictionBankError(
                "compact prediction reference differs from response-free support"
            )
        for value in (
            self.selection_protocol_digest,
            self.selection_policy_digest,
            self.tle_membership_authority_digest,
            self.candidate_universe_digest,
            self.predicted_cfo_array_sha256,
            self.standard_uncertainty_array_sha256,
            self.content_digest,
        ):
            if not _is_digest(value):
                raise CompactCataloguePredictionBankError(
                    "compact bank authority must be digest-bound"
                )
        numbers = tuple(item.catalog_number for item in self.candidate_metadata)
        if numbers != tuple(sorted(set(numbers))):
            raise CompactCataloguePredictionBankError(
                "compact candidate inventory must be nonempty, unique, and ordered"
            )
        member_keys = tuple(
            (item.catalog_number, item.selected_element_digest, item.element_epoch_utc_ns)
            for item in members
        )
        candidate_keys = tuple(
            (item.catalog_number, item.selected_element_digest, item.element_epoch_utc_ns)
            for item in self.candidate_metadata
        )
        if member_keys != candidate_keys:
            raise CompactCataloguePredictionBankError(
                "compact verified membership differs from candidates"
            )
        tau_values = tuple(item.tau_s for item in self.tau_states)
        if tau_values != tuple(sorted(set(tau_values))) or 0.0 not in tau_values:
            raise CompactCataloguePredictionBankError(
                "compact tau inventory must be unique, ordered, and contain zero"
            )
        if self.tau_search_policy == "fixed-tau-zero-v1" and tau_values != (0.0,):
            raise CompactCataloguePredictionBankError(
                "fixed compact tau policy requires exact zero"
            )
        if self.tau_search_policy == "bounded-profile-minus5-plus5-v1" and not (
            tau_values and tau_values[0] == -5.0 and tau_values[-1] == 5.0
        ):
            raise CompactCataloguePredictionBankError(
                "bounded compact tau policy must close [-5,+5]"
            )
        if (
            not self.observation_ids
            or self.observation_ids != tuple(sorted(set(self.observation_ids)))
            or set(self.observation_ids)
            != {item.observation_id for item in self.support.observations}
        ):
            raise CompactCataloguePredictionBankError(
                "compact observation inventory differs from support"
            )
        expected_shape = (
            len(self.candidate_metadata),
            len(self.tau_states),
            len(self.observation_ids),
        )
        if (
            not self.candidate_metadata
            or self.prediction_shape != expected_shape
            or isinstance(self.source_candidate_count, bool)
            or not isinstance(self.source_candidate_count, int)
            or isinstance(self.returned_candidate_count, bool)
            or not isinstance(self.returned_candidate_count, int)
            or self.source_candidate_count != len(self.candidate_metadata)
            or self.returned_candidate_count != len(self.candidate_metadata)
        ):
            raise CompactCataloguePredictionBankError("compact prediction shape is invalid")
        for path_value in (
            self.predicted_cfo_array_path,
            self.standard_uncertainty_array_path,
        ):
            path = Path(path_value)
            if not path.is_absolute() or not path.is_file():
                raise CompactCataloguePredictionBankError(
                    "compact prediction array path is not an existing absolute file"
                )
        object.__setattr__(
            self,
            "compact_content_digest",
            canonical_digest(_compact_payload(self)),
        )


def verify_compact_catalogue_prediction_bank(
    bank: CompactCataloguePredictionBank,
) -> None:
    """Revalidate wrapper closure, array headers, finiteness, and file hashes."""

    _verify_compact_closure_and_file_hashes(bank)
    with open_compact_prediction_arrays(bank, verify_hashes=False) as (
        predictions,
        uncertainties,
    ):
        if not np.isfinite(predictions).all() or not np.isfinite(uncertainties).all():
            raise CompactCataloguePredictionBankError(
                "compact prediction arrays contain non-finite values"
            )
        if np.any(uncertainties < 0.0):
            raise CompactCataloguePredictionBankError("compact prediction uncertainty is negative")


def _verify_compact_closure_and_file_hashes(
    bank: CompactCataloguePredictionBank,
) -> None:
    if bank.compact_content_digest != canonical_digest(_compact_payload(bank)):
        raise CompactCataloguePredictionBankError("compact bank digest does not close")
    prediction_path = Path(bank.predicted_cfo_array_path)
    uncertainty_path = Path(bank.standard_uncertainty_array_path)
    if _file_sha256(prediction_path) != bank.predicted_cfo_array_sha256 or (
        _file_sha256(uncertainty_path) != bank.standard_uncertainty_array_sha256
    ):
        raise CompactCataloguePredictionBankError("compact prediction array hash drifted")


@contextmanager
def open_compact_prediction_arrays(
    bank: CompactCataloguePredictionBank,
    *,
    verify_hashes: bool = True,
) -> Iterator[tuple[NDArray[np.float64], NDArray[np.float64]]]:
    """Open both complete cubes read-only without loading them into RAM."""

    if verify_hashes:
        prediction_path = Path(bank.predicted_cfo_array_path)
        uncertainty_path = Path(bank.standard_uncertainty_array_path)
        if _file_sha256(prediction_path) != bank.predicted_cfo_array_sha256 or (
            _file_sha256(uncertainty_path) != bank.standard_uncertainty_array_sha256
        ):
            raise CompactCataloguePredictionBankError("compact prediction array hash drifted")
    try:
        predictions = cast(
            NDArray[np.float64],
            np.load(bank.predicted_cfo_array_path, mmap_mode="r", allow_pickle=False),
        )
        uncertainties = cast(
            NDArray[np.float64],
            np.load(bank.standard_uncertainty_array_path, mmap_mode="r", allow_pickle=False),
        )
    except (OSError, ValueError) as error:
        raise CompactCataloguePredictionBankError(
            "compact prediction arrays are unreadable"
        ) from error
    if (
        predictions.shape != bank.prediction_shape
        or uncertainties.shape != bank.prediction_shape
        or predictions.dtype != np.dtype("<f8")
        or uncertainties.dtype != np.dtype("<f8")
    ):
        raise CompactCataloguePredictionBankError(
            "compact prediction array header differs from metadata"
        )
    predictions.setflags(write=False)
    uncertainties.setflags(write=False)
    try:
        yield predictions, uncertainties
    finally:
        _close_memmap(predictions)
        _close_memmap(uncertainties)


@contextmanager
def open_compact_catalogue_prediction_array_bank_view(
    bank: CompactCataloguePredictionBank,
) -> Iterator[CataloguePredictionArrayBankView]:
    """Authenticate compact storage and borrow it through the pure array port.

    Wrapper closure and both complete file hashes are checked before the view
    exists.  The pure view then validates authority, shape, read-only state,
    finiteness, and uncertainty sign without importing paths or storage logic.
    Its mmap-backed arrays are borrowed only until this context exits.
    """

    _verify_compact_closure_and_file_hashes(bank)
    with open_compact_prediction_arrays(bank, verify_hashes=False) as (
        predictions,
        uncertainties,
    ):
        try:
            candidate_authority = tuple(
                CatalogueArrayCandidateAuthority(
                    catalog_number=item.catalog_number,
                    object_name=item.object_name,
                    selected_element_digest=item.selected_element_digest,
                    element_epoch_utc_ns=item.element_epoch_utc_ns,
                    element_age_s_at_reference=item.element_age_s_at_reference,
                    eligible_episode_ids=item.eligible_episode_ids,
                )
                for item in bank.candidate_metadata
            )
            tau_authority = tuple(
                CatalogueArrayTauAuthority(
                    tau_s=item.tau_s,
                    log_prior_weight=item.log_prior_weight,
                )
                for item in bank.tau_states
            )
            prediction_authority = catalogue_prediction_inventory_authority_digest(
                field_delta_s=bank.field_delta_s,
                public_bank_content_digest=bank.content_digest,
                candidate_authority=candidate_authority,
                tau_authority=tau_authority,
                observation_ids=bank.observation_ids,
                predicted_cfo_hz=predictions,
                standard_uncertainty_hz=uncertainties,
            )
            view = CataloguePredictionArrayBankView(
                field_delta_s=bank.field_delta_s,
                support=bank.support,
                tle_snapshot=bank.tle_snapshot,
                observer_site=bank.observer_site,
                nominal_rf_hz=bank.nominal_rf_hz,
                prediction_reference_utc_ns=bank.prediction_reference_utc_ns,
                selection_protocol_digest=bank.selection_protocol_digest,
                selection_policy_digest=bank.selection_policy_digest,
                tle_membership_authority_digest=bank.tle_membership_authority_digest,
                verified_tle_members=bank.verified_tle_members,
                candidate_universe_digest=bank.candidate_universe_digest,
                tau_search_policy=bank.tau_search_policy,
                propagation_model=bank.propagation_model,
                candidate_authority=candidate_authority,
                tau_authority=tau_authority,
                observation_ids=bank.observation_ids,
                predicted_cfo_hz=predictions,
                standard_uncertainty_hz=uncertainties,
                public_bank_content_digest=bank.content_digest,
                prediction_inventory_authority_digest=prediction_authority,
            )
        except (AttributeError, TypeError, ValueError, CataloguePredictionArrayViewError) as error:
            raise CompactCataloguePredictionBankError(
                "compact bank cannot enter the pure prediction-array port"
            ) from error
        yield view


def iter_compact_candidate_views(
    bank: CompactCataloguePredictionBank,
    *,
    verify_hashes: bool = True,
) -> Iterator[CompactCandidatePredictionView]:
    """Yield one borrowed candidate cube at a time from a single mmap opening."""

    with open_compact_prediction_arrays(bank, verify_hashes=verify_hashes) as (
        predictions,
        uncertainties,
    ):
        for index, metadata in enumerate(bank.candidate_metadata):
            yield CompactCandidatePredictionView(
                candidate_index=index,
                metadata=metadata,
                tau_states=bank.tau_states,
                observation_ids=bank.observation_ids,
                predicted_cfo_hz=predictions[index],
                standard_uncertainty_hz=uncertainties[index],
            )


def materialize_compact_candidate(
    bank: CompactCataloguePredictionBank,
    candidate_index: int,
    *,
    verify_hashes: bool = True,
) -> CatalogueCandidatePredictionV1:
    """Materialize one public candidate, never the complete public bank."""

    if (
        isinstance(candidate_index, bool)
        or not isinstance(candidate_index, int)
        or not 0 <= candidate_index < len(bank.candidate_metadata)
    ):
        raise CompactCataloguePredictionBankError("compact candidate index is out of range")
    with open_compact_prediction_arrays(bank, verify_hashes=verify_hashes) as (
        predictions,
        uncertainties,
    ):
        return _materialize_candidate(
            bank.candidate_metadata[candidate_index],
            bank.tau_states,
            bank.observation_ids,
            predictions[candidate_index],
            uncertainties[candidate_index],
        )


def _materialize_candidate(
    metadata: CompactCandidateMetadata,
    tau_states: tuple[CompactTauStateMetadata, ...],
    observation_ids: tuple[str, ...],
    predictions: NDArray[np.float64],
    uncertainties: NDArray[np.float64],
) -> CatalogueCandidatePredictionV1:
    states = tuple(
        CandidateTauStateV1(
            tau_s=tau.tau_s,
            log_prior_weight=tau.log_prior_weight,
            predictions=tuple(
                CandidateObservationPredictionV1(
                    observation_id=observation_id,
                    predicted_cfo_hz=float(predictions[tau_index, observation_index]),
                    standard_uncertainty_hz=float(uncertainties[tau_index, observation_index]),
                )
                for observation_index, observation_id in enumerate(observation_ids)
            ),
        )
        for tau_index, tau in enumerate(tau_states)
    )
    return CatalogueCandidatePredictionV1(
        catalog_number=metadata.catalog_number,
        object_name=metadata.object_name,
        selected_element_digest=metadata.selected_element_digest,
        element_epoch_utc_ns=metadata.element_epoch_utc_ns,
        element_age_s_at_reference=metadata.element_age_s_at_reference,
        eligible_episode_ids=metadata.eligible_episode_ids,
        tau_states=states,
    )


def compact_catalogue_prediction_bank_payload(
    bank: CompactCataloguePredictionBank,
) -> dict[str, object]:
    """Return a JSON-compatible wrapper after checking digest closure."""

    payload = _compact_payload(bank)
    if bank.compact_content_digest != canonical_digest(payload):
        raise CompactCataloguePredictionBankError("compact bank digest does not close")
    return {**payload, "compact_content_digest": bank.compact_content_digest}


def file_sha256(path: Path) -> Sha256Digest:
    """Public bounded-memory file hash used by the compact writer."""

    return _file_sha256(path)


def _compact_payload(bank: CompactCataloguePredictionBank) -> dict[str, object]:
    return {
        "field_delta_s": bank.field_delta_s,
        "support": bank.support.model_dump(mode="json"),
        "tle_snapshot": bank.tle_snapshot.model_dump(mode="json"),
        "observer_site": bank.observer_site.model_dump(mode="json"),
        "nominal_rf_hz": bank.nominal_rf_hz,
        "prediction_reference_utc_ns": bank.prediction_reference_utc_ns,
        "selection_protocol_digest": bank.selection_protocol_digest,
        "selection_policy_digest": bank.selection_policy_digest,
        "tle_membership_authority_digest": bank.tle_membership_authority_digest,
        "verified_tle_members": tuple(
            item.model_dump(mode="json") for item in bank.verified_tle_members
        ),
        "candidate_universe_digest": bank.candidate_universe_digest,
        "tau_search_policy": bank.tau_search_policy,
        "propagation_model": bank.propagation_model,
        "candidate_metadata": tuple(asdict(item) for item in bank.candidate_metadata),
        "tau_states": tuple(asdict(item) for item in bank.tau_states),
        "observation_ids": bank.observation_ids,
        "prediction_shape": bank.prediction_shape,
        "source_candidate_count": bank.source_candidate_count,
        "returned_candidate_count": bank.returned_candidate_count,
        "predicted_cfo_array_sha256": bank.predicted_cfo_array_sha256,
        "standard_uncertainty_array_sha256": (bank.standard_uncertainty_array_sha256),
        "content_digest": bank.content_digest,
        "algorithm_version": bank.algorithm_version,
        "public_contract_algorithm_version": bank.public_contract_algorithm_version,
        "public_contract_schema_version": bank.public_contract_schema_version,
        "public_candidate_schema_version": bank.public_candidate_schema_version,
        "public_tau_state_schema_version": bank.public_tau_state_schema_version,
        "public_prediction_schema_version": bank.public_prediction_schema_version,
        "population_conditioning": bank.population_conditioning,
        "prediction_error_model": bank.prediction_error_model,
        "response_accessed": bank.response_accessed,
        "truncated_candidate_count": bank.truncated_candidate_count,
        "complete_tau_inventory": bank.complete_tau_inventory,
        "arrays_read_only": bank.arrays_read_only,
        "public_contract_materialized": bank.public_contract_materialized,
    }


def _file_sha256(path: Path) -> Sha256Digest:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1_048_576):
                digest.update(chunk)
    except OSError as error:
        raise CompactCataloguePredictionBankError(
            "compact prediction array cannot be hashed"
        ) from error
    return f"sha256:{digest.hexdigest()}"


def _close_memmap(value: NDArray[np.float64]) -> None:
    mmap = getattr(value, "_mmap", None)
    if mmap is not None:
        mmap.close()


def _is_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    hexadecimal = value.removeprefix("sha256:")
    return len(hexadecimal) == 64 and all(
        character in "0123456789abcdef" for character in hexadecimal
    )


__all__ = [
    "CompactCandidateMetadata",
    "CompactCandidatePredictionView",
    "CompactCataloguePredictionBank",
    "CompactCataloguePredictionBankError",
    "CompactTauStateMetadata",
    "compact_catalogue_prediction_bank_payload",
    "file_sha256",
    "iter_compact_candidate_views",
    "materialize_compact_candidate",
    "open_compact_catalogue_prediction_array_bank_view",
    "open_compact_prediction_arrays",
    "verify_compact_catalogue_prediction_bank",
]
