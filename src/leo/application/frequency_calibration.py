"""Trusted operational promotion of WP11 calibration draft evidence."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Protocol, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.calibration import (
    CalibrationEvidenceV1,
    ReceiverFrequencyCalibrationSetV1,
    ReceiverFrequencyCalibrationV1,
)
from leo.contracts.digests import (
    Sha256Digest,
    canonical_digest,
    canonical_json_bytes,
    sha256_digest,
)
from leo.qualification.frequency_calibration import (
    CalibrationCaptureEnvelopeV1,
    CalibrationExtractorReceiptV1,
    FrequencyCalibrationDraftEstimateV1,
    FrequencyCalibrationDwellV1,
    FrequencyCalibrationPlanV1,
    frozen_topology_for_radio,
    generate_frequency_calibration,
)
from leo.qualification.frequency_calibration_extractor import (
    BlindPilotCalibrationExtractor,
    ExactWindowIqReader,
)
from leo.storage import RecordingStore
from leo.storage.writer import PublishedBundle

TRUSTED_METHOD = "trusted_wp11_empirical_pilot_acquisition_center_v1"
SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class TrustedImmutableDocumentV1(ContractModel):
    schema_version: Literal[1] = 1
    logical_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    digest: Sha256Digest
    sealed_utc_ns: Annotated[int, Field(ge=0)]
    document: dict[str, Any]

    @model_validator(mode="after")
    def _content_matches(self) -> Self:
        if sha256_digest(canonical_json_bytes(self.document)) != self.digest:
            raise ValueError("trusted stored document digest does not match content")
        return self


class TrustedImmutableJsonPort(Protocol):
    def load(self, ref: ImmutableDocumentRefV1) -> TrustedImmutableDocumentV1: ...


class ImmutableReceiptPublisherPort(Protocol):
    """Persist a receipt after verifying its self-excluding semantic digest."""

    def publish_json(
        self,
        logical_uri: str,
        document: dict[str, Any],
        expected_digest: str,
    ) -> None: ...


class TrustedRecordingStorePort(Protocol):
    def inspect_uri(self, uri: str) -> PublishedBundle: ...

    def verify_digests(self, bundle: PublishedBundle) -> None: ...

    def reader(self, bundle: PublishedBundle, stream_id: str) -> ExactWindowIqReader: ...


class RecordingStoreCalibrationAdapter:
    """Trusted adapter using the ordinary store's full compressed/raw digest pass."""

    def __init__(self, store: RecordingStore) -> None:
        self._store = store

    def inspect_uri(self, uri: str) -> PublishedBundle:
        return self._store.inspect_uri(uri)

    def verify_digests(self, bundle: PublishedBundle) -> None:
        self._store.verify(bundle)

    def reader(self, bundle: PublishedBundle, stream_id: str) -> ExactWindowIqReader:
        return self._store.reader(bundle, stream_id, verify=True)


class ImmutableDocumentRefV1(ContractModel):
    schema_version: Literal[1] = 1
    logical_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    digest: Sha256Digest


class TrustedReleaseEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    evidence_digest: Sha256Digest
    release_id: SafeIdentifier
    git_revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    source_tree_digest: Sha256Digest
    executable_digest: Sha256Digest
    attestation_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    validated: Literal[True] = True

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        if self.evidence_digest != _digest_without(self, "evidence_digest"):
            raise ValueError("trusted release evidence digest does not match content")
        return self


class TrustedReleaseEvidencePort(Protocol):
    def current_release(self) -> TrustedReleaseEvidenceV1: ...


class TrustedCalibrationDwellInputV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: SafeIdentifier
    recording_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    extractor_product_ref: ImmutableDocumentRefV1


class TrustedCalibrationPromotionReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    promotion_digest: Sha256Digest
    promotion_id: SafeIdentifier
    promotion_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    promoted_utc_ns: Annotated[int, Field(ge=0)]
    promoter_git_revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    promoter_source_tree_digest: Sha256Digest
    promoter_executable_digest: Sha256Digest
    release_evidence_digest: Sha256Digest
    release_attestation_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    plan_ref: ImmutableDocumentRefV1
    plan_digest: Sha256Digest
    draft_digest: Sha256Digest
    capture_envelope_digests: tuple[Sha256Digest, ...]
    manifest_digests: tuple[Sha256Digest, ...]
    recording_uris: tuple[str, ...]
    extractor_product_refs: tuple[ImmutableDocumentRefV1, ...]
    extractor_receipt_digests: tuple[Sha256Digest, ...]
    calibration_id: SafeIdentifier
    calibration_set_id: SafeIdentifier
    trusted_method: Literal["trusted_wp11_empirical_pilot_acquisition_center_v1"] = (
        "trusted_wp11_empirical_pilot_acquisition_center_v1"
    )
    verification: Literal[
        "trusted_predeclaration_store_full_digests_and_sealed_extractor_products"
    ] = "trusted_predeclaration_store_full_digests_and_sealed_extractor_products"

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        count = len(self.capture_envelope_digests)
        if not count or any(
            len(items) != count
            for items in (
                self.manifest_digests,
                self.recording_uris,
                self.extractor_product_refs,
                self.extractor_receipt_digests,
            )
        ):
            raise ValueError("promotion evidence vectors must be nonempty and aligned")
        if self.promotion_digest != _digest_without(self, "promotion_digest"):
            raise ValueError("promotion receipt digest does not match content")
        return self


class TrustedCalibrationPromotionResultV1(ContractModel):
    schema_version: Literal[1] = 1
    receipt: TrustedCalibrationPromotionReceiptV1
    draft: FrequencyCalibrationDraftEstimateV1
    calibration: ReceiverFrequencyCalibrationV1
    calibration_set: ReceiverFrequencyCalibrationSetV1

    @model_validator(mode="after")
    def _outputs_replay(self) -> Self:
        if self.receipt.draft_digest != self.draft.draft_digest:
            raise ValueError("promotion receipt does not bind supplied draft")
        expected = _trusted_calibration(self.receipt, self.draft)
        if self.calibration != expected:
            raise ValueError("trusted calibration does not replay from promotion evidence")
        expected_set = ReceiverFrequencyCalibrationSetV1.create(
            calibration_set_id=self.receipt.calibration_set_id,
            calibrations=(expected,),
        )
        if self.calibration_set != expected_set:
            raise ValueError("trusted calibration set does not replay")
        return self


class CalibrationPromotionError(RuntimeError):
    pass


class TrustedFrequencyCalibrationPromoter:
    def __init__(
        self,
        *,
        plans: TrustedImmutableJsonPort,
        recordings: TrustedRecordingStorePort,
        artifacts: TrustedImmutableJsonPort,
        receipts: ImmutableReceiptPublisherPort,
        releases: TrustedReleaseEvidencePort,
    ) -> None:
        self._plans = plans
        self._recordings = recordings
        self._artifacts = artifacts
        self._receipts = receipts
        self._releases = releases

    def promote(
        self,
        *,
        plan_ref: ImmutableDocumentRefV1,
        dwell_inputs: tuple[TrustedCalibrationDwellInputV1, ...],
        promotion_id: str,
        promotion_uri: str,
        calibration_id: str,
        calibration_set_id: str,
        promoted_utc_ns: int,
        valid_until_utc_ns: int | None = None,
    ) -> TrustedCalibrationPromotionResultV1:
        stored_plan = self._plans.load(plan_ref)
        if (
            stored_plan.logical_uri != plan_ref.logical_uri
            or stored_plan.digest != plan_ref.digest
        ):
            raise CalibrationPromotionError("predeclared plan store returned wrong identity")
        plan = FrequencyCalibrationPlanV1.model_validate(stored_plan.document)
        if stored_plan.sealed_utc_ns > plan.declared_utc_ns:
            raise CalibrationPromotionError("predeclaration was published after it was declared")
        if len(dwell_inputs) != len(plan.scheduled_session_ids):
            raise CalibrationPromotionError("one sealed extractor product is required per dwell")

        dwells: list[FrequencyCalibrationDwellV1] = []
        for index, (session_id, dwell_input) in enumerate(
            zip(plan.scheduled_session_ids, dwell_inputs, strict=True)
        ):
            if dwell_input.session_id != session_id:
                raise CalibrationPromotionError("dwell input order differs from predeclaration")
            product_ref = dwell_input.extractor_product_ref
            bundle = self._recordings.inspect_uri(dwell_input.recording_uri)
            self._recordings.verify_digests(bundle)
            if bundle.uri != dwell_input.recording_uri:
                raise CalibrationPromotionError("recording store returned noncanonical bundle URI")
            if bundle.session_id != session_id:
                raise CalibrationPromotionError("recording store resolved wrong session")
            serial, physical_path, epoch, topology_digest = frozen_topology_for_radio(
                plan.radio_id
            )
            stream = bundle.manifest.streams[0]
            if stream.radio.serial != serial:
                raise CalibrationPromotionError("recording does not match trusted topology serial")
            capture = CalibrationCaptureEnvelopeV1.create(
                recording_uri=_bundle_uri(bundle),
                manifest_digest=bundle.manifest_sha256,
                manifest=bundle.manifest,
                stream_id=stream.stream_id,
                physical_receiver_id=physical_path,
                hardware_epoch_id=epoch,
                topology_evidence_digest=topology_digest,
            )
            stored_product = self._artifacts.load(product_ref)
            if (
                stored_product.logical_uri != product_ref.logical_uri
                or stored_product.digest != product_ref.digest
            ):
                raise CalibrationPromotionError("artifact store returned wrong extractor identity")
            extraction = CalibrationExtractorReceiptV1.model_validate(stored_product.document)
            rerun = BlindPilotCalibrationExtractor().extract(
                plan=plan,
                capture=capture,
                reader=self._recordings.reader(bundle, stream.stream_id),
            )
            if extraction != rerun:
                raise CalibrationPromotionError("sealed extractor product differs from IQ rerun")
            dwells.append(
                FrequencyCalibrationDwellV1(
                    scheduled_index=index,
                    capture=capture,
                    extraction=extraction,
                )
            )

        try:
            foundation = generate_frequency_calibration(
                plan=plan,
                dwells=tuple(dwells),
                calibration_id=calibration_id,
                calibration_set_id=calibration_set_id,
                created_utc_ns=promoted_utc_ns,
                valid_until_utc_ns=valid_until_utc_ns,
            )
        except ValueError as error:
            raise CalibrationPromotionError(f"foundation validation failed: {error}") from error
        if foundation.evidence.status != "sufficient" or foundation.draft_estimate is None:
            raise CalibrationPromotionError("calibration evidence is mathematically insufficient")
        draft = foundation.draft_estimate
        release = self._releases.current_release()
        if (
            release.git_revision != plan.extractor_git_revision
            or release.source_tree_digest != plan.extractor_source_tree_digest
            or release.executable_digest != plan.extractor_executable_digest
        ):
            raise CalibrationPromotionError(
                "validated release identity differs from predeclared extractor identity"
            )
        receipt_values: dict[str, Any] = {
            "schema_version": 1,
            "promotion_id": promotion_id,
            "promotion_uri": promotion_uri,
            "promoted_utc_ns": promoted_utc_ns,
            "promoter_git_revision": release.git_revision,
            "promoter_source_tree_digest": release.source_tree_digest,
            "promoter_executable_digest": release.executable_digest,
            "release_evidence_digest": release.evidence_digest,
            "release_attestation_uri": release.attestation_uri,
            "plan_ref": plan_ref,
            "plan_digest": plan.plan_digest,
            "draft_digest": draft.draft_digest,
            "capture_envelope_digests": tuple(d.capture.envelope_digest for d in dwells),
            "manifest_digests": tuple(d.capture.manifest_digest for d in dwells),
            "recording_uris": tuple(d.capture.recording_uri for d in dwells),
            "extractor_product_refs": tuple(
                item.extractor_product_ref for item in dwell_inputs
            ),
            "extractor_receipt_digests": tuple(d.extraction.receipt_digest for d in dwells),
            "calibration_id": calibration_id,
            "calibration_set_id": calibration_set_id,
            "trusted_method": TRUSTED_METHOD,
            "verification": (
                "trusted_predeclaration_store_full_digests_and_sealed_extractor_products"
            ),
        }
        receipt = TrustedCalibrationPromotionReceiptV1(
            promotion_digest=canonical_digest(_jsonable(receipt_values)),
            **receipt_values,
        )
        self._receipts.publish_json(
            receipt.promotion_uri,
            receipt.model_dump(mode="json"),
            receipt.promotion_digest,
        )
        calibration = _trusted_calibration(receipt, draft)
        return TrustedCalibrationPromotionResultV1(
            receipt=receipt,
            draft=draft,
            calibration=calibration,
            calibration_set=ReceiverFrequencyCalibrationSetV1.create(
                calibration_set_id=calibration_set_id,
                calibrations=(calibration,),
            ),
        )


def _trusted_calibration(
    receipt: TrustedCalibrationPromotionReceiptV1,
    draft: FrequencyCalibrationDraftEstimateV1,
) -> ReceiverFrequencyCalibrationV1:
    return ReceiverFrequencyCalibrationV1.create(
        calibration_id=receipt.calibration_id,
        radio_id=draft.radio_id,
        radio_serial=draft.radio_serial,
        receiver_id=draft.receiver_id,
        physical_receiver_id=draft.physical_receiver_id,
        hardware_epoch_id=draft.hardware_epoch_id,
        center_hz=draft.center_hz,
        uncertainty_lower_hz=draft.uncertainty_lower_hz,
        uncertainty_upper_hz=draft.uncertainty_upper_hz,
        valid_from_utc_ns=draft.proposed_valid_from_utc_ns,
        valid_until_utc_ns=draft.proposed_valid_until_utc_ns,
        method=TRUSTED_METHOD,
        created_utc_ns=receipt.promoted_utc_ns,
        evidence=(
            CalibrationEvidenceV1(
                kind="trusted_frequency_calibration_promotion_v1",
                uri=receipt.promotion_uri,
                digest=receipt.promotion_digest,
                source_revision=receipt.promoter_git_revision,
            ),
        ),
    )


def _bundle_uri(bundle: PublishedBundle) -> str:
    return bundle.uri


def _digest_without(value: ContractModel, field: str) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={field}))


def _jsonable(value: object) -> Any:
    if isinstance(value, ContractModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value
