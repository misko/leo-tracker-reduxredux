"""Authority boundary for durable WP11 trusted-campaign finalization."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import weakref
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, model_validator

from leo.analysis.starlink.acceptance import NATIVE_KNOWN_PILOT_EVIDENCE_STAGE
from leo.analysis.starlink.trusted_acceptance import evaluate_trusted_campaign_v2
from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
from leo.application.frequency_calibration import (
    ImmutableDocumentRefV1,
    NativeReleaseCalibrationEvidenceAdapter,
    TrustedReleaseEvidencePort,
    TrustedReleaseEvidenceV1,
)
from leo.artifacts import AnalysisArtifactStore, AnalysisRunManifestV1
from leo.catalog import (
    AnalysisRunState,
    CatalogRepository,
    PromotionPolicy,
    ScientificCampaignRegistration,
    ScientificCampaignSeal,
    ScientificCampaignStreamRegistration,
)
from leo.contracts.base import ContractModel
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1, ReceiverPathIdentityV1
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier, RecordingManifestV4
from leo.contracts.scientific import (
    DetectorPipelineBindingV1,
    LegacyExecutionEnvelopeV1,
    MatchedAcceptanceStatus,
    NativeKnownPilotEvidenceProductV2,
)
from leo.contracts.trusted_scientific import (
    TrustedMatchedRecoveryCampaignReceiptV2,
    TrustedMatchedRecoveryProductV2,
)
from leo.pipeline import IqReader
from leo.qualification.capture_modes import (
    CaptureModeCampaignAcceptanceReceiptV2,
    CaptureModeSessionCheckV1,
)
from leo.qualification.legacy_oracle import LegacyOracleReceiptV1
from leo.qualification.native_execution import ReleaseLocalNativeEvidenceExecutor
from leo.qualification.scientific_campaign import (
    SealedLegacyReferenceDecisionPort,
    campaign_config_from_accepted_capture,
)
from leo.qualification.trusted_matched_recovery_stage import TRUSTED_MATCHED_RECOVERY_STAGE
from leo.storage import PinnedLocalRoot, RecordingStore

_FINALIZER_REGISTRY: dict[int, tuple[weakref.ReferenceType[object], object]] = {}
_BOOTSTRAP_TOKEN = object()


class ImmutableCaptureCampaignAuthority:
    """Reload a create-only capture receipt from one confined evidence directory."""

    def __init__(self, evidence_root: PinnedLocalRoot) -> None:
        self._root = evidence_root.clone()

    def close(self) -> None:
        self._root.close()

    def resolve(self, ref: ImmutableDocumentRefV1) -> CaptureModeCampaignAcceptanceReceiptV2:
        prefix = "qualification://capture/"
        if not ref.logical_uri.startswith(prefix):
            raise ValueError("capture receipt URI is outside the qualification namespace")
        name = ref.logical_uri.removeprefix(prefix)
        payload = _read_confined_regular_file(
            self._root.io_root,
            name,
            maximum_bytes=128 * 1024,
        )
        if canonical_digest(json.loads(payload)) != ref.digest:
            raise ValueError("capture receipt differs from its durable reference")
        return CaptureModeCampaignAcceptanceReceiptV2.model_validate_json(payload)


class ConfinedLegacyExecutionAuthority:
    """Derive a scope envelope only from the sealed legacy receipt on disk."""

    def __init__(self, evidence_root: PinnedLocalRoot) -> None:
        self._root = evidence_root.clone()

    def close(self) -> None:
        self._root.close()

    def resolve(
        self,
        *,
        receipt_name: str,
        detector_binding: DetectorPipelineBindingV1,
        identity: ReceiverPathIdentityV1,
        calibration: ReceiverFrequencyCalibrationV1,
        iq_digest: str,
    ) -> LegacyExecutionEnvelopeV1:
        receipt = LegacyOracleReceiptV1.model_validate_json(
            _read_confined_regular_file(
                self._root.io_root,
                receipt_name,
                maximum_bytes=32 * 1024 * 1024,
            )
        )
        if receipt.iq_sha256 != iq_digest:
            raise ValueError("sealed legacy receipt is bound to different stored IQ")
        return SealedLegacyReferenceDecisionPort(
            receipt,
            detector_binding=detector_binding,
        ).execution_envelope(
            path_identity=identity,
            calibration=calibration,
            input_manifest_digest=identity.manifest_digest,
        )


class TrustedCampaignOutputStorePort(Protocol):
    def _bind_trusted_finalizer(self, finalizer: object, sentinel: object) -> object: ...

    def _publish_verified(
        self,
        authority: object,
        finalizer: object,
        sentinel: object,
        campaign_id: str,
        scientific: TrustedMatchedRecoveryCampaignReceiptV2,
        presentation: TrustedCampaignPresentationV1,
        material: TrustedCampaignSealMaterialV1,
    ) -> TrustedCampaignPublicationV1: ...

    def _load_verified(
        self,
        authority: object,
        finalizer: object,
        sentinel: object,
        campaign_id: str,
    ) -> tuple[
        TrustedCampaignPublicationV1,
        TrustedMatchedRecoveryCampaignReceiptV2,
        TrustedCampaignPresentationV1,
    ]: ...


@dataclass(frozen=True, slots=True)
class TrustedCampaignMemberInput:
    analysis_run_id: str
    analysis_product_id: int
    legacy_receipt_name: str


class TrustedCampaignDependencySealV1(ContractModel):
    schema_version: Literal[1] = 1
    analysis_product_id: Annotated[int, Field(gt=0)]
    kind: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    schema_version_of_product: Annotated[int, Field(gt=0)]
    scope_key: Identifier
    logical_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    digest: Sha256Digest


class TrustedCampaignMemberSealV1(ContractModel):
    schema_version: Literal[1] = 1
    ordinal: Annotated[int, Field(ge=0, lt=40)]
    session_id: Identifier
    stream_id: Identifier
    analysis_run_id: Identifier
    analysis_run_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    analysis_run_digest: Sha256Digest
    pipeline_release_id: Identifier
    analysis_product_id: Annotated[int, Field(gt=0)]
    analysis_product_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    analysis_product_digest: Sha256Digest
    frequency_calibration_id: Annotated[int, Field(gt=0)]
    calibration_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    calibration_digest: Sha256Digest
    legacy_envelope_digest: Sha256Digest
    legacy_receipt_name: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    product_dependency_closure: tuple[TrustedCampaignDependencySealV1, ...]

    @model_validator(mode="after")
    def _complete_product_lineage(self) -> Self:
        ids = tuple(item.analysis_product_id for item in self.product_dependency_closure)
        if self.analysis_product_id not in ids or len(ids) != len(set(ids)):
            raise ValueError("campaign member dependency closure is incomplete or duplicated")
        return self


class TrustedCampaignPresentationV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["trusted-campaign-presentation"] = "trusted-campaign-presentation"
    campaign_id: Identifier
    result_status: MatchedAcceptanceStatus
    mathematical_eligible: bool
    authoritative_evidence: Literal[True] = True
    production_accepted: bool
    strata: tuple[dict[str, object], ...]
    streams: tuple[tuple[str, str, str], ...]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    attribution_claimed: Literal[False] = False

    @model_validator(mode="after")
    def _bounded_projection(self) -> Self:
        if len(self.strata) != 4 or len(self.streams) != 40:
            raise ValueError("trusted campaign presentation must summarize four strata/40 streams")
        if self.production_accepted != (self.result_status is MatchedAcceptanceStatus.PASS):
            raise ValueError("production acceptance must equal the authoritative PASS result")
        return self


class TrustedCampaignOuterSealV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["trusted-campaign-outer-seal"] = "trusted-campaign-outer-seal"
    campaign_id: Identifier
    capture: ImmutableDocumentRefV1
    scientific: ImmutableDocumentRefV1
    presentation: ImmutableDocumentRefV1
    current_release_evidence_digest: Sha256Digest
    members: tuple[TrustedCampaignMemberSealV1, ...]
    result_status: MatchedAcceptanceStatus
    mathematical_eligible: bool
    authoritative_evidence: Literal[True] = True
    production_accepted: bool
    sealed_utc_ns: Annotated[int, Field(ge=0)]
    seal_digest: Sha256Digest

    @model_validator(mode="after")
    def _exact_seal(self) -> Self:
        if len(self.members) != 40 or tuple(item.ordinal for item in self.members) != tuple(
            range(40)
        ):
            raise ValueError("trusted campaign outer seal requires 40 ordered members")
        if self.production_accepted != (self.result_status is MatchedAcceptanceStatus.PASS):
            raise ValueError("production acceptance must equal the authoritative PASS result")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"seal_digest"}))
        if self.seal_digest != expected:
            raise ValueError(f"trusted campaign outer seal digest does not match: {expected}")
        return self


class TrustedCampaignPublicationV1(ContractModel):
    schema_version: Literal[1] = 1
    scientific: ImmutableDocumentRefV1
    presentation: ImmutableDocumentRefV1
    outer_seal: ImmutableDocumentRefV1
    seal: TrustedCampaignOuterSealV1


class TrustedCampaignSealMaterialV1(ContractModel):
    schema_version: Literal[1] = 1
    campaign_id: Identifier
    capture: ImmutableDocumentRefV1
    current_release_evidence_digest: Sha256Digest
    members: tuple[TrustedCampaignMemberSealV1, ...]
    result_status: MatchedAcceptanceStatus
    mathematical_eligible: bool
    production_accepted: bool

    @model_validator(mode="after")
    def _exact_material(self) -> Self:
        if len(self.members) != 40 or tuple(item.ordinal for item in self.members) != tuple(
            range(40)
        ):
            raise ValueError("trusted campaign seal material requires 40 ordered members")
        if self.production_accepted != (self.result_status is MatchedAcceptanceStatus.PASS):
            raise ValueError("production acceptance must equal replayed PASS status")
        return self


@dataclass(frozen=True, slots=True)
class _ResolvedMember:
    product: TrustedMatchedRecoveryProductV2
    registration: ScientificCampaignStreamRegistration
    seal: TrustedCampaignMemberSealV1


class TrustedCampaignFinalizer:
    """Resolve every authority source before publishing or mutating the catalog."""

    def __init__(
        self,
        *,
        catalog: CatalogRepository,
        artifacts: AnalysisArtifactStore,
        recordings: RecordingStore,
        calibrations: PostgresCalibrationCatalogAdapter,
        capture: ImmutableCaptureCampaignAuthority,
        legacy: ConfinedLegacyExecutionAuthority,
        releases: TrustedReleaseEvidencePort,
        native_executor: ReleaseLocalNativeEvidenceExecutor,
        outputs: TrustedCampaignOutputStorePort,
        _bootstrap_token: object | None = None,
    ) -> None:
        if _bootstrap_token is not _BOOTSTRAP_TOKEN:
            raise TypeError("trusted campaign finalizer must use authoritative bootstrap")
        if type(catalog) is not CatalogRepository:
            raise TypeError("trusted campaign requires the concrete PostgreSQL catalog")
        if type(artifacts) is not AnalysisArtifactStore:
            raise TypeError("trusted campaign requires the concrete immutable artifact store")
        if type(recordings) is not RecordingStore:
            raise TypeError("trusted campaign requires the concrete recording store")
        if artifacts.pinned_root_identity is None or recordings.pinned_root_identity is None:
            raise TypeError("trusted campaign requires pinned artifact and recording stores")
        if type(capture) is not ImmutableCaptureCampaignAuthority:
            raise TypeError("trusted campaign requires the confined capture authority")
        if type(legacy) is not ConfinedLegacyExecutionAuthority:
            raise TypeError("trusted campaign requires the confined legacy authority")
        if getattr(calibrations, "_repository", None) is not catalog:
            raise TypeError("trusted campaign calibration authority must bind the same catalog")
        if type(releases) is not NativeReleaseCalibrationEvidenceAdapter:
            raise TypeError("trusted campaign requires the deployed native-release authority")
        if type(native_executor) is not ReleaseLocalNativeEvidenceExecutor:
            raise TypeError("trusted campaign requires release-local native replay")
        from leo.qualification.trusted_campaign_store import (  # noqa: PLC0415
            ImmutableTrustedCampaignStore,
        )

        if type(outputs) is not ImmutableTrustedCampaignStore:
            raise TypeError("trusted campaign requires the immutable qualification store")
        sessions = getattr(catalog, "_sessions", None)
        bind = None if sessions is None else sessions.kw.get("bind")
        if bind is None:
            raise TypeError("trusted campaign catalog has no live database binding")
        if bind.dialect.name != "postgresql":
            raise TypeError("trusted campaign catalog must use PostgreSQL")
        with bind.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        self._catalog = catalog
        self._artifacts = artifacts
        self._recordings = recordings
        self._calibrations = calibrations
        self._capture = capture
        self._legacy = legacy
        self._releases = releases
        self._native_executor = native_executor
        self._outputs = outputs
        self._initialization_sentinel = object()
        registry_key = id(self)

        def discard_finalizer(
            _reference: weakref.ReferenceType[object],
            key: int = registry_key,
        ) -> None:
            _FINALIZER_REGISTRY.pop(key, None)

        _FINALIZER_REGISTRY[id(self)] = (
            weakref.ref(self, discard_finalizer),
            self._initialization_sentinel,
        )
        self._authority = outputs._bind_trusted_finalizer(
            self,
            self._initialization_sentinel,
        )

    @classmethod
    def _bootstrap_production(
        cls,
        *,
        catalog: CatalogRepository,
        artifacts: AnalysisArtifactStore,
        recordings: RecordingStore,
        calibrations: PostgresCalibrationCatalogAdapter,
        capture: ImmutableCaptureCampaignAuthority,
        legacy: ConfinedLegacyExecutionAuthority,
        releases: NativeReleaseCalibrationEvidenceAdapter,
        native_executor: ReleaseLocalNativeEvidenceExecutor,
        outputs: TrustedCampaignOutputStorePort,
    ) -> TrustedCampaignFinalizer:
        return cls(
            catalog=catalog,
            artifacts=artifacts,
            recordings=recordings,
            calibrations=calibrations,
            capture=capture,
            legacy=legacy,
            releases=releases,
            native_executor=native_executor,
            outputs=outputs,
            _bootstrap_token=_BOOTSTRAP_TOKEN,
        )

    def finalize(
        self,
        *,
        campaign_id: str,
        capture_ref: ImmutableDocumentRefV1,
        members: tuple[TrustedCampaignMemberInput, ...],
    ) -> TrustedCampaignPublicationV1:
        if (
            len(members) != 40
            or len({(item.analysis_run_id, item.analysis_product_id) for item in members}) != 40
        ):
            raise ValueError("trusted campaign finalization requires 40 unique product inputs")
        capture = self._capture.resolve(capture_ref)
        if canonical_digest(capture.model_dump(mode="json")) != capture_ref.digest:
            raise ValueError("accepted capture receipt digest differs from immutable reference")
        if not capture.accepted:
            raise ValueError("trusted campaign requires an accepted capture receipt")
        capture_checks = {
            check.session_id: check for trial in capture.trial_receipts for check in trial.checks
        }
        if len(capture_checks) != 30:
            raise ValueError("accepted capture authority does not contain exact 30 sessions")
        current_release = self._releases.current_release()
        resolved = tuple(
            self._resolve_member(item, current_release, capture_checks) for item in members
        )
        bindings = {
            item.product.receipt.config.detector_binding.binding_digest: (
                item.product.receipt.config.detector_binding
            )
            for item in resolved
        }
        if len(bindings) != 1:
            raise ValueError("trusted campaign products contain mixed detector bindings")
        config = campaign_config_from_accepted_capture(
            campaign_id=campaign_id,
            capture_receipt=capture,
            detector_binding=next(iter(bindings.values())),
        )
        products = tuple(item.product for item in resolved)
        scientific = evaluate_trusted_campaign_v2(config=config, products=products)
        if not scientific.content_complete or not scientific.mathematical_eligible:
            raise ValueError("trusted campaign lacks complete mathematically eligible evidence")
        by_identity = {
            (
                item.product.receipt.path_identity.session_id,
                item.product.receipt.path_identity.stream_id,
            ): item
            for item in resolved
        }
        if len(by_identity) != 40:
            raise ValueError("trusted campaign contains duplicate session/stream scopes")
        ordered = tuple(
            by_identity[(stream.product.receipt.path_identity.session_id, stream.product.scope_key)]
            for stream in scientific.streams
        )
        member_seals = tuple(
            item.seal.model_copy(update={"ordinal": ordinal})
            for ordinal, item in enumerate(ordered)
        )
        registrations = tuple(
            replace(item.registration, ordinal=ordinal) for ordinal, item in enumerate(ordered)
        )
        presentation = _presentation(scientific)

        material = TrustedCampaignSealMaterialV1(
            campaign_id=campaign_id,
            capture=capture_ref,
            current_release_evidence_digest=current_release.evidence_digest,
            members=member_seals,
            result_status=scientific.status,
            mathematical_eligible=scientific.mathematical_eligible,
            production_accepted=scientific.status is MatchedAcceptanceStatus.PASS,
        )

        publication = self._outputs._publish_verified(
            self._authority,
            self,
            self._initialization_sentinel,
            campaign_id,
            scientific,
            presentation,
            material,
        )
        self._catalog.create_scientific_campaign(
            ScientificCampaignRegistration(
                campaign_id=campaign_id,
                capture_uri=capture_ref.logical_uri,
                capture_digest=capture_ref.digest,
            )
        )
        for registration in registrations:
            self._catalog.add_scientific_campaign_stream(
                campaign_id=campaign_id,
                stream=registration,
            )
        self._catalog.seal_scientific_campaign(
            campaign_id=campaign_id,
            seal=ScientificCampaignSeal(
                scientific_uri=publication.scientific.logical_uri,
                scientific_digest=publication.scientific.digest,
                presentation_uri=publication.presentation.logical_uri,
                presentation_digest=publication.presentation.digest,
                result_status=scientific.status.value,
                outer_seal_uri=publication.outer_seal.logical_uri,
                outer_seal_digest=publication.outer_seal.digest,
            ),
        )
        return publication

    def resolve_publication(self, campaign_id: str) -> TrustedCampaignPublicationV1:
        """Re-resolve every authority before exposing one cataloged campaign seal."""

        record = self._catalog.scientific_campaign(campaign_id)
        if record is None or record.state != "sealed":
            raise ValueError("trusted campaign is not sealed in the catalog")
        publication, stored_scientific, stored_presentation = self._outputs._load_verified(
            self._authority,
            self,
            self._initialization_sentinel,
            campaign_id,
        )
        if (
            record.capture_uri != publication.seal.capture.logical_uri
            or record.capture_digest != publication.seal.capture.digest
            or record.outer_seal_uri != publication.outer_seal.logical_uri
            or record.outer_seal_digest != publication.outer_seal.digest
            or record.scientific_uri != publication.scientific.logical_uri
            or record.scientific_digest != publication.scientific.digest
            or record.presentation_uri != publication.presentation.logical_uri
            or record.presentation_digest != publication.presentation.digest
        ):
            raise ValueError("catalog campaign references differ from immutable publication")
        seal = publication.seal
        capture = self._capture.resolve(seal.capture)
        if not capture.accepted:
            raise ValueError("cataloged trusted campaign capture is no longer authoritative")
        release = self._releases.current_release()
        if release.evidence_digest != seal.current_release_evidence_digest:
            raise ValueError("cataloged trusted campaign uses a non-current deployed release")
        capture_checks = {
            check.session_id: check for trial in capture.trial_receipts for check in trial.checks
        }
        resolved = tuple(
            self._resolve_member(
                TrustedCampaignMemberInput(
                    analysis_run_id=item.analysis_run_id,
                    analysis_product_id=item.analysis_product_id,
                    legacy_receipt_name=item.legacy_receipt_name,
                ),
                release,
                capture_checks,
            )
            for item in seal.members
        )
        config = campaign_config_from_accepted_capture(
            campaign_id=campaign_id,
            capture_receipt=capture,
            detector_binding=resolved[0].product.receipt.config.detector_binding,
        )
        replayed = evaluate_trusted_campaign_v2(
            config=config,
            products=tuple(item.product for item in resolved),
        )
        if replayed != stored_scientific or _presentation(replayed) != stored_presentation:
            raise ValueError("stored trusted campaign differs from authoritative replay")
        if (
            seal.result_status is not replayed.status
            or seal.mathematical_eligible != replayed.mathematical_eligible
            or seal.production_accepted != (replayed.status is MatchedAcceptanceStatus.PASS)
            or record.result_status != replayed.status.value
        ):
            raise ValueError("outer/catalog campaign result differs from authoritative replay")
        expected_members = tuple(
            item.seal.model_copy(update={"ordinal": ordinal})
            for ordinal, item in enumerate(resolved)
        )
        if expected_members != seal.members:
            raise ValueError("outer campaign member seal differs from authoritative replay")
        return publication

    def _resolve_member(
        self,
        value: TrustedCampaignMemberInput,
        current_release: TrustedReleaseEvidenceV1,
        capture_checks: dict[str, CaptureModeSessionCheckV1],
    ) -> _ResolvedMember:
        release = current_release
        snapshot = self._catalog.run_seal_snapshot(value.analysis_run_id)
        if (
            self._catalog.run_state(value.analysis_run_id) is not AnalysisRunState.SUCCEEDED
            or snapshot.execution.promotion_policy != PromotionPolicy.EVIDENCE_ONLY.value
        ):
            raise ValueError("trusted campaign member run is not successful evidence-only")
        candidates = tuple(
            item for item in snapshot.products if item.product_id == value.analysis_product_id
        )
        if len(candidates) != 1:
            raise ValueError("trusted campaign product is absent or ambiguous in sealed run")
        catalog_product = candidates[0]
        if (
            catalog_product.run_id != value.analysis_run_id
            or catalog_product.stage_key != TRUSTED_MATCHED_RECOVERY_STAGE.key
            or catalog_product.kind != "starlink.trusted-matched-recovery"
            or catalog_product.schema_version != 2
            or catalog_product.role != "scientific"
            or catalog_product.status != "complete"
            or not catalog_product.available
        ):
            raise ValueError("catalog product is not a complete trusted recovery V2 artifact")
        product = TrustedMatchedRecoveryProductV2.model_validate(
            self._artifacts.read_json(catalog_product.logical_uri, catalog_product.digest)
        )
        identity = product.receipt.path_identity
        capture_check = capture_checks.get(identity.session_id)
        if capture_check is None or snapshot.execution.bundle_uri != capture_check.bundle_uri:
            raise ValueError("run recording URI differs from accepted capture authority")
        try:
            radio_index = capture_check.observed_radio_ids.index(identity.radio_id)
        except ValueError as error:
            raise ValueError("trusted product radio is absent from accepted capture") from error
        if (
            capture_check.observed_radio_serials[radio_index] != identity.radio_serial
            or capture_check.declared_receiver_chain_ids[radio_index]
            != identity.physical_receiver_id
            or capture_check.declared_hardware_epoch_ids[radio_index] != identity.hardware_epoch_id
        ):
            raise ValueError("trusted product receiver topology differs from accepted capture")
        dependency_records = self._catalog.product_dependency_closure(value.analysis_product_id)
        if any(
            item.run_id != value.analysis_run_id
            or not item.available
            or item.media_type != "application/json"
            for item in dependency_records
        ):
            raise ValueError("trusted product dependency closure is unavailable or cross-run")
        dependency_seals = tuple(
            TrustedCampaignDependencySealV1(
                analysis_product_id=item.product_id,
                kind=item.kind,
                schema_version_of_product=item.schema_version,
                scope_key=item.scope_key,
                logical_uri=item.logical_uri,
                digest=item.digest,
            )
            for item in dependency_records
        )
        for item in dependency_records:
            self._artifacts.read_json(item.logical_uri, item.digest)
        direct_dependencies = self._catalog.product_direct_dependencies(value.analysis_product_id)
        closure_native_dependencies = tuple(
            item
            for item in dependency_records
            if (item.kind, item.schema_version) == ("starlink.native-known-pilot-evidence", 2)
        )
        native_dependencies = tuple(
            item
            for item in direct_dependencies
            if (item.kind, item.schema_version) == ("starlink.native-known-pilot-evidence", 2)
        )
        if (
            len(direct_dependencies) != 1
            or len(native_dependencies) != 1
            or len(closure_native_dependencies) != 1
        ):
            raise ValueError("trusted product requires one exact native V2 dependency")
        native_record = native_dependencies[0]
        if (
            native_record.role != "scientific"
            or native_record.stage_key != NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key
            or native_record.status != "complete"
            or not native_record.available
            or native_record.run_id != value.analysis_run_id
            or native_record.scope_key != product.scope_key
        ):
            raise ValueError("native V2 dependency has invalid catalog lineage")
        native_dependency = NativeKnownPilotEvidenceProductV2.model_validate(
            self._artifacts.read_json(
                native_record.logical_uri,
                native_record.digest,
            )
        )
        if (
            native_dependency.product_digest != product.receipt.native_evidence_product_digest
            or native_dependency.analysis_run_id != value.analysis_run_id
            or native_dependency.scope_key != product.scope_key
            or native_dependency.path_identity != identity
            or native_dependency.calibration != product.receipt.calibration
            or native_dependency.execution != product.receipt.native_execution
            or native_dependency.release != product.receipt.native_release
        ):
            raise ValueError("native dependency artifact differs from trusted recovery receipt")
        if (
            product.analysis_run_id != value.analysis_run_id
            or product.scope_key != catalog_product.scope_key
            or identity.session_id != snapshot.execution.session_id
            or identity.manifest_digest != snapshot.execution.input_manifest_digest
            or product.receipt.native_release != release.native_release
        ):
            raise ValueError("trusted product artifact is retargeted from run/scope/release")
        authoritative = self._calibrations.resolve(identity)
        if authoritative.calibration != product.receipt.calibration:
            raise ValueError("trusted product calibration differs from durable authority")
        calibration = self._catalog.resolve_frequency_calibration(
            radio_serial=identity.radio_serial,
            receiver_id=identity.receiver_id,
            physical_receiver_id=identity.physical_receiver_id,
            hardware_epoch_id=identity.hardware_epoch_id,
            capture_start_utc_ns=identity.capture_utc_ns,
            capture_end_utc_ns=identity.capture_end_utc_ns,
        )
        promotion_id = calibration.calibration_set.registration.promotion_id
        if promotion_id is None:
            raise ValueError("trusted campaign calibration uses quarantined legacy lineage")
        publication = self._calibrations.lookup(promotion_id)
        if (
            publication.calibration_set != authoritative.calibration_set
            or publication.publication.bundle_uri
            != calibration.calibration_set.registration.evidence_uri
            or publication.publication.manifest_digest
            != calibration.calibration_set.registration.evidence_digest
        ):
            raise ValueError("calibration catalog differs from durable promotion bundle")
        bundle = self._recordings.inspect_uri(snapshot.execution.bundle_uri)
        if (
            bundle.session_id != identity.session_id
            or bundle.manifest_sha256 != identity.manifest_digest
        ):
            raise ValueError("recording bundle differs from trusted product identity")
        self._recordings.verify(bundle)
        recording_streams = tuple(
            item for item in bundle.manifest.streams if item.stream_id == identity.stream_id
        )
        if len(recording_streams) != 1:
            raise ValueError("trusted recording stream is absent or ambiguous")
        recording_stream = recording_streams[0]
        if isinstance(bundle.manifest, RecordingManifestV4):
            raise ValueError("trusted campaign does not accept mixed-rate manifests")
        settings = recording_stream.applied_settings
        timing = recording_stream.timing
        if (
            recording_stream.radio.radio_id != identity.radio_id
            or recording_stream.radio.serial != identity.radio_serial
            or settings is None
            or identity.receiver_id not in settings.receiver_ids
            or settings.sample_rate_hz != 2_500_000
            or recording_stream.captured_sample_count != 150_000_000
            or timing is None
            or timing.first_sample.estimate_utc_ns != identity.capture_utc_ns
            or timing.last_sample.estimate_utc_ns + 400 != identity.capture_end_utc_ns
            or bundle.manifest.capture_plan.profile_revision.revision_digest
            != identity.profile_revision_digest
        ):
            raise ValueError("recording manifest differs from trusted receiver path identity")
        iq = self._recordings.reader(bundle, identity.stream_id, verify=True)
        iq_digest = _receiver_iq_digest(iq, identity.receiver_id)
        legacy = self._legacy.resolve(
            receipt_name=value.legacy_receipt_name,
            detector_binding=product.receipt.config.detector_binding,
            identity=identity,
            calibration=authoritative.calibration,
            iq_digest=iq_digest,
        )
        if legacy != product.receipt.legacy_execution:
            raise ValueError("legacy authority returned different sealed execution evidence")
        replayed_native = self._native_executor.execute(
            iq=iq,
            path_identity=identity,
            calibration=authoritative.calibration,
            release=release.native_release,
            config=product.receipt.config,
        )
        if (
            replayed_native.decisions != native_dependency.execution.decisions
            or replayed_native.execution_environment_digest
            != native_dependency.execution.execution_environment_digest
            or replayed_native.worker_output_digest
            != native_dependency.execution.worker_output_digest
        ):
            raise ValueError("native artifact differs from current release-local IQ replay")
        run_manifest = self._catalog.run_manifest_reference(value.analysis_run_id)
        manifest = AnalysisRunManifestV1.model_validate(
            self._artifacts.read_json(run_manifest.logical_uri, run_manifest.digest)
        )
        manifest_products = {item.product_id: item for item in manifest.products}
        manifest_product = manifest_products.get(value.analysis_product_id)
        manifest_native = manifest_products.get(native_record.product_id)
        if (
            manifest.run_id != value.analysis_run_id
            or manifest.session_id != identity.session_id
            or manifest.pipeline_release_id != product.pipeline_release
            or manifest.input_manifest_digest != identity.manifest_digest
            or manifest_product is None
            or manifest_product.logical_uri != catalog_product.logical_uri
            or manifest_product.digest != catalog_product.digest
            or manifest_product.scope_key != product.scope_key
            or manifest_product.kind != catalog_product.kind
            or manifest_product.product_schema_version != catalog_product.schema_version
            or manifest_native is None
            or manifest_native.logical_uri != native_record.logical_uri
            or manifest_native.digest != native_record.digest
            or manifest_native.scope_key != native_record.scope_key
            or manifest_native.kind != native_record.kind
            or manifest_native.product_schema_version != native_record.schema_version
        ):
            raise ValueError("sealed analysis-run manifest differs from trusted product")
        for dependency in dependency_records:
            declared = manifest_products.get(dependency.product_id)
            if (
                declared is None
                or declared.logical_uri != dependency.logical_uri
                or declared.digest != dependency.digest
                or declared.scope_key != dependency.scope_key
                or declared.kind != dependency.kind
                or declared.product_schema_version != dependency.schema_version
            ):
                raise ValueError("run manifest omits or retargets product dependency closure")
        registration = ScientificCampaignStreamRegistration(
            ordinal=0,
            session_id=identity.session_id,
            stream_id=identity.stream_id,
            analysis_run_id=value.analysis_run_id,
            analysis_run_uri=run_manifest.logical_uri,
            analysis_run_digest=run_manifest.digest,
            pipeline_release_id=product.pipeline_release,
            analysis_product_id=value.analysis_product_id,
            frequency_calibration_id=calibration.calibration.database_id,
            capture_uri=snapshot.execution.bundle_uri,
            capture_digest=identity.manifest_digest,
            calibration_uri=calibration.calibration.registration.evidence_uri,
            calibration_digest=calibration.calibration.registration.evidence_digest,
            scientific_uri=catalog_product.logical_uri,
            scientific_digest=catalog_product.digest,
            status=product.receipt.status.value,
        )
        seal = TrustedCampaignMemberSealV1(
            ordinal=0,
            session_id=identity.session_id,
            stream_id=identity.stream_id,
            analysis_run_id=value.analysis_run_id,
            analysis_run_uri=run_manifest.logical_uri,
            analysis_run_digest=run_manifest.digest,
            pipeline_release_id=product.pipeline_release,
            analysis_product_id=value.analysis_product_id,
            analysis_product_uri=catalog_product.logical_uri,
            analysis_product_digest=catalog_product.digest,
            frequency_calibration_id=calibration.calibration.database_id,
            calibration_uri=calibration.calibration.registration.evidence_uri,
            calibration_digest=calibration.calibration.registration.evidence_digest,
            legacy_envelope_digest=legacy.envelope_digest,
            legacy_receipt_name=value.legacy_receipt_name,
            product_dependency_closure=dependency_seals,
        )
        return _ResolvedMember(product=product, registration=registration, seal=seal)


def _trusted_finalizer_is_registered(finalizer: object, sentinel: object) -> bool:
    registered = _FINALIZER_REGISTRY.get(id(finalizer))
    return (
        registered is not None
        and registered[0]() is finalizer
        and registered[1] is sentinel
        and getattr(finalizer, "_initialization_sentinel", None) is sentinel
    )


def _receiver_iq_digest(iq: IqReader, receiver_id: int) -> str:
    receiver_ids = iq.receiver_ids
    try:
        receiver_index = receiver_ids.index(receiver_id)
    except ValueError as error:
        raise ValueError("trusted legacy IQ receiver is absent") from error
    digest = hashlib.sha256()
    observed = 0
    for block in iq.iter_blocks(block_samples=1_000_000):
        if block.metadata.session_sample_start != observed:
            raise ValueError("trusted legacy IQ contains a discontinuity")
        selected = block.samples[:, receiver_index, :]
        digest.update(selected.astype("<i2", copy=False).tobytes(order="C"))
        observed += block.metadata.sample_count
    if observed != iq.sample_count:
        raise ValueError("trusted legacy IQ digest did not cover the complete dwell")
    return f"sha256:{digest.hexdigest()}"


def _presentation(
    scientific: TrustedMatchedRecoveryCampaignReceiptV2,
) -> TrustedCampaignPresentationV1:
    return TrustedCampaignPresentationV1(
        campaign_id=scientific.config.campaign_id,
        result_status=scientific.status,
        mathematical_eligible=scientific.mathematical_eligible,
        production_accepted=scientific.status is MatchedAcceptanceStatus.PASS,
        strata=tuple(
            {
                "stratum_id": item.stratum_id,
                "status": item.status.value,
                "observed_session_count": item.observed_session_count,
                "reference_positive_count": item.reference_positive_count,
                "associated_reference_positive_count": item.associated_reference_positive_count,
                "recovery": item.recovery.model_dump(mode="json"),
                "qam_noninferiority_passed": item.qam_noninferiority_passed,
            }
            for item in scientific.strata
        ),
        streams=tuple(
            (
                item.product.receipt.path_identity.session_id,
                item.product.scope_key,
                item.product.receipt.status.value,
            )
            for item in scientific.streams
        ),
    )


def _reject_qnap(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    qnap = Path("/mnt/qnap01")
    if absolute == qnap or qnap in absolute.parents:
        raise ValueError("trusted campaign evidence cannot use QNAP")


def _read_confined_regular_file(root: Path, name: str, *, maximum_bytes: int) -> bytes:
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError("trusted evidence reference must be one confined file name")
    root_descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_descriptor,
        )
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o440
                or info.st_nlink != 1
                or info.st_size > maximum_bytes
            ):
                raise ValueError("trusted evidence lacks immutable publication semantics")
            payload = bytearray()
            while len(payload) <= maximum_bytes:
                block = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - len(payload)))
                if not block:
                    break
                payload.extend(block)
            if len(payload) != info.st_size:
                raise ValueError("trusted evidence changed while being read")
            return bytes(payload)
        finally:
            os.close(descriptor)
    finally:
        os.close(root_descriptor)
