"""Rebuild sealed long-arc prediction banks without reading CFO response.

The opened long-arc result archives persisted complete response-free candidate
inventories and prediction-bank digests, but intentionally did not persist the
per-observation predictions.  This module recovers that narrow input by reading
only the leading ``field_banks`` receipt array, authenticating the original TLE
bytes, and regenerating a bank whose complete content digest must match the
sealed receipt.

The public rebuild port accepts prediction support, never a physical response
graph.  It therefore cannot inspect measured CFO while reconstructing the
catalogue geometry used by an observability atlas.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import zstandard as zstd

from leo.analysis.catalogue_prediction import (
    ExactTauPolicy,
    FrozenCatalogueCandidate,
    FrozenResponseFreeCandidateUniverse,
    KnownSiteRfAuthority,
    Sgp4SupportPredictionPolicy,
    SnapshotPayload,
    build_sgp4_catalogue_prediction_bank,
)
from leo.analysis.research.compact_catalogue_prediction_bank import (
    CompactCandidateMetadata,
    CompactCataloguePredictionBank,
    CompactTauStateMetadata,
    file_sha256,
)
from leo.contracts.catalogue_association import (
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import (
    Sha256Digest,
    canonical_digest,
    canonical_json_bytes,
    sha256_digest,
)
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1

_SHA256_PREFIX = "sha256:"
_FIELD_DELTAS = (-500, 0, 500)


class LongArcObservabilityRebuildError(ValueError):
    """A sealed receipt or regenerated response-free bank failed closed."""


@dataclass(frozen=True, slots=True)
class CompactFieldBankRebuildPolicy:
    """Explicit RAM, storage, and inventory bounds for compact rebuilding.

    The upstream SGP4 policy remains the authority for propagated-state work.
    These additional limits prevent chunking from silently turning an
    unbounded public-bank materialization into unbounded disk or metadata work.
    """

    candidate_chunk_size: int = 8
    maximum_candidate_count: int = 1_024
    maximum_tau_count: int = 401
    maximum_observation_count: int = 2_048
    maximum_prediction_cells_per_field: int = 100_000_000
    maximum_array_storage_bytes_per_field: int = 2_000_000_000
    maximum_array_storage_bytes_total: int = 6_000_000_000

    def __post_init__(self) -> None:
        integer_limits = (
            (self.candidate_chunk_size, "candidate chunk size"),
            (self.maximum_candidate_count, "candidate-count cap"),
            (self.maximum_tau_count, "tau-count cap"),
            (self.maximum_observation_count, "observation-count cap"),
            (
                self.maximum_prediction_cells_per_field,
                "prediction-cell cap",
            ),
            (
                self.maximum_array_storage_bytes_per_field,
                "per-field storage cap",
            ),
            (self.maximum_array_storage_bytes_total, "total storage cap"),
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value, _ in integer_limits
        ):
            failed = next(
                label
                for value, label in integer_limits
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0
            )
            raise LongArcObservabilityRebuildError(f"{failed} must be a positive integer")
        if self.candidate_chunk_size > self.maximum_candidate_count:
            raise LongArcObservabilityRebuildError(
                "candidate chunk size exceeds the candidate-count cap"
            )


@dataclass(frozen=True, slots=True)
class SealedFieldCandidateReceipt:
    catalog_number: int
    object_name: str
    selected_element_digest: Sha256Digest
    element_epoch_utc_ns: int
    element_age_s_at_reference: float


@dataclass(frozen=True, slots=True)
class SealedFieldBankReceipt:
    field_delta_s: int
    population_receipt_digest: Sha256Digest
    selection_policy_digest: Sha256Digest
    candidate_universe_digest: Sha256Digest
    prediction_bank_digest: Sha256Digest
    candidate_count: int
    candidates: tuple[SealedFieldCandidateReceipt, ...]
    propagation_complete_for_association: Literal[True]


@dataclass(frozen=True, slots=True)
class SealedResponseFreeBankInventory:
    archive_path: str
    archive_sha256: Sha256Digest
    field_banks: tuple[SealedFieldBankReceipt, ...]
    content_digest: Sha256Digest
    response_section_parsed: Literal[False] = field(default=False, init=False)
    candidate_ranking_performed: Literal[False] = field(default=False, init=False)
    algorithm_version: Literal["sealed-leading-field-bank-inventory-v1"] = field(
        default="sealed-leading-field-bank-inventory-v1", init=False
    )


def load_sealed_response_free_bank_inventory(
    archive_path: Path,
    *,
    expected_archive_sha256: Sha256Digest,
    maximum_decompressed_prefix_bytes: int = 16_000_000,
) -> SealedResponseFreeBankInventory:
    """Authenticate an archive and parse only its leading field-bank receipts."""

    if not _is_digest(expected_archive_sha256):
        raise LongArcObservabilityRebuildError("expected archive SHA-256 is invalid")
    if maximum_decompressed_prefix_bytes < 1_000:
        raise LongArcObservabilityRebuildError("decompressed-prefix cap is too small")
    path = archive_path.resolve()
    try:
        compressed = path.read_bytes()
    except OSError as error:
        raise LongArcObservabilityRebuildError("sealed result archive is unreadable") from error
    actual_sha256 = sha256_digest(compressed)
    if actual_sha256 != expected_archive_sha256:
        raise LongArcObservabilityRebuildError("sealed result archive SHA-256 drifted")
    field_payload = _read_leading_field_bank_array(
        compressed,
        maximum_decompressed_prefix_bytes=maximum_decompressed_prefix_bytes,
    )
    receipts = _validate_field_bank_payload(field_payload)
    payload = {
        "algorithm_version": "sealed-leading-field-bank-inventory-v1",
        "archive_sha256": actual_sha256,
        "field_banks": [_receipt_payload(item) for item in receipts],
        "response_section_parsed": False,
        "candidate_ranking_performed": False,
    }
    return SealedResponseFreeBankInventory(
        archive_path=path.as_posix(),
        archive_sha256=actual_sha256,
        field_banks=receipts,
        content_digest=canonical_digest(payload),
    )


def rebuild_digest_identical_field_banks(
    support: CataloguePredictionSupportV1,
    snapshot_payload: SnapshotPayload,
    *,
    tle_snapshot: TleSnapshotRefV1,
    observer_site: ObserverSiteV1,
    nominal_rf_hz: float,
    selection_protocol_digest: Sha256Digest,
    tau_policy: ExactTauPolicy,
    prediction_policy: Sgp4SupportPredictionPolicy,
    inventory: SealedResponseFreeBankInventory,
) -> tuple[CataloguePredictionBankV1, ...]:
    """Rebuild all three exact banks and require their sealed content digests."""

    try:
        support = CataloguePredictionSupportV1.model_validate(support.model_dump(mode="json"))
        tle_snapshot = TleSnapshotRefV1.model_validate(tle_snapshot.model_dump(mode="json"))
        observer_site = ObserverSiteV1.model_validate(observer_site.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise LongArcObservabilityRebuildError("rebuild contracts are invalid") from error
    if not support.response_fields_excluded:
        raise LongArcObservabilityRebuildError("rebuild support must exclude response fields")
    if not _is_digest(selection_protocol_digest):
        raise LongArcObservabilityRebuildError("selection protocol digest is invalid")
    raw_bytes = _snapshot_bytes(snapshot_payload)
    if sha256_digest(raw_bytes) != tle_snapshot.digest:
        raise LongArcObservabilityRebuildError("TLE snapshot bytes failed authentication")
    episode_ids = support.episode_ids
    if len(episode_ids) != 1:
        raise LongArcObservabilityRebuildError(
            "sealed long-arc recovery requires exactly one response-free episode"
        )

    banks: list[CataloguePredictionBankV1] = []
    for receipt in inventory.field_banks:
        members = tuple(
            CatalogueVerifiedTleMemberV1(
                catalog_number=item.catalog_number,
                selected_element_digest=item.selected_element_digest,
                element_epoch_utc_ns=item.element_epoch_utc_ns,
            )
            for item in receipt.candidates
        )
        membership_digest = canonical_digest(
            {
                "algorithm_version": "response-free-tle-membership-authority-v1",
                "snapshot_digest": tle_snapshot.digest,
                "members": [item.model_dump(mode="json") for item in members],
            }
        )
        universe = FrozenResponseFreeCandidateUniverse(
            candidates=tuple(
                FrozenCatalogueCandidate(
                    catalog_number=item.catalog_number,
                    eligible_episode_ids=episode_ids,
                )
                for item in receipt.candidates
            ),
            selection_protocol_digest=selection_protocol_digest,
            selection_policy_digest=receipt.selection_policy_digest,
            tle_membership_authority_digest=membership_digest,
            catalogue_field_delta_s=receipt.field_delta_s,
        )
        bank = build_sgp4_catalogue_prediction_bank(
            support,
            raw_bytes,
            tle_snapshot=tle_snapshot,
            site_rf_authority=KnownSiteRfAuthority.create(
                observer_site=observer_site,
                nominal_rf_hz=nominal_rf_hz,
            ),
            candidate_universe=universe,
            verified_tle_members=members,
            tau_policy=tau_policy,
            prediction_policy=prediction_policy,
            catalogue_field_delta_s=receipt.field_delta_s,
        )
        if bank.returned_candidate_count != receipt.candidate_count:
            raise LongArcObservabilityRebuildError(
                f"field {receipt.field_delta_s:+d} candidate count drifted"
            )
        if bank.candidate_universe_digest != receipt.candidate_universe_digest:
            raise LongArcObservabilityRebuildError(
                f"field {receipt.field_delta_s:+d} candidate-universe digest drifted"
            )
        if bank.content_digest != receipt.prediction_bank_digest:
            raise LongArcObservabilityRebuildError(
                f"field {receipt.field_delta_s:+d} prediction-bank digest drifted"
            )
        banks.append(bank)
    return tuple(banks)


def iter_rebuilt_digest_identical_compact_field_banks(
    support: CataloguePredictionSupportV1,
    snapshot_payload: SnapshotPayload,
    *,
    tle_snapshot: TleSnapshotRefV1,
    observer_site: ObserverSiteV1,
    nominal_rf_hz: float,
    selection_protocol_digest: Sha256Digest,
    tau_policy: ExactTauPolicy,
    prediction_policy: Sgp4SupportPredictionPolicy,
    inventory: SealedResponseFreeBankInventory,
    storage_directory: Path,
    compact_policy: CompactFieldBankRebuildPolicy | None = None,
) -> Iterator[CompactCataloguePredictionBank]:
    """Rebuild complete banks one field at a time into read-only mmap cubes.

    Candidate chunks pass through the same public SGP4 adapter as the legacy
    rebuild.  Candidate JSON is fed, in canonical order, into an incremental
    hash of the *full* public V1 bank.  The yielded ``content_digest`` must
    therefore equal the sealed public-bank digest even though the full bank is
    never retained or constructed.

    Calling this function is lazy: authentication and propagation start on the
    first iteration.  Each yield occurs only after one complete field has been
    propagated, its public digest has closed, and both dense arrays have been
    committed without overwriting an existing file.
    """

    try:
        support = CataloguePredictionSupportV1.model_validate(support.model_dump(mode="json"))
        tle_snapshot = TleSnapshotRefV1.model_validate(tle_snapshot.model_dump(mode="json"))
        observer_site = ObserverSiteV1.model_validate(observer_site.model_dump(mode="json"))
        tau_policy = ExactTauPolicy(policy=tau_policy.policy, points=tau_policy.points)
        prediction_policy = Sgp4SupportPredictionPolicy(
            integration_sample_count=prediction_policy.integration_sample_count,
            standard_uncertainty_floor_hz=(prediction_policy.standard_uncertainty_floor_hz),
            element_age_growth_hz_per_day=(prediction_policy.element_age_growth_hz_per_day),
            fit_residual_multiplier=prediction_policy.fit_residual_multiplier,
            maximum_propagated_states=prediction_policy.maximum_propagated_states,
        )
        policy_source = (
            CompactFieldBankRebuildPolicy() if compact_policy is None else compact_policy
        )
        compact_policy = CompactFieldBankRebuildPolicy(
            candidate_chunk_size=policy_source.candidate_chunk_size,
            maximum_candidate_count=policy_source.maximum_candidate_count,
            maximum_tau_count=policy_source.maximum_tau_count,
            maximum_observation_count=policy_source.maximum_observation_count,
            maximum_prediction_cells_per_field=(policy_source.maximum_prediction_cells_per_field),
            maximum_array_storage_bytes_per_field=(
                policy_source.maximum_array_storage_bytes_per_field
            ),
            maximum_array_storage_bytes_total=(policy_source.maximum_array_storage_bytes_total),
        )
    except (AttributeError, TypeError, ValueError) as error:
        if isinstance(error, LongArcObservabilityRebuildError):
            raise
        raise LongArcObservabilityRebuildError(
            "compact rebuild contracts or policies are invalid"
        ) from error
    if not support.response_fields_excluded:
        raise LongArcObservabilityRebuildError(
            "compact rebuild support must exclude response fields"
        )
    if not _is_digest(selection_protocol_digest):
        raise LongArcObservabilityRebuildError("selection protocol digest is invalid")
    if len(support.episode_ids) != 1:
        raise LongArcObservabilityRebuildError(
            "sealed long-arc recovery requires exactly one response-free episode"
        )
    if tle_snapshot.collected_utc_ns >= min(
        item.support_start_utc_ns for item in support.observations
    ):
        raise LongArcObservabilityRebuildError(
            "catalogue TLE snapshot must be strictly pre-measurement"
        )
    raw_bytes = _snapshot_bytes(snapshot_payload)
    if sha256_digest(raw_bytes) != tle_snapshot.digest:
        raise LongArcObservabilityRebuildError("TLE snapshot bytes failed authentication")
    inventory = _revalidate_inventory(inventory)
    _authenticate_inventory_archive(inventory)
    storage_path = _validated_storage_directory(storage_directory)
    site_rf_authority = KnownSiteRfAuthority.create(
        observer_site=observer_site,
        nominal_rf_hz=nominal_rf_hz,
    )

    observation_ids = tuple(sorted(item.observation_id for item in support.observations))
    tau_states = tuple(
        CompactTauStateMetadata(
            tau_s=item.tau_s,
            log_prior_weight=item.log_prior_weight,
        )
        for item in tau_policy.points
    )
    reference_utc_ns = min(item.support_center_utc_ns for item in support.observations)
    prepared_fields: list[
        tuple[
            SealedFieldBankReceipt,
            tuple[CatalogueVerifiedTleMemberV1, ...],
            Sha256Digest,
            tuple[CompactCandidateMetadata, ...],
            str,
            int,
        ]
    ] = []
    total_storage_bytes = 0
    for receipt in inventory.field_banks:
        if receipt.candidate_count > tle_snapshot.object_count:
            raise LongArcObservabilityRebuildError(
                f"field {receipt.field_delta_s:+d} membership exceeds the TLE snapshot"
            )
        for item in receipt.candidates:
            expected_age_s = abs(reference_utc_ns - item.element_epoch_utc_ns) / 1e9
            if not math.isclose(
                item.element_age_s_at_reference,
                expected_age_s,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise LongArcObservabilityRebuildError(
                    f"field {receipt.field_delta_s:+d} candidate element age drifted"
                )
        members = _members_from_receipt(receipt)
        membership_digest = _membership_authority_digest(
            tle_snapshot=tle_snapshot,
            members=members,
        )
        candidate_metadata = tuple(
            CompactCandidateMetadata(
                catalog_number=item.catalog_number,
                object_name=item.object_name,
                selected_element_digest=item.selected_element_digest,
                element_epoch_utc_ns=item.element_epoch_utc_ns,
                element_age_s_at_reference=item.element_age_s_at_reference,
                eligible_episode_ids=support.episode_ids,
            )
            for item in receipt.candidates
        )
        universe_digest = _receipt_candidate_universe_digest(
            support=support,
            tle_snapshot=tle_snapshot,
            observer_site=observer_site,
            nominal_rf_hz=nominal_rf_hz,
            prediction_reference_utc_ns=reference_utc_ns,
            selection_protocol_digest=selection_protocol_digest,
            selection_policy_digest=receipt.selection_policy_digest,
            tle_membership_authority_digest=membership_digest,
            verified_tle_members=members,
            tau_search_policy=tau_policy.policy,
            candidates=candidate_metadata,
        )
        if universe_digest != receipt.candidate_universe_digest:
            raise LongArcObservabilityRebuildError(
                f"field {receipt.field_delta_s:+d} candidate-universe digest drifted"
            )
        storage_bytes = _preflight_compact_field_work(
            receipt=receipt,
            observation_count=len(observation_ids),
            tau_count=len(tau_states),
            prediction_policy=prediction_policy,
            compact_policy=compact_policy,
        )
        total_storage_bytes += storage_bytes
        if total_storage_bytes > compact_policy.maximum_array_storage_bytes_total:
            raise LongArcObservabilityRebuildError(
                "compact rebuild exceeds the declared total array-storage cap "
                f"({total_storage_bytes} > "
                f"{compact_policy.maximum_array_storage_bytes_total})"
            )
        propagation_model = _propagation_model(
            site_rf_authority=site_rf_authority,
            prediction_policy=prediction_policy,
            field_delta_s=receipt.field_delta_s,
        )
        prepared_fields.append(
            (
                receipt,
                members,
                membership_digest,
                candidate_metadata,
                propagation_model,
                storage_bytes,
            )
        )

    for (
        receipt,
        members,
        membership_digest,
        candidate_metadata,
        propagation_model,
        _,
    ) in prepared_fields:
        yield _rebuild_one_compact_field_bank(
            support=support,
            raw_snapshot_bytes=raw_bytes,
            tle_snapshot=tle_snapshot,
            site_rf_authority=site_rf_authority,
            selection_protocol_digest=selection_protocol_digest,
            tau_policy=tau_policy,
            prediction_policy=prediction_policy,
            receipt=receipt,
            members=members,
            membership_digest=membership_digest,
            candidate_metadata=candidate_metadata,
            observation_ids=observation_ids,
            tau_states=tau_states,
            propagation_model=propagation_model,
            storage_directory=storage_path,
            compact_policy=compact_policy,
        )


def _rebuild_one_compact_field_bank(
    *,
    support: CataloguePredictionSupportV1,
    raw_snapshot_bytes: bytes,
    tle_snapshot: TleSnapshotRefV1,
    site_rf_authority: KnownSiteRfAuthority,
    selection_protocol_digest: Sha256Digest,
    tau_policy: ExactTauPolicy,
    prediction_policy: Sgp4SupportPredictionPolicy,
    receipt: SealedFieldBankReceipt,
    members: tuple[CatalogueVerifiedTleMemberV1, ...],
    membership_digest: Sha256Digest,
    candidate_metadata: tuple[CompactCandidateMetadata, ...],
    observation_ids: tuple[Sha256Digest, ...],
    tau_states: tuple[CompactTauStateMetadata, ...],
    propagation_model: str,
    storage_directory: Path,
    compact_policy: CompactFieldBankRebuildPolicy,
) -> CompactCataloguePredictionBank:
    shape = (len(candidate_metadata), len(tau_states), len(observation_ids))
    field_label = (
        f"minus{abs(receipt.field_delta_s)}"
        if receipt.field_delta_s < 0
        else f"plus{receipt.field_delta_s}"
    )
    bank_hex = receipt.prediction_bank_digest.removeprefix(_SHA256_PREFIX)
    predicted_path = storage_directory / (f"{field_label}-{bank_hex}-predicted-cfo-hz.npy")
    uncertainty_path = storage_directory / (f"{field_label}-{bank_hex}-standard-uncertainty-hz.npy")
    if predicted_path.exists() or uncertainty_path.exists():
        raise LongArcObservabilityRebuildError(
            f"field {receipt.field_delta_s:+d} compact output already exists; "
            "refusing to overwrite it"
        )

    predicted_temporary = _temporary_array_path(storage_directory, "predicted")
    uncertainty_temporary = _temporary_array_path(storage_directory, "uncertainty")
    predicted_array: np.memmap | None = None
    uncertainty_array: np.memmap | None = None
    committed_paths: list[Path] = []
    try:
        predicted_array = np.lib.format.open_memmap(
            predicted_temporary,
            mode="w+",
            dtype=np.dtype("<f8"),
            shape=shape,
        )
        uncertainty_array = np.lib.format.open_memmap(
            uncertainty_temporary,
            mode="w+",
            dtype=np.dtype("<f8"),
            shape=shape,
        )
        bank_payload = _public_bank_payload_without_candidates(
            support=support,
            tle_snapshot=tle_snapshot,
            site_rf_authority=site_rf_authority,
            selection_protocol_digest=selection_protocol_digest,
            receipt=receipt,
            members=members,
            membership_digest=membership_digest,
            tau_policy=tau_policy,
            propagation_model=propagation_model,
        )
        prefix, suffix = _canonical_list_stream_parts(
            bank_payload,
            list_key="candidates",
        )
        public_digest = hashlib.sha256()
        public_digest.update(prefix)
        written_candidate_count = 0
        for chunk_start in range(
            0,
            len(candidate_metadata),
            compact_policy.candidate_chunk_size,
        ):
            chunk_stop = min(
                chunk_start + compact_policy.candidate_chunk_size,
                len(candidate_metadata),
            )
            chunk_receipts = receipt.candidates[chunk_start:chunk_stop]
            chunk_members = members[chunk_start:chunk_stop]
            chunk_universe = FrozenResponseFreeCandidateUniverse(
                candidates=tuple(
                    FrozenCatalogueCandidate(
                        catalog_number=item.catalog_number,
                        eligible_episode_ids=support.episode_ids,
                    )
                    for item in chunk_receipts
                ),
                selection_protocol_digest=selection_protocol_digest,
                selection_policy_digest=receipt.selection_policy_digest,
                tle_membership_authority_digest=membership_digest,
                catalogue_field_delta_s=receipt.field_delta_s,
            )
            chunk_bank = build_sgp4_catalogue_prediction_bank(
                support,
                raw_snapshot_bytes,
                tle_snapshot=tle_snapshot,
                site_rf_authority=site_rf_authority,
                candidate_universe=chunk_universe,
                verified_tle_members=chunk_members,
                tau_policy=tau_policy,
                prediction_policy=prediction_policy,
                catalogue_field_delta_s=receipt.field_delta_s,
            )
            _validate_chunk_bank(
                chunk_bank,
                expected_candidates=chunk_receipts,
                expected_members=chunk_members,
                expected_observation_ids=observation_ids,
                expected_tau_states=tau_states,
                support=support,
                tle_snapshot=tle_snapshot,
                site_rf_authority=site_rf_authority,
                selection_protocol_digest=selection_protocol_digest,
                selection_policy_digest=receipt.selection_policy_digest,
                membership_digest=membership_digest,
                propagation_model=propagation_model,
            )
            for chunk_index, candidate in enumerate(chunk_bank.candidates):
                candidate_index = chunk_start + chunk_index
                _write_candidate_arrays(
                    candidate,
                    predicted_array=predicted_array,
                    uncertainty_array=uncertainty_array,
                    candidate_index=candidate_index,
                )
                if written_candidate_count:
                    public_digest.update(b",")
                public_digest.update(canonical_json_bytes(candidate.model_dump(mode="json")))
                written_candidate_count += 1
            del chunk_bank
        if written_candidate_count != receipt.candidate_count:
            raise LongArcObservabilityRebuildError(
                f"field {receipt.field_delta_s:+d} compact candidate inventory is incomplete"
            )
        public_digest.update(suffix)
        actual_public_digest = f"sha256:{public_digest.hexdigest()}"
        if actual_public_digest != receipt.prediction_bank_digest:
            raise LongArcObservabilityRebuildError(
                f"field {receipt.field_delta_s:+d} prediction-bank digest drifted"
            )

        _flush_and_close_memmap(predicted_array)
        _flush_and_close_memmap(uncertainty_array)
        predicted_array = None
        uncertainty_array = None
        predicted_sha256 = file_sha256(predicted_temporary)
        uncertainty_sha256 = file_sha256(uncertainty_temporary)
        _link_without_overwrite(predicted_temporary, predicted_path)
        committed_paths.append(predicted_path)
        _link_without_overwrite(uncertainty_temporary, uncertainty_path)
        committed_paths.append(uncertainty_path)
        predicted_temporary.unlink()
        uncertainty_temporary.unlink()

        compact = CompactCataloguePredictionBank(
            field_delta_s=cast(
                Literal[-500, 0, 500],
                receipt.field_delta_s,
            ),
            support=support,
            tle_snapshot=tle_snapshot,
            observer_site=site_rf_authority.observer_site,
            nominal_rf_hz=site_rf_authority.nominal_rf_hz,
            prediction_reference_utc_ns=min(
                item.support_center_utc_ns for item in support.observations
            ),
            selection_protocol_digest=selection_protocol_digest,
            selection_policy_digest=receipt.selection_policy_digest,
            tle_membership_authority_digest=membership_digest,
            verified_tle_members=members,
            candidate_universe_digest=receipt.candidate_universe_digest,
            tau_search_policy=tau_policy.policy,
            propagation_model=propagation_model,
            candidate_metadata=candidate_metadata,
            tau_states=tau_states,
            observation_ids=observation_ids,
            prediction_shape=shape,
            source_candidate_count=receipt.candidate_count,
            returned_candidate_count=receipt.candidate_count,
            predicted_cfo_array_path=predicted_path.as_posix(),
            standard_uncertainty_array_path=uncertainty_path.as_posix(),
            predicted_cfo_array_sha256=predicted_sha256,
            standard_uncertainty_array_sha256=uncertainty_sha256,
            content_digest=actual_public_digest,
        )
    except Exception:
        if predicted_array is not None:
            _flush_and_close_memmap(predicted_array)
        if uncertainty_array is not None:
            _flush_and_close_memmap(uncertainty_array)
        for path in (predicted_temporary, uncertainty_temporary):
            path.unlink(missing_ok=True)
        for path in committed_paths:
            path.unlink(missing_ok=True)
        raise
    return compact


def _validate_chunk_bank(
    bank: CataloguePredictionBankV1,
    *,
    expected_candidates: tuple[SealedFieldCandidateReceipt, ...],
    expected_members: tuple[CatalogueVerifiedTleMemberV1, ...],
    expected_observation_ids: tuple[Sha256Digest, ...],
    expected_tau_states: tuple[CompactTauStateMetadata, ...],
    support: CataloguePredictionSupportV1,
    tle_snapshot: TleSnapshotRefV1,
    site_rf_authority: KnownSiteRfAuthority,
    selection_protocol_digest: Sha256Digest,
    selection_policy_digest: Sha256Digest,
    membership_digest: Sha256Digest,
    propagation_model: str,
) -> None:
    if (
        bank.support.content_digest != support.content_digest
        or bank.tle_snapshot != tle_snapshot
        or bank.observer_site != site_rf_authority.observer_site
        or bank.nominal_rf_hz != site_rf_authority.nominal_rf_hz
        or bank.selection_protocol_digest != selection_protocol_digest
        or bank.selection_policy_digest != selection_policy_digest
        or bank.tle_membership_authority_digest != membership_digest
        or bank.verified_tle_members != expected_members
        or bank.propagation_model != propagation_model
        or bank.response_accessed
        or bank.truncated_candidate_count != 0
        or bank.source_candidate_count != len(expected_candidates)
        or bank.returned_candidate_count != len(expected_candidates)
        or len(bank.candidates) != len(expected_candidates)
    ):
        raise LongArcObservabilityRebuildError(
            "chunked public-bank authority or accounting drifted"
        )
    expected_tau = tuple((item.tau_s, item.log_prior_weight) for item in expected_tau_states)
    for candidate, receipt in zip(
        bank.candidates,
        expected_candidates,
        strict=True,
    ):
        if (
            candidate.catalog_number != receipt.catalog_number
            or candidate.object_name != receipt.object_name
            or candidate.selected_element_digest != receipt.selected_element_digest
            or candidate.element_epoch_utc_ns != receipt.element_epoch_utc_ns
            or candidate.element_age_s_at_reference != receipt.element_age_s_at_reference
            or candidate.eligible_episode_ids != support.episode_ids
            or tuple((item.tau_s, item.log_prior_weight) for item in candidate.tau_states)
            != expected_tau
            or any(
                tuple(item.observation_id for item in state.predictions) != expected_observation_ids
                for state in candidate.tau_states
            )
        ):
            raise LongArcObservabilityRebuildError(
                f"candidate {receipt.catalog_number} chunk prediction metadata drifted"
            )


def _write_candidate_arrays(
    candidate: CatalogueCandidatePredictionV1,
    *,
    predicted_array: np.memmap,
    uncertainty_array: np.memmap,
    candidate_index: int,
) -> None:
    observation_count = predicted_array.shape[2]
    for tau_index, state in enumerate(candidate.tau_states):
        predicted_array[candidate_index, tau_index, :] = np.fromiter(
            (item.predicted_cfo_hz for item in state.predictions),
            dtype=np.dtype("<f8"),
            count=observation_count,
        )
        uncertainty_array[candidate_index, tau_index, :] = np.fromiter(
            (item.standard_uncertainty_hz for item in state.predictions),
            dtype=np.dtype("<f8"),
            count=observation_count,
        )


def _public_bank_payload_without_candidates(
    *,
    support: CataloguePredictionSupportV1,
    tle_snapshot: TleSnapshotRefV1,
    site_rf_authority: KnownSiteRfAuthority,
    selection_protocol_digest: Sha256Digest,
    receipt: SealedFieldBankReceipt,
    members: tuple[CatalogueVerifiedTleMemberV1, ...],
    membership_digest: Sha256Digest,
    tau_policy: ExactTauPolicy,
    propagation_model: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "algorithm_version": "support-integrated-tle-bank-v1",
        "support": support.model_dump(mode="json"),
        "tle_snapshot": tle_snapshot.model_dump(mode="json"),
        "observer_site": site_rf_authority.observer_site.model_dump(mode="json"),
        "nominal_rf_hz": site_rf_authority.nominal_rf_hz,
        "prediction_reference_utc_ns": min(
            item.support_center_utc_ns for item in support.observations
        ),
        "selection_protocol_digest": selection_protocol_digest,
        "selection_policy_digest": receipt.selection_policy_digest,
        "tle_membership_authority_digest": membership_digest,
        "verified_tle_members": [item.model_dump(mode="json") for item in members],
        "candidate_universe_digest": receipt.candidate_universe_digest,
        "population_conditioning": "frozen-response-free-universe-v1",
        "tau_search_policy": tau_policy.policy,
        "propagation_model": propagation_model,
        "prediction_error_model": ("independent-diagonal-conditional-on-candidate-v1"),
        "source_candidate_count": receipt.candidate_count,
        "returned_candidate_count": receipt.candidate_count,
        "truncated_candidate_count": 0,
        "response_accessed": False,
    }


def _canonical_list_stream_parts(
    payload_without_list: Mapping[str, object],
    *,
    list_key: str,
) -> tuple[bytes, bytes]:
    if list_key in payload_without_list:
        raise LongArcObservabilityRebuildError("canonical stream list key already exists")
    payload = {**payload_without_list, list_key: []}
    encoded = canonical_json_bytes(payload)
    marker = canonical_json_bytes(list_key) + b":[]"
    marker_index = encoded.find(marker)
    if marker_index < 0 or encoded.find(marker, marker_index + 1) >= 0:
        raise LongArcObservabilityRebuildError("canonical stream list marker is ambiguous")
    closing_bracket = marker_index + len(marker) - 1
    return encoded[:closing_bracket], encoded[closing_bracket:]


def _members_from_receipt(
    receipt: SealedFieldBankReceipt,
) -> tuple[CatalogueVerifiedTleMemberV1, ...]:
    return tuple(
        CatalogueVerifiedTleMemberV1(
            catalog_number=item.catalog_number,
            selected_element_digest=item.selected_element_digest,
            element_epoch_utc_ns=item.element_epoch_utc_ns,
        )
        for item in receipt.candidates
    )


def _membership_authority_digest(
    *,
    tle_snapshot: TleSnapshotRefV1,
    members: tuple[CatalogueVerifiedTleMemberV1, ...],
) -> Sha256Digest:
    return canonical_digest(
        {
            "algorithm_version": "response-free-tle-membership-authority-v1",
            "snapshot_digest": tle_snapshot.digest,
            "members": [item.model_dump(mode="json") for item in members],
        }
    )


def _receipt_candidate_universe_digest(
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
    candidates: tuple[CompactCandidateMetadata, ...],
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
            "source_candidate_count": len(candidates),
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


def _propagation_model(
    *,
    site_rf_authority: KnownSiteRfAuthority,
    prediction_policy: Sgp4SupportPredictionPolicy,
    field_delta_s: int,
) -> str:
    configuration_digest = canonical_digest(
        {
            "algorithm_version": "sgp4-wgs72-local-cubic-diagonal-v1",
            "site_rf_authority_digest": site_rf_authority.content_digest,
            "prediction_policy_digest": prediction_policy.digest,
            "catalogue_field_delta_s": field_delta_s,
        }
    )
    return f"sgp4-wgs72-local-cubic-diagonal-v1-{configuration_digest.removeprefix(_SHA256_PREFIX)}"


def _preflight_compact_field_work(
    *,
    receipt: SealedFieldBankReceipt,
    observation_count: int,
    tau_count: int,
    prediction_policy: Sgp4SupportPredictionPolicy,
    compact_policy: CompactFieldBankRebuildPolicy,
) -> int:
    candidate_count = receipt.candidate_count
    if candidate_count > compact_policy.maximum_candidate_count:
        raise LongArcObservabilityRebuildError(
            f"field {receipt.field_delta_s:+d} candidate count exceeds compact cap"
        )
    if tau_count > compact_policy.maximum_tau_count:
        raise LongArcObservabilityRebuildError("tau count exceeds compact cap")
    if observation_count > compact_policy.maximum_observation_count:
        raise LongArcObservabilityRebuildError("observation count exceeds compact cap")
    prediction_cells = candidate_count * tau_count * observation_count
    if prediction_cells > compact_policy.maximum_prediction_cells_per_field:
        raise LongArcObservabilityRebuildError(
            f"field {receipt.field_delta_s:+d} prediction cells exceed compact cap "
            f"({prediction_cells} > "
            f"{compact_policy.maximum_prediction_cells_per_field})"
        )
    propagated_states = prediction_cells * (prediction_policy.integration_sample_count + 1)
    if propagated_states > prediction_policy.maximum_propagated_states:
        raise LongArcObservabilityRebuildError(
            f"field {receipt.field_delta_s:+d} exceeds the declared propagation-work cap "
            f"({propagated_states} > {prediction_policy.maximum_propagated_states})"
        )
    # Two little-endian float64 cubes plus a conservative allowance for both
    # NPY headers.  The allowance keeps the declared storage cap honest without
    # depending on a NumPy-version-specific header length.
    storage_bytes = prediction_cells * 16 + 8_192
    if storage_bytes > compact_policy.maximum_array_storage_bytes_per_field:
        raise LongArcObservabilityRebuildError(
            f"field {receipt.field_delta_s:+d} array storage exceeds compact cap "
            f"({storage_bytes} > "
            f"{compact_policy.maximum_array_storage_bytes_per_field})"
        )
    return storage_bytes


def _revalidate_inventory(
    inventory: SealedResponseFreeBankInventory,
) -> SealedResponseFreeBankInventory:
    if (
        not isinstance(inventory, SealedResponseFreeBankInventory)
        or inventory.algorithm_version != "sealed-leading-field-bank-inventory-v1"
        or inventory.response_section_parsed is not False
        or inventory.candidate_ranking_performed is not False
        or not isinstance(inventory.archive_path, str)
        or not _is_digest(inventory.archive_sha256)
        or not _is_digest(inventory.content_digest)
        or not isinstance(inventory.field_banks, tuple)
        or len(inventory.field_banks) != len(_FIELD_DELTAS)
    ):
        raise LongArcObservabilityRebuildError("sealed response-free inventory metadata is invalid")
    receipts: list[SealedFieldBankReceipt] = []
    for expected_delta, source in zip(
        _FIELD_DELTAS,
        inventory.field_banks,
        strict=True,
    ):
        if (
            not isinstance(source, SealedFieldBankReceipt)
            or isinstance(source.field_delta_s, bool)
            or not isinstance(source.field_delta_s, int)
            or source.field_delta_s != expected_delta
            or isinstance(source.candidate_count, bool)
            or not isinstance(source.candidate_count, int)
            or source.candidate_count <= 0
            or source.candidate_count != len(source.candidates)
            or source.propagation_complete_for_association is not True
            or any(
                not _is_digest(value)
                for value in (
                    source.population_receipt_digest,
                    source.selection_policy_digest,
                    source.candidate_universe_digest,
                    source.prediction_bank_digest,
                )
            )
        ):
            raise LongArcObservabilityRebuildError("sealed field receipt metadata is invalid")
        candidates: list[SealedFieldCandidateReceipt] = []
        for item in source.candidates:
            if (
                not isinstance(item, SealedFieldCandidateReceipt)
                or isinstance(item.catalog_number, bool)
                or not isinstance(item.catalog_number, int)
                or item.catalog_number <= 0
                or not isinstance(item.object_name, str)
                or not 0 < len(item.object_name) <= 128
                or not _is_digest(item.selected_element_digest)
                or isinstance(item.element_epoch_utc_ns, bool)
                or not isinstance(item.element_epoch_utc_ns, int)
                or item.element_epoch_utc_ns <= 0
                or isinstance(item.element_age_s_at_reference, bool)
                or not isinstance(item.element_age_s_at_reference, (int, float))
                or not math.isfinite(item.element_age_s_at_reference)
                or item.element_age_s_at_reference < 0.0
            ):
                raise LongArcObservabilityRebuildError(
                    "sealed candidate receipt metadata is invalid"
                )
            candidates.append(
                SealedFieldCandidateReceipt(
                    catalog_number=item.catalog_number,
                    object_name=item.object_name,
                    selected_element_digest=item.selected_element_digest,
                    element_epoch_utc_ns=item.element_epoch_utc_ns,
                    element_age_s_at_reference=float(item.element_age_s_at_reference),
                )
            )
        numbers = tuple(item.catalog_number for item in candidates)
        if numbers != tuple(sorted(set(numbers))):
            raise LongArcObservabilityRebuildError(
                "sealed candidate inventory must be unique and canonical"
            )
        receipts.append(
            SealedFieldBankReceipt(
                field_delta_s=source.field_delta_s,
                population_receipt_digest=source.population_receipt_digest,
                selection_policy_digest=source.selection_policy_digest,
                candidate_universe_digest=source.candidate_universe_digest,
                prediction_bank_digest=source.prediction_bank_digest,
                candidate_count=source.candidate_count,
                candidates=tuple(candidates),
                propagation_complete_for_association=True,
            )
        )
    payload = {
        "algorithm_version": "sealed-leading-field-bank-inventory-v1",
        "archive_sha256": inventory.archive_sha256,
        "field_banks": [_receipt_payload(item) for item in receipts],
        "response_section_parsed": False,
        "candidate_ranking_performed": False,
    }
    if inventory.content_digest != canonical_digest(payload):
        raise LongArcObservabilityRebuildError(
            "sealed response-free inventory digest does not close"
        )
    return SealedResponseFreeBankInventory(
        archive_path=inventory.archive_path,
        archive_sha256=inventory.archive_sha256,
        field_banks=tuple(receipts),
        content_digest=inventory.content_digest,
    )


def _authenticate_inventory_archive(
    inventory: SealedResponseFreeBankInventory,
) -> None:
    archive_path = Path(inventory.archive_path)
    if not archive_path.is_absolute() or not archive_path.is_file():
        raise LongArcObservabilityRebuildError(
            "sealed response-free inventory archive path is invalid"
        )
    digest = hashlib.sha256()
    try:
        with archive_path.open("rb") as stream:
            while chunk := stream.read(1_048_576):
                digest.update(chunk)
    except OSError as error:
        raise LongArcObservabilityRebuildError(
            "sealed response-free inventory archive is unreadable"
        ) from error
    if f"sha256:{digest.hexdigest()}" != inventory.archive_sha256:
        raise LongArcObservabilityRebuildError(
            "sealed response-free inventory archive SHA-256 drifted"
        )


def _validated_storage_directory(storage_directory: Path) -> Path:
    unresolved_path = storage_directory.resolve(strict=False)
    qnap_root = Path("/mnt/qnap01")
    if unresolved_path == qnap_root or unresolved_path.is_relative_to(qnap_root):
        raise LongArcObservabilityRebuildError(
            "compact arrays may not be written beneath the read-only QNAP root"
        )
    try:
        path = storage_directory.resolve(strict=True)
    except OSError as error:
        raise LongArcObservabilityRebuildError(
            "compact storage directory does not exist"
        ) from error
    if path == qnap_root or path.is_relative_to(qnap_root):
        raise LongArcObservabilityRebuildError(
            "compact arrays may not be written beneath the read-only QNAP root"
        )
    if not path.is_dir():
        raise LongArcObservabilityRebuildError("compact storage path is not a directory")
    return path


def _temporary_array_path(storage_directory: Path, label: str) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".compact-{label}-",
        suffix=".npy",
        dir=storage_directory,
    )
    os.close(descriptor)
    return Path(name)


def _flush_and_close_memmap(value: np.memmap) -> None:
    value.flush()
    backing = getattr(value, "_mmap", None)
    if backing is not None:
        backing.close()


def _link_without_overwrite(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except FileExistsError as error:
        raise LongArcObservabilityRebuildError(
            "compact output appeared during commit; refusing to overwrite it"
        ) from error
    except OSError as error:
        raise LongArcObservabilityRebuildError(
            "compact output could not be committed atomically"
        ) from error


def _read_leading_field_bank_array(
    compressed: bytes,
    *,
    maximum_decompressed_prefix_bytes: int,
) -> Any:
    try:
        reader = zstd.ZstdDecompressor().stream_reader(compressed)
        buffer = bytearray()
        marker = b'"field_banks"'
        array_start: int | None = None
        scan_position = 0
        depth = 0
        in_string = False
        escaped = False
        while len(buffer) <= maximum_decompressed_prefix_bytes:
            chunk = reader.read(min(262_144, maximum_decompressed_prefix_bytes - len(buffer) + 1))
            if not chunk:
                break
            buffer.extend(chunk)
            if array_start is None:
                marker_position = buffer.find(marker)
                if marker_position < 0:
                    continue
                colon = buffer.find(b":", marker_position + len(marker))
                if colon < 0:
                    continue
                array_start = buffer.find(b"[", colon + 1)
                if array_start < 0:
                    array_start = None
                    continue
                scan_position = array_start
            while scan_position < len(buffer):
                value = buffer[scan_position]
                if in_string:
                    if escaped:
                        escaped = False
                    elif value == 0x5C:
                        escaped = True
                    elif value == 0x22:
                        in_string = False
                elif value == 0x22:
                    in_string = True
                elif value == 0x5B:
                    depth += 1
                elif value == 0x5D:
                    depth -= 1
                    if depth == 0:
                        encoded = bytes(buffer[array_start : scan_position + 1])
                        return json.loads(encoded)
                scan_position += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, zstd.ZstdError) as error:
        raise LongArcObservabilityRebuildError(
            "sealed field-bank prefix is not valid Zstandard JSON"
        ) from error
    raise LongArcObservabilityRebuildError(
        "field-bank receipt array was not closed inside the declared prefix cap"
    )


def _validate_field_bank_payload(value: Any) -> tuple[SealedFieldBankReceipt, ...]:
    if not isinstance(value, list) or len(value) != 3:
        raise LongArcObservabilityRebuildError("sealed field-bank inventory must contain 3 fields")
    receipts: list[SealedFieldBankReceipt] = []
    expected_keys = {
        "field_delta_s",
        "population_receipt_digest",
        "selection_policy_digest",
        "candidate_universe_digest",
        "prediction_bank_digest",
        "candidate_count",
        "candidates",
        "propagation_complete_for_association",
    }
    candidate_keys = {
        "catalog_number",
        "object_name",
        "selected_element_digest",
        "element_epoch_utc_ns",
        "element_age_s_at_reference",
    }
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != expected_keys:
            raise LongArcObservabilityRebuildError("sealed field-bank receipt schema drifted")
        raw_candidates = raw["candidates"]
        if not isinstance(raw_candidates, list):
            raise LongArcObservabilityRebuildError("sealed candidate inventory is not a list")
        candidates: list[SealedFieldCandidateReceipt] = []
        for item in raw_candidates:
            if not isinstance(item, dict) or set(item) != candidate_keys:
                raise LongArcObservabilityRebuildError("sealed candidate receipt schema drifted")
            try:
                candidate = SealedFieldCandidateReceipt(
                    catalog_number=int(item["catalog_number"]),
                    object_name=str(item["object_name"]),
                    selected_element_digest=str(item["selected_element_digest"]),
                    element_epoch_utc_ns=int(item["element_epoch_utc_ns"]),
                    element_age_s_at_reference=float(item["element_age_s_at_reference"]),
                )
            except (TypeError, ValueError) as error:
                raise LongArcObservabilityRebuildError(
                    "sealed candidate receipt values are invalid"
                ) from error
            if (
                candidate.catalog_number <= 0
                or not candidate.object_name
                or not _is_digest(candidate.selected_element_digest)
                or candidate.element_epoch_utc_ns <= 0
                or candidate.element_age_s_at_reference < 0.0
            ):
                raise LongArcObservabilityRebuildError(
                    "sealed candidate receipt values are outside bounds"
                )
            candidates.append(candidate)
        numbers = tuple(item.catalog_number for item in candidates)
        if numbers != tuple(sorted(set(numbers))):
            raise LongArcObservabilityRebuildError(
                "sealed candidate inventory must be unique and canonical"
            )
        try:
            receipt = SealedFieldBankReceipt(
                field_delta_s=int(raw["field_delta_s"]),
                population_receipt_digest=str(raw["population_receipt_digest"]),
                selection_policy_digest=str(raw["selection_policy_digest"]),
                candidate_universe_digest=str(raw["candidate_universe_digest"]),
                prediction_bank_digest=str(raw["prediction_bank_digest"]),
                candidate_count=int(raw["candidate_count"]),
                candidates=tuple(candidates),
                propagation_complete_for_association=raw["propagation_complete_for_association"],
            )
        except (TypeError, ValueError) as error:
            raise LongArcObservabilityRebuildError(
                "sealed field receipt values are invalid"
            ) from error
        if (
            receipt.field_delta_s not in _FIELD_DELTAS
            or receipt.candidate_count != len(receipt.candidates)
            or receipt.propagation_complete_for_association is not True
            or any(
                not _is_digest(item)
                for item in (
                    receipt.population_receipt_digest,
                    receipt.selection_policy_digest,
                    receipt.candidate_universe_digest,
                    receipt.prediction_bank_digest,
                )
            )
        ):
            raise LongArcObservabilityRebuildError("sealed field receipt failed closure")
        receipts.append(receipt)
    if tuple(item.field_delta_s for item in receipts) != _FIELD_DELTAS:
        raise LongArcObservabilityRebuildError("sealed fields must be ordered -500, 0, +500")
    return tuple(receipts)


def _receipt_payload(receipt: SealedFieldBankReceipt) -> dict[str, Any]:
    return {
        "field_delta_s": receipt.field_delta_s,
        "population_receipt_digest": receipt.population_receipt_digest,
        "selection_policy_digest": receipt.selection_policy_digest,
        "candidate_universe_digest": receipt.candidate_universe_digest,
        "prediction_bank_digest": receipt.prediction_bank_digest,
        "candidate_count": receipt.candidate_count,
        "candidates": [
            {
                "catalog_number": item.catalog_number,
                "object_name": item.object_name,
                "selected_element_digest": item.selected_element_digest,
                "element_epoch_utc_ns": item.element_epoch_utc_ns,
                "element_age_s_at_reference": item.element_age_s_at_reference,
            }
            for item in receipt.candidates
        ],
        "propagation_complete_for_association": True,
    }


def _snapshot_bytes(payload: SnapshotPayload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        try:
            return payload.encode("ascii")
        except UnicodeEncodeError as error:
            raise LongArcObservabilityRebuildError("TLE text must be ASCII") from error
    raise LongArcObservabilityRebuildError("TLE payload must be exact bytes or ASCII text")


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(_SHA256_PREFIX)
        and len(value) == len(_SHA256_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    )


__all__ = [
    "CompactFieldBankRebuildPolicy",
    "LongArcObservabilityRebuildError",
    "SealedFieldBankReceipt",
    "SealedFieldCandidateReceipt",
    "SealedResponseFreeBankInventory",
    "iter_rebuilt_digest_identical_compact_field_banks",
    "load_sealed_response_free_bank_inventory",
    "rebuild_digest_identical_field_banks",
]
