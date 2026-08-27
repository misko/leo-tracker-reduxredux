"""Concrete authority composition for selected WP11 matched-recovery V2 runs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from leo.analysis.starlink.acceptance import (
    NATIVE_KNOWN_PILOT_EVIDENCE_STAGE,
    NativeEvidenceScopeBinding,
    NativeKnownPilotEvidenceAnalyzer,
)
from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
from leo.application.frequency_calibration import NativeReleaseCalibrationEvidenceAdapter
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, PromotionPolicy
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1, ReceiverPathIdentityV1
from leo.contracts.recording import RecordingManifestV4
from leo.contracts.scientific import (
    LegacyExecutionEnvelopeV1,
    MatchedPilotAcceptanceConfigV1,
    NativeKnownPilotEvidenceProductV2,
    TrustedNativeReleaseEvidenceV2,
)
from leo.contracts.states import SourceType, StreamState
from leo.pipeline import AnalysisContext, AnalyzerRegistry, IqReader
from leo.processing import RecordingIqReaderProvider
from leo.qualification.frequency_calibration import (
    PROFILE_DIGEST,
    PROFILE_NAME,
    SAMPLE_COUNT,
    SAMPLE_RATE_HZ,
    frozen_topology_for_radio,
)
from leo.qualification.legacy_oracle import LegacyOracleReceiptV1
from leo.qualification.native_execution import ReleaseLocalNativeEvidenceExecutor
from leo.qualification.scientific_campaign import SealedLegacyReferenceDecisionPort
from leo.qualification.trusted_matched_recovery_stage import (
    TRUSTED_MATCHED_RECOVERY_STAGE,
    TrustedMatchedRecoveryAnalyzer,
    TrustedMatchedRecoveryBinding,
)
from leo.storage import PinnedLocalRoot, PublishedBundle, RecordingIqReader, RecordingStore

WP11_TRUSTED_MATCHED_STAGE_KEYS = (
    NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key,
    TRUSTED_MATCHED_RECOVERY_STAGE.key,
)
_SAFE_RECEIPT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_QNAP_ROOT = Path("/mnt/qnap01")


@dataclass(frozen=True, slots=True)
class WP11TrustedMatchedComposition:
    """Selected-only, content-evidence processing components on one pinned root."""

    registry: AnalyzerRegistry
    iq_readers: RecordingIqReaderProvider
    artifacts: AnalysisArtifactStore
    stage_keys: tuple[str, ...] = WP11_TRUSTED_MATCHED_STAGE_KEYS


class PinnedLegacyOracleAuthority:
    """Load one sealed receipt through an owned, retained local directory FD."""

    def __init__(self, evidence_root: Path) -> None:
        supplied = PinnedLocalRoot(evidence_root)
        self._root = supplied.clone()
        supplied.close()

    def close(self) -> None:
        self._root.close()

    def resolve(
        self,
        *,
        receipt_name: str,
        detector_binding,
        identity: ReceiverPathIdentityV1,
        calibration: ReceiverFrequencyCalibrationV1,
        iq_digest: str,
    ) -> LegacyExecutionEnvelopeV1:
        identity = ReceiverPathIdentityV1.model_validate(identity.model_dump(mode="json"))
        calibration = ReceiverFrequencyCalibrationV1.model_validate(
            calibration.model_dump(mode="json")
        )
        if not _SAFE_RECEIPT.fullmatch(receipt_name):
            raise ValueError("legacy oracle receipt name is not one safe leaf")
        self._root.assert_open()
        descriptor = os.open(
            receipt_name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=self._root.fileno(),
        )
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o440
                or info.st_nlink != 1
                or info.st_size <= 0
                or info.st_size > _MAX_RECEIPT_BYTES
            ):
                raise ValueError("legacy oracle receipt lacks immutable publication semantics")
            payload = _read_bounded(descriptor, info.st_size)
        finally:
            os.close(descriptor)
        receipt = LegacyOracleReceiptV1.model_validate(json.loads(payload))
        if receipt.iq_sha256 != iq_digest:
            raise ValueError("legacy oracle receipt is bound to different IQ content")
        return SealedLegacyReferenceDecisionPort(
            receipt,
            detector_binding=detector_binding,
        ).execution_envelope(
            path_identity=identity,
            calibration=calibration,
            input_manifest_digest=identity.manifest_digest,
        )


class PostgresAuthoritativeCalibrationScope:
    """Resolve a manifest-derived receiver identity through durable PG calibration truth."""

    def __init__(
        self,
        repository: CatalogRepository,
        recordings: RecordingStore,
        calibrations: PostgresCalibrationCatalogAdapter,
    ) -> None:
        if type(repository) is not CatalogRepository:
            raise TypeError("trusted matched scope requires the concrete PostgreSQL catalog")
        if type(recordings) is not RecordingStore:
            raise TypeError("trusted matched scope requires the concrete recording store")
        if recordings.pinned_root_identity is None:
            raise ValueError("trusted matched scope requires a pinned recording store")
        if type(calibrations) is not PostgresCalibrationCatalogAdapter:
            raise TypeError("trusted matched scope requires the authoritative calibration adapter")
        self._repository = repository
        self._recordings = recordings
        self._calibrations = calibrations

    @property
    def recordings(self) -> RecordingStore:
        return self._recordings

    def resolve(self, context: AnalysisContext, iq: IqReader) -> NativeEvidenceScopeBinding:
        execution = self._repository.run_execution_info(context.run_id)
        if (
            execution.session_id != context.session_id
            or execution.pipeline_release_id != context.pipeline_release
            or execution.promotion_policy != PromotionPolicy.EVIDENCE_ONLY.value
        ):
            raise ValueError("native evidence run is not exact evidence-only catalog lineage")
        bundle = self._recordings.inspect_uri(execution.bundle_uri)
        if (
            bundle.session_id != context.session_id
            or bundle.manifest_sha256 != execution.input_manifest_digest
        ):
            raise ValueError("recording bundle differs from native run manifest lineage")
        self._recordings.verify(bundle)
        return self._resolve_verified_recording(
            session_id=context.session_id,
            stream_id=context.scope_key,
            bundle=bundle,
            iq=iq,
        )

    def resolve_recording(
        self,
        session_id: str,
        stream_id: str,
    ) -> tuple[NativeEvidenceScopeBinding, RecordingIqReader, str]:
        """Resolve accepted IQ/calibration before WP11 jobs can be queued."""

        snapshot = self._repository.presentation_snapshot(session_id)
        if snapshot is None or snapshot.bundle_uri is None or snapshot.manifest_digest is None:
            raise ValueError("WP11 recording is absent from the authoritative catalog")
        bundle = self._recordings.inspect_uri(snapshot.bundle_uri)
        if bundle.session_id != session_id or bundle.manifest_sha256 != snapshot.manifest_digest:
            raise ValueError("catalog and recording bundle lineage disagree")
        self._recordings.verify(bundle)
        reader = self._recordings.reader(bundle, stream_id, verify=True)
        binding = self._resolve_verified_recording(
            session_id=session_id,
            stream_id=stream_id,
            bundle=bundle,
            iq=reader,
        )
        return binding, reader, snapshot.bundle_uri

    def _resolve_verified_recording(
        self,
        *,
        session_id: str,
        stream_id: str,
        bundle: PublishedBundle,
        iq: IqReader,
    ) -> NativeEvidenceScopeBinding:
        streams = tuple(item for item in bundle.manifest.streams if item.stream_id == stream_id)
        if len(streams) != 1:
            raise ValueError("native evidence scope is absent or ambiguous in recording manifest")
        stream = streams[0]
        if isinstance(bundle.manifest, RecordingManifestV4):
            raise ValueError("trusted recovery does not accept mixed-rate manifests")
        if (
            type(iq) is not RecordingIqReader
            or iq.session_id != bundle.session_id
            or iq.stream_id != stream_id
            or iq.manifest_digest != bundle.manifest_sha256
            or not iq.verifies_digests
        ):
            raise ValueError("native evidence IQ reader is not the exact verified recording scope")
        profile = bundle.manifest.capture_plan.profile_revision
        settings = stream.applied_settings
        if (
            bundle.manifest.source_type is not SourceType.LIVE
            or "ACCEPTANCE" not in bundle.manifest.tags
            or "CALIBRATION" in bundle.manifest.tags
            or profile.revision_digest != PROFILE_DIGEST
            or profile.profile.name != PROFILE_NAME
            or stream.state is not StreamState.COMPLETE
            or settings is None
            or settings.sample_rate_hz != SAMPLE_RATE_HZ
            or settings.receiver_ids != (1,)
            or stream.captured_sample_count != SAMPLE_COUNT
            or stream.timing is None
            or iq.sample_rate_hz != SAMPLE_RATE_HZ
            or iq.sample_count != SAMPLE_COUNT
            or iq.receiver_ids != (1,)
        ):
            raise ValueError("native evidence recording differs from frozen WP11 acceptance mode")
        serial, physical, epoch, _topology = frozen_topology_for_radio(stream.radio.radio_id)
        if stream.radio.serial != serial:
            raise ValueError("recording radio serial differs from frozen station topology")
        sample_ns = math.ceil(1_000_000_000 / SAMPLE_RATE_HZ)
        identity = ReceiverPathIdentityV1(
            radio_id=stream.radio.radio_id,
            radio_serial=serial,
            receiver_id=1,
            physical_receiver_id=physical,
            capture_utc_ns=stream.timing.first_sample.estimate_utc_ns,
            capture_end_utc_ns=stream.timing.last_sample.estimate_utc_ns + sample_ns,
            hardware_epoch_id=epoch,
            session_id=session_id,
            stream_id=stream_id,
            manifest_digest=bundle.manifest_sha256,
            profile_revision_digest=profile.revision_digest,
        )
        calibration = self._calibrations.resolve(identity).calibration
        return NativeEvidenceScopeBinding(
            input_manifest_digest=bundle.manifest_sha256,
            path_identity=identity,
            calibration=calibration,
        )


class CurrentNativeReleaseProvider:
    def __init__(self, releases: NativeReleaseCalibrationEvidenceAdapter) -> None:
        if type(releases) is not NativeReleaseCalibrationEvidenceAdapter:
            raise TypeError("native V2 selected stage requires deployed release validation")
        self._releases = releases

    def resolve(self, context: AnalysisContext) -> TrustedNativeReleaseEvidenceV2:
        release = self._releases.current_release().native_release
        if release.pipeline_release != context.pipeline_release:
            raise ValueError("current deployed release differs from analysis run")
        return release


class AuthoritativeMatchedRecoveryBindingProvider:
    def __init__(
        self,
        *,
        config: MatchedPilotAcceptanceConfigV1,
        scopes: PostgresAuthoritativeCalibrationScope,
        legacy: PinnedLegacyOracleAuthority,
        receipt_names: dict[tuple[str, str], str],
    ) -> None:
        if type(scopes) is not PostgresAuthoritativeCalibrationScope:
            raise TypeError("matched V2 selected stage requires concrete calibration scope")
        if type(legacy) is not PinnedLegacyOracleAuthority:
            raise TypeError("matched V2 selected stage requires pinned legacy authority")
        if not receipt_names or any(
            not _SAFE_RECEIPT.fullmatch(name) for name in receipt_names.values()
        ):
            raise ValueError("matched V2 receipt inventory must contain safe sealed leaf names")
        self._config = config
        self._scopes = scopes
        self._legacy = legacy
        self._receipt_names = dict(receipt_names)

    def resolve(
        self,
        context: AnalysisContext,
        iq: IqReader,
        native: NativeKnownPilotEvidenceProductV2,
    ) -> TrustedMatchedRecoveryBinding:
        scope = self._scopes.resolve(context, iq)
        if (
            native.path_identity != scope.path_identity
            or native.calibration != scope.calibration
            or native.execution.input_manifest_digest != scope.input_manifest_digest
        ):
            raise ValueError("native evidence differs from authoritative recording/calibration")
        binding = self._config.detector_binding
        if (
            native.release.source_revision != binding.native_source_revision
            or native.release.source_tree_digest != binding.native_source_tree_digest
            or native.release.release_metadata_digest != binding.native_release_manifest_digest
            or native.execution.template_digest != binding.native_template_digest
            or native.execution.acquisition_configuration_digest
            != binding.native_acquisition_configuration_digest
            or native.execution.qam_configuration_digest != binding.native_qam_configuration_digest
        ):
            raise ValueError("native evidence differs from frozen detector binding")
        try:
            receipt_name = self._receipt_names[(context.session_id, context.scope_key)]
        except KeyError as error:
            raise ValueError("legacy receipt is not prebound to this run scope") from error
        legacy = self._legacy.resolve(
            receipt_name=receipt_name,
            detector_binding=binding,
            identity=scope.path_identity,
            calibration=scope.calibration,
            iq_digest=_receiver_iq_digest(iq, receiver_id=1),
        )
        return TrustedMatchedRecoveryBinding(
            config=self._config,
            path_identity=scope.path_identity,
            calibration=scope.calibration,
            legacy_execution=legacy,
        )


def wp11_trusted_matched_registry(
    *,
    config: MatchedPilotAcceptanceConfigV1,
    scopes: PostgresAuthoritativeCalibrationScope,
    legacy: PinnedLegacyOracleAuthority,
    receipt_names: dict[tuple[str, str], str],
    releases: NativeReleaseCalibrationEvidenceAdapter,
    executor: ReleaseLocalNativeEvidenceExecutor,
    recordings: RecordingStore,
    artifacts: AnalysisArtifactStore,
) -> WP11TrustedMatchedComposition:
    """Build the explicit selected-only DAG on one retained local storage inode."""

    if type(recordings) is not RecordingStore or type(artifacts) is not AnalysisArtifactStore:
        raise TypeError("trusted matched composition requires concrete storage adapters")
    if _is_qnap_lexically(recordings.root) or _is_qnap_lexically(artifacts.root):
        raise ValueError("trusted matched composition cannot use QNAP storage")
    recording_identity = recordings.pinned_root_identity
    artifact_identity = artifacts.pinned_root_identity
    if recording_identity is None or artifact_identity is None:
        raise ValueError("trusted matched composition requires pinned storage adapters")
    if recording_identity != artifact_identity or scopes.recordings is not recordings:
        raise ValueError("trusted matched composition storage authorities do not match")
    if type(executor) is not ReleaseLocalNativeEvidenceExecutor:
        raise TypeError("native V2 selected stage requires release-local execution")
    native = NativeKnownPilotEvidenceAnalyzer(
        config=config,
        scopes=scopes,
        releases=CurrentNativeReleaseProvider(releases),
        executor=executor,
    )
    matched = TrustedMatchedRecoveryAnalyzer(
        AuthoritativeMatchedRecoveryBindingProvider(
            config=config,
            scopes=scopes,
            legacy=legacy,
            receipt_names=receipt_names,
        )
    )
    return WP11TrustedMatchedComposition(
        registry=AnalyzerRegistry((native, matched)),
        iq_readers=RecordingIqReaderProvider(recordings, verify=True),
        artifacts=artifacts,
    )


def _is_qnap_lexically(path: Path) -> bool:
    lexical = os.path.normpath(os.fspath(path))
    if lexical.startswith("//"):
        lexical = "/" + lexical.lstrip("/")
    normalized = Path(lexical)
    return normalized == _QNAP_ROOT or _QNAP_ROOT in normalized.parents


def _receiver_iq_digest(iq: IqReader, *, receiver_id: int) -> str:
    try:
        receiver_index = iq.receiver_ids.index(receiver_id)
    except ValueError as error:
        raise ValueError("legacy IQ receiver is absent from analysis scope") from error
    digest = hashlib.sha256()
    expected = 0
    for block in iq.iter_blocks(block_samples=1_000_000):
        if block.metadata.session_sample_start != expected:
            raise ValueError("legacy IQ digest cannot be formed across a discontinuity")
        selected = np.ascontiguousarray(block.samples[:, receiver_index, :], dtype="<i2")
        digest.update(selected.tobytes(order="C"))
        expected += block.metadata.sample_count
    if expected != SAMPLE_COUNT:
        raise ValueError("legacy IQ digest did not cover the exact 60-second dwell")
    return f"sha256:{digest.hexdigest()}"


def _read_bounded(descriptor: int, size: int) -> bytes:
    payload = bytearray()
    while len(payload) < size:
        block = os.read(descriptor, min(1024 * 1024, size - len(payload)))
        if not block:
            break
        payload.extend(block)
    if len(payload) != size:
        raise ValueError("legacy oracle receipt changed during read")
    return bytes(payload)
