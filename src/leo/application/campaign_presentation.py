"""Bounded, read-only projection of authoritative WP11 campaign evidence."""

from __future__ import annotations

import os
import stat
from collections import Counter, defaultdict
from typing import Literal, cast

from leo.application.trusted_campaign import (
    TrustedCampaignOuterSealV1,
    TrustedCampaignPresentationV1,
)
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import (
    CatalogRepository,
    CatalogSessionReadSnapshot,
    ScientificCampaignRecord,
)
from leo.contracts.digests import sha256_digest
from leo.contracts.scientific import NativeKnownPilotEvidenceProductV2
from leo.contracts.trusted_scientific import (
    TrustedMatchedRecoveryCampaignReceiptV2,
    TrustedMatchedRecoveryProductV2,
)
from leo.presentation.models import (
    QualificationCalibrationV1,
    QualificationCampaignDetailV1,
    QualificationCampaignListItemV1,
    QualificationCampaignListV1,
    QualificationDocumentRefV1,
    QualificationQamV1,
    QualificationRecoveryV1,
    QualificationStratumV1,
)
from leo.storage import PinnedLocalRoot

_LIMITS = {
    "scientific.json": 64 * 1024 * 1024,
    "presentation.json": 256 * 1024,
    "seal.json": 2 * 1024 * 1024,
}
_MAX_CLOSURE_PRODUCTS = 160
_MAX_CLOSURE_BYTES = 512 * 1024 * 1024
_MAX_LIST_DOCUMENT_BYTES = 128 * 1024 * 1024


class CampaignPresentationError(RuntimeError):
    """Authoritative campaign evidence is unavailable or inconsistent."""


class CatalogCampaignPresentation:
    """Verify durable bounded evidence without replaying raw recording IQ."""

    def __init__(
        self,
        catalog: CatalogRepository,
        artifacts: AnalysisArtifactStore,
        qualification_root: PinnedLocalRoot,
    ) -> None:
        if artifacts.pinned_root_identity is None:
            raise ValueError("campaign presentation requires a pinned artifact store")
        self._catalog = catalog
        self._artifacts = artifacts
        self._root = qualification_root.clone()
        self._campaigns = self._root.child("trusted-campaigns")

    def close(self) -> None:
        self._campaigns.close()
        self._root.close()

    def campaigns(self, *, cursor: int, limit: int) -> QualificationCampaignListV1:
        if cursor < 0 or not 1 <= limit <= 25:
            raise ValueError("campaign pagination is outside its bounded range")
        total = self._catalog.scientific_campaign_count()
        budget = [0]
        details = tuple(
            self._detail(record, verify_members=False, read_budget=budget)
            for record in self._catalog.scientific_campaigns(cursor=cursor, limit=limit)
        )
        next_cursor = cursor + len(details)
        return QualificationCampaignListV1(
            items=tuple(self._list_item(item) for item in details),
            total=total,
            next_cursor=next_cursor if next_cursor < total else None,
        )

    def campaign(self, campaign_id: str) -> QualificationCampaignDetailV1 | None:
        record = self._catalog.scientific_campaign(campaign_id)
        if record is None or record.state != "sealed" or record.seal_authority_version != 1:
            return None
        return self._detail(record, verify_members=True, read_budget=None)

    @staticmethod
    def _list_item(detail: QualificationCampaignDetailV1) -> QualificationCampaignListItemV1:
        return QualificationCampaignListItemV1.model_validate(
            detail.model_dump(
                exclude={
                    "pipeline_release_ids",
                    "capture",
                    "outer_seal",
                    "outer_sealed_utc_ns",
                    "current_release_evidence_digest",
                    "strata",
                    "calibrations",
                }
            )
        )

    def _detail(
        self,
        record: ScientificCampaignRecord,
        *,
        verify_members: bool,
        read_budget: list[int] | None,
    ) -> QualificationCampaignDetailV1:
        if (
            record.state != "sealed"
            or record.seal_authority_version != 1
            or record.sealed_at is None
            or record.scientific_uri is None
            or record.scientific_digest is None
            or record.presentation_uri is None
            or record.presentation_digest is None
            or record.outer_seal_uri is None
            or record.outer_seal_digest is None
            or record.result_status is None
        ):
            raise CampaignPresentationError("campaign is not an authority-version-1 seal")
        payloads = {
            name: self._read_document(record.campaign_id, name, read_budget=read_budget)
            for name in ("scientific.json", "presentation.json", "seal.json")
        }
        scientific = TrustedMatchedRecoveryCampaignReceiptV2.model_validate_json(
            payloads["scientific.json"]
        )
        presentation = TrustedCampaignPresentationV1.model_validate_json(
            payloads["presentation.json"]
        )
        seal = TrustedCampaignOuterSealV1.model_validate_json(payloads["seal.json"])
        refs = {
            "scientific": (record.scientific_uri, record.scientific_digest, seal.scientific),
            "presentation": (
                record.presentation_uri,
                record.presentation_digest,
                seal.presentation,
            ),
            "outer": (record.outer_seal_uri, record.outer_seal_digest, None),
        }
        for name, (uri, digest, sealed_ref) in refs.items():
            filename = "seal.json" if name == "outer" else f"{name}.json"
            expected_uri = f"qualification://trusted-campaigns/{record.campaign_id}/{filename}"
            if uri != expected_uri or digest != sha256_digest(payloads[filename]):
                raise CampaignPresentationError(f"catalog {name} document reference differs")
            if sealed_ref is not None and (
                sealed_ref.logical_uri != uri or sealed_ref.digest != digest
            ):
                raise CampaignPresentationError(f"outer seal {name} reference differs")
        if (
            seal.campaign_id != record.campaign_id
            or seal.capture.logical_uri != record.capture_uri
            or seal.capture.digest != record.capture_digest
            or seal.result_status.value != record.result_status
            or presentation.campaign_id != record.campaign_id
            or presentation.result_status != seal.result_status
            or scientific.config.campaign_id != record.campaign_id
            or scientific.status != seal.result_status
            or presentation.mathematical_eligible != scientific.mathematical_eligible
            or seal.mathematical_eligible != scientific.mathematical_eligible
            or presentation.production_accepted != seal.production_accepted
        ):
            raise CampaignPresentationError("catalog and campaign documents disagree")
        if verify_members:
            self._verify_members(record, seal, scientific)
        expected = {
            item.stratum_id: item.required_session_count for item in scientific.config.strata
        }
        strata = tuple(
            QualificationStratumV1(
                stratum_id=item.stratum_id,
                status=item.status.value,
                reason=item.reason,
                expected_session_count=expected[item.stratum_id],
                observed_session_count=item.observed_session_count,
                reference_positive_count=item.reference_positive_count,
                associated_reference_positive_count=item.associated_reference_positive_count,
                recovery=QualificationRecoveryV1(
                    successes=item.recovery.successes,
                    trials=item.recovery.trials,
                    point_estimate=item.recovery.point_estimate,
                    confidence_level=item.recovery.confidence_level,
                    wilson_lower_bound=item.recovery.wilson_one_sided_lower,
                    clopper_pearson_lower_bound=(item.recovery.clopper_pearson_one_sided_lower),
                ),
                qam=QualificationQamV1(
                    reference_positive_count=item.reference_qam_positive_count,
                    native_recovery_count=item.recovery.successes,
                    mean_accuracy_difference=item.mean_qam_accuracy_difference,
                    accuracy_difference_lower_bound=item.qam_accuracy_difference_lower_bound,
                    interval_method=item.qam_interval_method,
                    noninferiority_passed=item.qam_noninferiority_passed,
                ),
            )
            for item in scientific.strata
        )
        return QualificationCampaignDetailV1(
            campaign_id=record.campaign_id,
            result_status=cast(Literal["pass", "fail", "inconclusive"], record.result_status),
            reason=scientific.reason,
            mathematical_eligible=scientific.mathematical_eligible,
            production_accepted=seal.production_accepted,
            observed_session_count=scientific.observed_session_count,
            observed_stream_count=scientific.observed_stream_count,
            sealed_at=record.sealed_at,
            pipeline_release_ids=tuple(sorted({item.pipeline_release_id for item in seal.members})),
            capture=QualificationDocumentRefV1(
                logical_uri=seal.capture.logical_uri, digest=seal.capture.digest
            ),
            outer_seal=QualificationDocumentRefV1(
                logical_uri=record.outer_seal_uri, digest=record.outer_seal_digest
            ),
            outer_sealed_utc_ns=seal.sealed_utc_ns,
            current_release_evidence_digest=seal.current_release_evidence_digest,
            strata=strata,
            calibrations=self._calibrations(record, scientific),
        )

    def _verify_members(
        self,
        record: ScientificCampaignRecord,
        seal: TrustedCampaignOuterSealV1,
        scientific: TrustedMatchedRecoveryCampaignReceiptV2,
    ) -> None:
        if len(record.streams) != 40 or len(seal.members) != 40:
            raise CampaignPresentationError("campaign membership is incomplete")
        scientific_streams = {
            (
                item.product.receipt.path_identity.session_id,
                item.product.receipt.path_identity.stream_id,
            ): item
            for item in scientific.streams
        }
        if len(scientific_streams) != 40:
            raise CampaignPresentationError("scientific campaign stream inventory is ambiguous")
        closure_product_ids: set[int] = set()
        closure_bytes = 0
        verified_runs: set[str] = set()
        capture_snapshots: dict[str, CatalogSessionReadSnapshot | None] = {}
        for registration, member in zip(record.streams, seal.members, strict=True):
            embedded = scientific_streams.get((member.session_id, member.stream_id))
            embedded_product = None if embedded is None else embedded.product
            identity = (
                None if embedded_product is None else embedded_product.receipt.path_identity
            )
            capture_snapshot = capture_snapshots.get(member.session_id)
            if capture_snapshot is None:
                capture_snapshot = self._catalog.presentation_snapshot(member.session_id)
                capture_snapshots[member.session_id] = capture_snapshot
            if (
                registration.ordinal != member.ordinal
                or registration.session_id != member.session_id
                or registration.stream_id != member.stream_id
                or registration.analysis_run_id != member.analysis_run_id
                or registration.analysis_run_uri != member.analysis_run_uri
                or registration.analysis_run_digest != member.analysis_run_digest
                or registration.pipeline_release_id != member.pipeline_release_id
                or registration.analysis_product_id != member.analysis_product_id
                or registration.frequency_calibration_id != member.frequency_calibration_id
                or capture_snapshot is None
                or registration.capture_uri != capture_snapshot.bundle_uri
                or registration.capture_digest != capture_snapshot.manifest_digest
                or registration.scientific_uri != member.analysis_product_uri
                or registration.scientific_digest != member.analysis_product_digest
                or registration.calibration_uri != member.calibration_uri
                or registration.calibration_digest != member.calibration_digest
                or embedded_product is None
                or identity is None
                or embedded_product.analysis_run_id != member.analysis_run_id
                or embedded_product.scope_key != member.stream_id
                or embedded_product.pipeline_release != member.pipeline_release_id
                or identity.session_id != member.session_id
                or identity.stream_id != member.stream_id
                or identity.manifest_digest != registration.capture_digest
                or embedded_product.receipt.legacy_execution.envelope_digest
                != member.legacy_envelope_digest
            ):
                raise CampaignPresentationError("campaign member differs from outer seal")
            if member.analysis_run_id not in verified_runs:
                manifest = self._catalog.run_manifest_reference(member.analysis_run_id)
                if (
                    manifest.logical_uri != member.analysis_run_uri
                    or manifest.digest != member.analysis_run_digest
                ):
                    raise CampaignPresentationError("campaign run manifest differs")
                self._artifacts.read_json(manifest.logical_uri, manifest.digest)
                verified_runs.add(member.analysis_run_id)
            closure = self._catalog.product_dependency_closure(member.analysis_product_id)
            sealed_closure = {
                item.analysis_product_id: item for item in member.product_dependency_closure
            }
            if set(sealed_closure) != {item.product_id for item in closure}:
                raise CampaignPresentationError("campaign product dependency closure differs")
            for catalog_product in closure:
                sealed = sealed_closure[catalog_product.product_id]
                if (
                    not catalog_product.available
                    or catalog_product.logical_uri != sealed.logical_uri
                    or catalog_product.digest != sealed.digest
                    or catalog_product.kind != sealed.kind
                    or catalog_product.schema_version != sealed.schema_version_of_product
                    or catalog_product.scope_key != sealed.scope_key
                ):
                    raise CampaignPresentationError("campaign dependency is unavailable or drifted")
                if catalog_product.product_id not in closure_product_ids:
                    closure_product_ids.add(catalog_product.product_id)
                    closure_bytes += catalog_product.byte_size
                    if (
                        len(closure_product_ids) > _MAX_CLOSURE_PRODUCTS
                        or closure_bytes > _MAX_CLOSURE_BYTES
                    ):
                        raise CampaignPresentationError(
                            "campaign dependency verification budget exceeded"
                        )
                document = self._artifacts.read_json(
                    catalog_product.logical_uri, catalog_product.digest
                )
                if catalog_product.product_id == member.analysis_product_id:
                    if TrustedMatchedRecoveryProductV2.model_validate(document) != embedded_product:
                        raise CampaignPresentationError(
                            "embedded scientific product differs from catalog artifact"
                        )
                elif catalog_product.kind == "starlink.native-known-pilot-evidence":
                    native = NativeKnownPilotEvidenceProductV2.model_validate(document)
                    if (
                        native.product_digest
                        != embedded_product.receipt.native_evidence_product_digest
                        or native.analysis_run_id != embedded_product.analysis_run_id
                        or native.scope_key != embedded_product.scope_key
                        or native.release != embedded_product.receipt.native_release
                        or native.path_identity != embedded_product.receipt.path_identity
                        or native.calibration != embedded_product.receipt.calibration
                        or native.execution != embedded_product.receipt.native_execution
                    ):
                        raise CampaignPresentationError(
                            "native dependency differs from embedded scientific evidence"
                        )

    def _calibrations(
        self,
        record: ScientificCampaignRecord,
        scientific: TrustedMatchedRecoveryCampaignReceiptV2,
    ) -> tuple[QualificationCalibrationV1, ...]:
        counts: Counter[int] = Counter(item.frequency_calibration_id for item in record.streams)
        sessions: dict[int, set[str]] = defaultdict(set)
        for item in record.streams:
            sessions[item.frequency_calibration_id].add(item.session_id)
        scientific_calibrations = {
            (
                item.product.receipt.path_identity.session_id,
                item.product.receipt.path_identity.stream_id,
            ): item.product.receipt.calibration
            for item in scientific.streams
        }
        registrations = {}
        for item in record.streams:
            registration = self._catalog.frequency_calibration(
                item.frequency_calibration_id
            ).registration
            contract = scientific_calibrations.get((item.session_id, item.stream_id))
            if contract is None or (
                registration.calibration_id != contract.calibration_id
                or registration.calibration_digest != contract.calibration_digest
                or registration.radio_id != contract.radio_id
                or registration.radio_serial != contract.radio_serial
                or registration.receiver_id != contract.receiver_id
                or registration.physical_receiver_id != contract.physical_receiver_id
                or registration.hardware_epoch_id != contract.hardware_epoch_id
                or registration.center_hz != contract.center_hz
                or registration.uncertainty_lower_hz != contract.uncertainty_lower_hz
                or registration.uncertainty_upper_hz != contract.uncertainty_upper_hz
                or registration.valid_from_utc_ns != contract.valid_from_utc_ns
                or registration.valid_until_utc_ns != contract.valid_until_utc_ns
                or registration.method != contract.method
                or registration.evidence_uri != item.calibration_uri
                or registration.evidence_digest != item.calibration_digest
            ):
                raise CampaignPresentationError("campaign calibration evidence differs")
            registrations[item.frequency_calibration_id] = registration
        values = []
        for calibration_id in sorted(counts):
            registration = registrations[calibration_id]
            values.append(
                QualificationCalibrationV1(
                    frequency_calibration_id=calibration_id,
                    calibration_id=registration.calibration_id,
                    radio_id=registration.radio_id,
                    radio_serial=registration.radio_serial,
                    receiver_id=registration.receiver_id,
                    physical_receiver_id=registration.physical_receiver_id,
                    hardware_epoch_id=registration.hardware_epoch_id,
                    center_hz=registration.center_hz,
                    uncertainty_lower_hz=registration.uncertainty_lower_hz,
                    uncertainty_upper_hz=registration.uncertainty_upper_hz,
                    valid_from_utc_ns=registration.valid_from_utc_ns,
                    valid_until_utc_ns=registration.valid_until_utc_ns,
                    method=registration.method,
                    evidence_uri=registration.evidence_uri,
                    evidence_digest=registration.evidence_digest,
                    session_count=len(sessions[calibration_id]),
                    stream_count=counts[calibration_id],
                )
            )
        return tuple(values)

    def _read_document(
        self, campaign_id: str, filename: str, *, read_budget: list[int] | None
    ) -> bytes:
        try:
            directory = self._campaigns.child(campaign_id)
        except ValueError as error:
            raise CampaignPresentationError("campaign directory is absent or symlinked") from error
        try:
            descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory.fileno())
            try:
                info = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or stat.S_IMODE(info.st_mode) != 0o440
                    or info.st_nlink != 1
                    or info.st_size > _LIMITS[filename]
                ):
                    raise CampaignPresentationError("campaign document is invalid or oversized")
                if read_budget is not None:
                    read_budget[0] += info.st_size
                    if read_budget[0] > _MAX_LIST_DOCUMENT_BYTES:
                        raise CampaignPresentationError(
                            "campaign list document verification budget exceeded"
                        )
                chunks: list[bytes] = []
                remaining = info.st_size
                while remaining:
                    chunk = os.read(descriptor, min(remaining, 1024 * 1024))
                    if not chunk:
                        raise CampaignPresentationError("campaign document was truncated")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                after = os.fstat(descriptor)
                if (
                    after.st_dev != info.st_dev
                    or after.st_ino != info.st_ino
                    or after.st_size != info.st_size
                    or after.st_mtime_ns != info.st_mtime_ns
                ):
                    raise CampaignPresentationError("campaign document changed while reading")
                return b"".join(chunks)
            finally:
                os.close(descriptor)
        except OSError as error:
            raise CampaignPresentationError("campaign document cannot be read") from error
        finally:
            directory.close()
