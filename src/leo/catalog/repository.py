"""Transactional PostgreSQL catalog operations.

Every public mutation owns one short transaction. Processing work happens
outside these methods while a worker holds a renewable lease.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    BigInteger,
    Select,
    and_,
    case,
    exists,
    func,
    literal,
    select,
    text,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, sessionmaker

from leo.catalog.errors import (
    ActiveRunExistsError,
    CatalogNotFoundError,
    IdenticalRunExistsError,
    InvalidStateError,
    LeaseLostError,
    ProductConflictError,
    PromotionError,
)
from leo.catalog.models import (
    AcquisitionOperation,
    AnalysisProduct,
    AnalysisRun,
    AnalysisScope,
    AnalysisSummary,
    CapturePathAuthority,
    CaptureProfile,
    CaptureProfileRevision,
    CaptureReceiverLineage,
    CaptureSession,
    CurrentAnalysis,
    CurrentPipelineAnalysis,
    FrequencyCalibration,
    FrequencyCalibrationSet,
    FrequencyCalibrationSetMember,
    HardwareEpoch,
    PipelineRelease,
    ProcessingFenceEvent,
    ProcessingJob,
    ProcessingJobAttempt,
    ProcessingJobDependency,
    ProcessingResourceCapacity,
    ProductDependency,
    Radio,
    RadioStream,
    RawIntegrityAttestation,
    ReceiverPath,
    RecordingChunk,
    RetentionEvent,
    RetentionHold,
    RunSubjectBinding,
    ScientificCampaign,
    ScientificCampaignStream,
    SessionTag,
    StageDerivation,
    StageDerivationOutput,
    StationReceiverAssignment,
    StationTopology,
    Tag,
    WorkerIncompatibilityEvent,
)
from leo.catalog.states import (
    AnalysisRunState,
    AttemptState,
    JobState,
    PromotionPolicy,
    SessionState,
)
from leo.catalog.types import (
    AcquisitionOperationLease,
    AcquisitionOperationRecord,
    ActiveJobRecord,
    CapturePathAuthorityRecord,
    CaptureReceiverBinding,
    CaptureRecordingIdentity,
    CatalogBacklogSnapshot,
    CatalogJobRecord,
    CatalogProductPurgeClaim,
    CatalogProductRecord,
    CatalogRetentionCandidate,
    CatalogRunReadSnapshot,
    CatalogSessionPurgeClaim,
    CatalogSessionReadSnapshot,
    CurrentSummary,
    FrequencyCalibrationRecord,
    FrequencyCalibrationRegistration,
    FrequencyCalibrationResolution,
    FrequencyCalibrationSetRecord,
    FrequencyCalibrationSetRegistration,
    JobDefinition,
    JobLease,
    PipelineReleaseSnapshot,
    ProcessingFenceResult,
    ProductRegistration,
    RadioStreamRegistration,
    RawIntegrityAttestationRegistration,
    ReceiverPathRecord,
    ReceiverPathRegistration,
    RecordingListPage,
    RecordingListRow,
    RunExecutionInfo,
    RunManifestReference,
    RunSealSnapshot,
    RunSubjectBindingRecord,
    RunSubjectBindingRegistration,
    ScientificCampaignRecord,
    ScientificCampaignRegistration,
    ScientificCampaignSeal,
    ScientificCampaignStreamRegistration,
    SessionSearch,
    SessionSearchResult,
    StageDerivationOutputRecord,
    StageDerivationOutputRegistration,
    StageDerivationRegistration,
    StageResultCommit,
    StationTopologyRecord,
    WorkerReleaseAuthority,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import PipelineLane
from leo.contracts.recording import (
    RecordingManifestV1,
    RecordingManifestV2,
    RecordingManifestV3,
    RecordingManifestV4,
    RecordingManifestV5,
    RecordingManifestV6,
    RecordingStreamV2,
    RecordingStreamV3,
)
from leo.contracts.standard_pipeline import (
    FrequencyReference,
    ReceiverFrequencyReferenceV1,
    StandardPairInputBindV2,
    StandardPathInputBindV3,
    StandardPathInputBindV4,
    StandardPathInputBindV5,
    resolve_manifest_starlink_tuning,
)
from leo.pipeline import ScopeIdentityV1, StageDerivationKeyV1
from leo.pipeline.planning import RawIntegrityAttestationV1
from leo.station.authority import (
    CaptureHardwareBindingV1,
    CaptureHardwareBindingV2,
    CaptureHardwareBindingV3,
    CaptureHardwareBindingV4,
    CaptureHardwareBindingV5,
    CaptureHardwareBindingV6,
    FixturePathAuthorityV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
    parse_capture_hardware_binding,
)

_ZERO_DIGEST = "sha256:" + "0" * 64
_ACQUISITION_CADENCE_KINDS = frozenset({"scheduled_recording", "scanner_sweep"})
_ACQUISITION_CADENCE_LOCK_KEY = "acquisition-cadence-coalescing-v1"
type StationCaptureHardwareBinding = (
    CaptureHardwareBindingV1
    | CaptureHardwareBindingV2
    | CaptureHardwareBindingV3
    | CaptureHardwareBindingV4
    | CaptureHardwareBindingV5
    | CaptureHardwareBindingV6
)
type CapturePathAuthorityContract = StationCaptureHardwareBinding | FixturePathAuthorityV1


class CatalogRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def dispose_inherited_connections_after_fork(self) -> None:
        """Drop copied pool state before an isolated analyzer reads products."""

        bind = self._sessions.kw.get("bind")
        if bind is None:
            raise RuntimeError("catalog session factory has no database engine")
        bind.dispose(close=False)

    def enqueue_acquisition_operation(
        self,
        *,
        operation_key: str,
        kind: str,
        payload: dict[str, Any],
        scheduled_for: datetime,
        available_at: datetime | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        coalesce_pending_kind: bool = False,
    ) -> AcquisitionOperationRecord:
        """Persist one idempotent radio-owning intent.

        A repeated cadence tick is a read of the original immutable intent, not
        a second operation. Conflicting reuse of a key fails closed.
        """

        if not operation_key or len(operation_key) > 160:
            raise ValueError("acquisition operation key must contain 1..160 characters")
        allowed = {
            "scheduled_recording",
            "scanner_sweep",
            "operator_once",
            "qualification",
            "soak",
            "radio_probe",
        }
        if kind not in allowed:
            raise ValueError("unsupported acquisition operation kind")
        if max_attempts <= 0:
            raise ValueError("acquisition maximum attempts must be positive")
        if coalesce_pending_kind and kind not in _ACQUISITION_CADENCE_KINDS:
            raise ValueError("only scheduled dwell and scanner intents may be coalesced")
        due = _require_aware(scheduled_for)
        ready = due if available_at is None else _require_aware(available_at)
        with self._sessions.begin() as session:
            insert_values: dict[str, Any] = {
                "operation_key": operation_key,
                "kind": kind,
                "payload": payload,
                "scheduled_for": due,
                "available_at": ready,
                "priority": priority,
                "max_attempts": max_attempts,
            }
            if coalesce_pending_kind:
                _lock_acquisition_cadence(session)
                existing = session.scalar(
                    select(AcquisitionOperation)
                    .where(AcquisitionOperation.operation_key == operation_key)
                    .with_for_update()
                )
                pending = session.scalar(
                    select(AcquisitionOperation)
                    .where(
                        AcquisitionOperation.kind == kind,
                        AcquisitionOperation.state == "pending",
                        AcquisitionOperation.operation_key != operation_key,
                    )
                    .order_by(
                        AcquisitionOperation.scheduled_for.desc(),
                        AcquisitionOperation.id.desc(),
                    )
                    .with_for_update()
                )
                if existing is None and pending is not None:
                    now = _database_now(session)
                    incoming_rank = (due, operation_key)
                    pending_rank = (pending.scheduled_for, pending.operation_key)
                    if incoming_rank > pending_rank:
                        pending.state = "cancelled"
                        pending.outcome = f"superseded by newer {kind} intent {operation_key}"
                        pending.error = None
                        pending.completed_at = now
                        pending.updated_at = now
                    else:
                        insert_values.update(
                            state="cancelled",
                            outcome=(f"superseded by newer {kind} intent {pending.operation_key}"),
                            completed_at=now,
                            updated_at=now,
                        )
                elif existing is None and pending is None:
                    pass
                elif existing is not None and pending is not None:
                    # An idempotent retry of an older slot must not alter the
                    # one newer pending cadence intent.
                    existing_rank = (existing.scheduled_for, existing.operation_key)
                    pending_rank = (pending.scheduled_for, pending.operation_key)
                    if existing.state == "pending" and existing_rank > pending_rank:
                        now = _database_now(session)
                        pending.state = "cancelled"
                        pending.outcome = f"superseded by newer {kind} intent {operation_key}"
                        pending.error = None
                        pending.completed_at = now
                        pending.updated_at = now
                session.flush()
            statement = (
                insert(AcquisitionOperation)
                .values(**insert_values)
                .on_conflict_do_nothing(index_elements=[AcquisitionOperation.operation_key])
                .returning(AcquisitionOperation.id)
            )
            operation_id = session.scalar(statement)
            operation = (
                session.get(AcquisitionOperation, operation_id)
                if operation_id is not None
                else session.scalar(
                    select(AcquisitionOperation).where(
                        AcquisitionOperation.operation_key == operation_key
                    )
                )
            )
            assert operation is not None
            if (
                operation.kind != kind
                or operation.payload != payload
                or operation.scheduled_for != due
                or operation.priority != priority
                or operation.max_attempts != max_attempts
            ):
                raise InvalidStateError(
                    "acquisition operation key was reused with different intent"
                )
            return _acquisition_operation_record(operation)

    def active_acquisition_operations(
        self, *, limit: int = 200
    ) -> tuple[AcquisitionOperationRecord, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("active acquisition operation limit must be in [1, 200]")
        with self._sessions() as session:
            operations = session.scalars(
                select(AcquisitionOperation)
                .where(AcquisitionOperation.state.in_(("pending", "leased")))
                .order_by(
                    case((AcquisitionOperation.state == "leased", 0), else_=1),
                    AcquisitionOperation.scheduled_for,
                    AcquisitionOperation.priority.desc(),
                    AcquisitionOperation.id,
                )
                .limit(limit)
            )
            return tuple(_acquisition_operation_record(item) for item in operations)

    def active_acquisition_operation_count(self) -> int:
        with self._sessions() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(AcquisitionOperation)
                    .where(AcquisitionOperation.state.in_(("pending", "leased")))
                )
                or 0
            )

    def claim_acquisition_operation(
        self, *, worker_id: str, lease_for: timedelta
    ) -> AcquisitionOperationLease | None:
        """Claim exactly one operation under a database-wide radio-owner mutex."""

        _require_positive_duration(lease_for)
        if not worker_id or len(worker_id) > 128:
            raise ValueError("acquisition worker ID must contain 1..128 characters")
        with self._sessions.begin() as session:
            now = _database_now(session)
            # Claims and reclaim use the same transaction mutex. The partial
            # unique index remains a database invariant if this code regresses.
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": "acquisition-global-radio-owner-v1"},
            )
            active = session.scalar(
                select(func.count())
                .select_from(AcquisitionOperation)
                .where(
                    AcquisitionOperation.state == "leased",
                    AcquisitionOperation.lease_expires_at > now,
                )
            )
            if int(active or 0) != 0:
                return None
            operation = session.scalar(
                select(AcquisitionOperation)
                .where(
                    AcquisitionOperation.state == "pending",
                    AcquisitionOperation.available_at <= now,
                )
                .order_by(
                    AcquisitionOperation.scheduled_for,
                    AcquisitionOperation.priority.desc(),
                    AcquisitionOperation.id,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if operation is None:
                return None
            expires_at = now + lease_for
            operation.state = "leased"
            operation.attempt_count += 1
            operation.lease_owner = worker_id
            operation.lease_expires_at = expires_at
            operation.heartbeat_at = now
            operation.started_at = operation.started_at or now
            operation.updated_at = now
            return AcquisitionOperationLease(
                operation_id=operation.id,
                operation_key=operation.operation_key,
                kind=operation.kind,
                payload=operation.payload,
                scheduled_for=operation.scheduled_for,
                attempt_number=operation.attempt_count,
                worker_id=worker_id,
                lease_expires_at=expires_at,
            )

    def heartbeat_acquisition_operation(
        self, *, operation_id: int, worker_id: str, lease_for: timedelta
    ) -> datetime:
        _require_positive_duration(lease_for)
        with self._sessions.begin() as session:
            now = _database_now(session)
            operation = _locked_acquisition_operation(session, operation_id)
            _require_live_acquisition_lease(operation, worker_id, now)
            expires_at = now + lease_for
            operation.heartbeat_at = now
            operation.lease_expires_at = expires_at
            operation.updated_at = now
            return expires_at

    def complete_acquisition_operation(
        self, *, operation_id: int, worker_id: str, outcome: str
    ) -> None:
        with self._sessions.begin() as session:
            now = _database_now(session)
            operation = _locked_acquisition_operation(session, operation_id)
            _require_live_acquisition_lease(operation, worker_id, now)
            operation.state = "succeeded"
            operation.outcome = outcome
            operation.error = None
            operation.completed_at = now
            _clear_acquisition_lease(operation)
            operation.updated_at = now

    def fail_acquisition_operation(
        self,
        *,
        operation_id: int,
        worker_id: str,
        error: str,
        retryable: bool = True,
        retry_after: timedelta = timedelta(0),
    ) -> str:
        if retry_after < timedelta(0):
            raise ValueError("acquisition retry delay cannot be negative")
        with self._sessions.begin() as session:
            now = _database_now(session)
            _lock_acquisition_cadence(session)
            operation = _locked_acquisition_operation(session, operation_id)
            _require_live_acquisition_lease(operation, worker_id, now)
            if retryable and operation.attempt_count < operation.max_attempts:
                return _requeue_acquisition_operation(
                    session,
                    operation,
                    now=now,
                    available_at=now + retry_after,
                    error=error,
                )
            else:
                operation.error = error
                _clear_acquisition_lease(operation)
                operation.state = "failed"
                operation.completed_at = now
            operation.updated_at = now
            return operation.state

    def reclaim_expired_acquisition_operations(
        self, *, as_of: datetime | None = None
    ) -> tuple[int, ...]:
        with self._sessions.begin() as session:
            now = _database_now(session)
            cutoff = now if as_of is None else _require_aware(as_of)
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": "acquisition-global-radio-owner-v1"},
            )
            # An expired cadence lease can coexist with one pending successor.
            # Serialize with cadence enqueue before either row changes state so
            # the partial unique pending-kind index remains an invariant.
            _lock_acquisition_cadence(session)
            operations = session.scalars(
                select(AcquisitionOperation)
                .where(
                    AcquisitionOperation.state == "leased",
                    AcquisitionOperation.lease_expires_at <= cutoff,
                )
                .order_by(AcquisitionOperation.id)
                .with_for_update(skip_locked=True)
            )
            reclaimed: list[int] = []
            for operation in operations:
                if operation.attempt_count >= operation.max_attempts:
                    _clear_acquisition_lease(operation)
                    operation.state = "failed"
                    operation.error = "maximum attempts exhausted after lease expiry"
                    operation.completed_at = now
                    operation.updated_at = now
                else:
                    _requeue_acquisition_operation(
                        session,
                        operation,
                        now=now,
                        available_at=now,
                        error="previous lease expired; operation recovered",
                    )
                reclaimed.append(operation.id)
            return tuple(reclaimed)

    def create_capture_session(
        self,
        *,
        session_id: str,
        source_type: str,
        state: str,
        bundle_uri: str | None,
        manifest_digest: str | None,
        profile_revision_id: int | None = None,
        attributes: dict[str, Any] | None = None,
        tags: Iterable[str] = (),
        allocated_bytes: int = 0,
        observed_start_at: datetime | None = None,
        observed_end_at: datetime | None = None,
    ) -> None:
        if allocated_bytes < 0:
            raise ValueError("allocated_bytes cannot be negative")
        canonical_tags = tuple(sorted(set(tags)))
        with self._sessions.begin() as session:
            capture = CaptureSession(
                id=session_id,
                source_type=source_type,
                state=state,
                bundle_uri=bundle_uri,
                manifest_digest=manifest_digest,
                profile_revision_id=profile_revision_id,
                attributes={} if attributes is None else attributes,
                allocated_bytes=allocated_bytes,
                raw_available=state != SessionState.PURGED.value,
                observed_start_at=observed_start_at,
                observed_end_at=observed_end_at,
            )
            session.add(capture)
            session.flush()
            for tag_name in canonical_tags:
                session.execute(
                    insert(Tag)
                    .values(name=tag_name)
                    .on_conflict_do_nothing(index_elements=[Tag.name])
                )
                session.add(SessionTag(session_id=session_id, tag_name=tag_name))
            if source_type == "test":
                session.add(
                    RetentionHold(
                        session_id=session_id,
                        reason="automatic TEST corpus hold",
                        created_by="system",
                    )
                )

    def capture_recording_identity(self, session_id: str) -> CaptureRecordingIdentity:
        with self._sessions() as session:
            capture = session.get(CaptureSession, session_id)
            if capture is None:
                raise CatalogNotFoundError(f"capture session is absent: {session_id}")
            if (
                capture.bundle_uri is None
                or capture.manifest_digest is None
                or not capture.raw_available
            ):
                raise InvalidStateError(f"capture recording is unavailable: {session_id}")
            return CaptureRecordingIdentity(
                session_id=session_id,
                bundle_uri=capture.bundle_uri,
                manifest_digest=capture.manifest_digest,
            )

    def capture_receiver_binding(self, scope: ScopeIdentityV1) -> CaptureReceiverBinding:
        """Return exact catalog lineage for a run-bound manifest subject adapter."""

        if (
            scope.kind.value != "receiver_path"
            or scope.stream_id is None
            or scope.receiver_id is None
        ):
            raise ValueError("capture receiver binding requires a receiver_path scope")
        with self._sessions() as session:
            capture = session.get(CaptureSession, scope.session_id)
            stream = session.get(RadioStream, (scope.session_id, scope.stream_id))
            lineage = session.get(
                CaptureReceiverLineage,
                (scope.session_id, scope.stream_id, scope.receiver_id),
            )
            if capture is None or stream is None or lineage is None:
                raise CatalogNotFoundError("capture receiver binding is absent")
            profile = (
                None
                if capture.profile_revision_id is None
                else session.get(CaptureProfileRevision, capture.profile_revision_id)
            )
            epoch = (
                None
                if lineage.hardware_epoch_id is None
                else session.get(HardwareEpoch, lineage.hardware_epoch_id)
            )
            authority = session.get(CapturePathAuthority, scope.session_id)
            assignment = (
                None
                if lineage.station_assignment_id is None
                else session.get(StationReceiverAssignment, lineage.station_assignment_id)
            )
            radio = session.get(Radio, stream.radio_id)
            bounds_ns = _stream_observed_bounds_ns(stream.attributes)
            if (
                capture.manifest_digest is None
                or lineage.manifest_digest != capture.manifest_digest
                or lineage.radio_id != stream.radio_id
                or radio is None
                or radio.serial != lineage.radio_serial
                or profile is None
                or bounds_ns is None
                or authority is None
                or authority.manifest_digest != capture.manifest_digest
                or lineage.capture_authority_session_id != authority.session_id
            ):
                raise InvalidStateError(
                    "capture receiver binding lacks exact manifest/profile/path authority"
                )
            resolved = lineage.lineage_status == "resolved"
            fixture = authority.authority_kind == "protected_test_fixture"
            if resolved:
                if (
                    lineage.physical_receiver_id is None
                    or lineage.hardware_epoch_external_id is None
                    or epoch is None
                    or assignment is None
                    or assignment.topology_digest != authority.topology_digest
                    or assignment.radio_id != lineage.radio_id
                    or assignment.radio_serial != lineage.radio_serial
                    or assignment.receiver_id != lineage.receiver_id
                    or assignment.physical_receiver_id != lineage.physical_receiver_id
                    or assignment.hardware_epoch_external_id != lineage.hardware_epoch_external_id
                    or assignment.valid_from_utc_ns > bounds_ns[0]
                    or bounds_ns[1] > assignment.valid_until_utc_ns
                    or not _hardware_epoch_covers_stream(epoch, stream)
                    or not authority.physical_association_permitted
                ):
                    raise InvalidStateError(
                        "capture receiver binding lacks exact station assignment authority"
                    )
            elif not (
                fixture
                and capture.source_type == "test"
                and lineage.physical_receiver_id is None
                and lineage.hardware_epoch_external_id is None
                and assignment is None
                and authority.evidence_only
                and not authority.physical_association_permitted
                and not authority.calibration_association_permitted
                and not authority.promotion_permitted
            ):
                raise InvalidStateError("unresolved capture lacks protected TEST authority")
            return CaptureReceiverBinding(
                scope=scope,
                radio_id=lineage.radio_id,
                radio_serial=lineage.radio_serial,
                lineage_resolution="resolved" if resolved else "legacy_unresolved",
                physical_receiver_id=lineage.physical_receiver_id,
                hardware_epoch_id=lineage.hardware_epoch_external_id,
                manifest_digest=lineage.manifest_digest,
                stream_identity_digest=lineage.stream_identity_digest,
                profile_revision_digest=profile.digest,
                capture_start_utc_ns=bounds_ns[0],
                capture_end_utc_ns=bounds_ns[1],
                capture_authority_digest=authority.authority_digest,
                topology_digest=authority.topology_digest,
                calibration_association_permitted=(authority.calibration_association_permitted),
            )

    def pipeline_release_snapshot(self, release_id: str) -> PipelineReleaseSnapshot:
        """Return immutable identities needed to freeze Standard subject facts."""

        with self._sessions() as session:
            release = session.get(PipelineRelease, release_id)
            if release is None:
                raise CatalogNotFoundError(f"pipeline release is absent: {release_id}")
            if release.authority_version != 1:
                raise InvalidStateError("typed snapshots require an authoritative release")
            return PipelineReleaseSnapshot(
                release_id=release.id,
                code_revision=release.code_revision,
                configuration_digest=release.configuration_digest,
                executable_digest=release.executable_digest,
            )

    def capture_frequency_reference(
        self,
        scope: ScopeIdentityV1,
        *,
        tuned_center_frequency_hz: int,
    ) -> ReceiverFrequencyReferenceV1:
        """Resolve calibration for the complete capture interval, or an honest prior."""

        binding = self.capture_receiver_binding(scope)
        if (
            not binding.calibration_association_permitted
            or binding.physical_receiver_id is None
            or binding.hardware_epoch_id is None
        ):
            return ReceiverFrequencyReferenceV1(reference=FrequencyReference.UNCALIBRATED_PRIOR)
        try:
            resolved = self.resolve_frequency_calibration(
                radio_serial=binding.radio_serial,
                receiver_id=scope.receiver_id if scope.receiver_id is not None else -1,
                physical_receiver_id=binding.physical_receiver_id,
                hardware_epoch_id=binding.hardware_epoch_id,
                capture_start_utc_ns=binding.capture_start_utc_ns,
                capture_end_utc_ns=binding.capture_end_utc_ns,
            )
        except CatalogNotFoundError:
            return ReceiverFrequencyReferenceV1(reference=FrequencyReference.UNCALIBRATED_PRIOR)
        calibration = resolved.calibration.registration
        uncertainty = max(
            calibration.center_hz - calibration.uncertainty_lower_hz,
            calibration.uncertainty_upper_hz - calibration.center_hz,
        )
        return ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.CALIBRATED,
            center_frequency_hz=tuned_center_frequency_hz + calibration.center_hz,
            uncertainty_hz=uncertainty,
            calibration_digest=calibration.calibration_digest,
        )

    def add_pipeline_release(
        self,
        *,
        release_id: str,
        code_revision: str,
        environment_digest: str,
        graph_digest: str,
        configuration: dict[str, Any] | None = None,
        executable_digest: str | None = None,
    ) -> None:
        normalized_configuration = {} if configuration is None else configuration
        values: dict[str, Any] = {
            "id": release_id,
            "code_revision": code_revision,
            "environment_digest": environment_digest,
            "graph_digest": graph_digest,
            "configuration": normalized_configuration,
            "configuration_digest": canonical_digest(normalized_configuration),
            "executable_digest": (
                environment_digest if executable_digest is None else executable_digest
            ),
        }
        values["authority_version"] = int(
            _is_exact_git_sha(release_id)
            and _is_exact_git_sha(code_revision)
            and all(
                digest != _ZERO_DIGEST
                for digest in (
                    environment_digest,
                    graph_digest,
                    values["configuration_digest"],
                    values["executable_digest"],
                )
            )
        )
        with self._sessions.begin() as session:
            statement = (
                insert(PipelineRelease)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[PipelineRelease.id])
            )
            inserted = session.execute(statement.returning(PipelineRelease.id)).scalar_one_or_none()
            if inserted is not None:
                return
            existing = session.get(PipelineRelease, release_id)
            if existing is None or any(
                getattr(existing, key) != value for key, value in values.items()
            ):
                raise ProductConflictError(
                    f"pipeline release {release_id!r} conflicts with catalog"
                )

    def register_receiver_path(self, registration: ReceiverPathRegistration) -> ReceiverPathRecord:
        started_at = _datetime_from_utc_ns(registration.hardware_epoch_started_utc_ns)
        if registration.receiver_id not in {0, 1}:
            raise ValueError("receiver ID must be 0 or 1")
        try:
            with self._sessions.begin() as session:
                session.execute(
                    insert(Radio)
                    .values(
                        id=registration.radio_id,
                        serial=registration.radio_serial,
                        uri=registration.radio_uri,
                        transport=registration.transport,
                    )
                    .on_conflict_do_nothing()
                )
                radio = session.get(Radio, registration.radio_id)
                if radio is None or (
                    radio.serial != registration.radio_serial
                    or radio.uri != registration.radio_uri
                    or radio.transport != registration.transport
                ):
                    raise ProductConflictError("receiver-path radio identity conflicts")
                session.execute(
                    insert(ReceiverPath)
                    .values(
                        radio_id=registration.radio_id,
                        receiver_id=registration.receiver_id,
                        physical_receiver_id=registration.physical_receiver_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            ReceiverPath.radio_id,
                            ReceiverPath.receiver_id,
                            ReceiverPath.physical_receiver_id,
                        ]
                    )
                )
                receiver_path = session.execute(
                    select(ReceiverPath)
                    .where(
                        ReceiverPath.radio_id == registration.radio_id,
                        ReceiverPath.receiver_id == registration.receiver_id,
                        ReceiverPath.physical_receiver_id == registration.physical_receiver_id,
                    )
                    .with_for_update()
                ).scalar_one()
                session.execute(
                    insert(HardwareEpoch)
                    .values(
                        external_id=registration.hardware_epoch_id,
                        radio_id=registration.radio_id,
                        started_at=started_at,
                        started_utc_ns=registration.hardware_epoch_started_utc_ns,
                    )
                    .on_conflict_do_nothing(index_elements=[HardwareEpoch.external_id])
                )
                epoch = session.execute(
                    select(HardwareEpoch)
                    .where(HardwareEpoch.external_id == registration.hardware_epoch_id)
                    .with_for_update()
                ).scalar_one()
                if (
                    epoch.radio_id != registration.radio_id
                    or epoch.started_utc_ns != registration.hardware_epoch_started_utc_ns
                    or epoch.ended_utc_ns is not None
                ):
                    raise ProductConflictError("hardware epoch identity conflicts")
                return ReceiverPathRecord(
                    receiver_path_id=receiver_path.id,
                    hardware_epoch_database_id=epoch.id,
                    registration=registration,
                )
        except IntegrityError as error:
            raise ProductConflictError("receiver-path registration conflicts") from error

    def register_station_topology(
        self, topology: StationReceiverTopologyV1
    ) -> StationTopologyRecord:
        """Register one exact topology and its complete immutable assignment inventory."""

        document = topology.model_dump(mode="json")
        try:
            with self._sessions.begin() as session:
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                    {"identity": f"station-topology:{topology.topology_digest}"},
                )
                inserted = session.execute(
                    insert(StationTopology)
                    .values(
                        topology_digest=topology.topology_digest,
                        station_id=topology.station_id,
                        topology_revision=topology.topology_revision,
                        valid_from_utc_ns=topology.valid_from_utc_ns,
                        valid_until_utc_ns=topology.valid_until_utc_ns,
                        document=document,
                        assignment_sealed=False,
                    )
                    .on_conflict_do_nothing()
                    .returning(StationTopology.topology_digest)
                ).scalar_one_or_none()
                stored = session.get(StationTopology, topology.topology_digest)
                if stored is None or any(
                    getattr(stored, key) != value
                    for key, value in {
                        "station_id": topology.station_id,
                        "topology_revision": topology.topology_revision,
                        "valid_from_utc_ns": topology.valid_from_utc_ns,
                        "valid_until_utc_ns": topology.valid_until_utc_ns,
                        "document": document,
                    }.items()
                ):
                    raise ProductConflictError("station topology identity conflicts")
                if inserted is not None:
                    for radio in topology.radios:
                        _reconcile_station_radio(session, radio)
                        for assignment in radio.receiver_assignments:
                            receiver_path, epoch = _reconcile_station_assignment_authorities(
                                session, radio, assignment
                            )
                            session.add(
                                StationReceiverAssignment(
                                    topology_digest=topology.topology_digest,
                                    radio_id=radio.radio_id,
                                    radio_serial=radio.radio_serial,
                                    radio_transport=radio.endpoint_evidence.transport.value,
                                    radio_endpoint=radio.endpoint_evidence.endpoint,
                                    endpoint_evidence_uri=radio.endpoint_evidence.evidence_uri,
                                    endpoint_evidence_digest=(
                                        radio.endpoint_evidence.evidence_digest
                                    ),
                                    receiver_id=assignment.receiver_id,
                                    physical_receiver_id=assignment.physical_receiver_id,
                                    hardware_epoch_external_id=(
                                        assignment.hardware_epoch_external_id
                                    ),
                                    valid_from_utc_ns=assignment.valid_from_utc_ns,
                                    valid_until_utc_ns=assignment.valid_until_utc_ns,
                                    receiver_path_id=receiver_path.id,
                                    hardware_epoch_id=epoch.id,
                                )
                            )
                    session.flush()
                    session.execute(
                        update(StationTopology)
                        .where(StationTopology.topology_digest == topology.topology_digest)
                        .values(assignment_sealed=True)
                    )
                elif not stored.assignment_sealed:
                    raise ProductConflictError("station topology assignment inventory is unsealed")
                assignments = tuple(
                    session.scalars(
                        select(StationReceiverAssignment)
                        .where(
                            StationReceiverAssignment.topology_digest == topology.topology_digest
                        )
                        .order_by(
                            StationReceiverAssignment.radio_id,
                            StationReceiverAssignment.receiver_id,
                            StationReceiverAssignment.valid_from_utc_ns,
                            StationReceiverAssignment.valid_until_utc_ns,
                        )
                    )
                )
                if _station_assignment_documents(assignments) != _topology_assignment_documents(
                    topology
                ):
                    raise ProductConflictError("station topology assignment inventory conflicts")
                return StationTopologyRecord(
                    topology_digest=topology.topology_digest,
                    assignment_count=len(assignments),
                )
        except IntegrityError as error:
            raise ProductConflictError("station topology registration conflicts") from error

    def register_raw_integrity_attestation(
        self, registration: RawIntegrityAttestationRegistration
    ) -> int:
        """Persist one completed full-byte verification prerequisite."""

        attestation = RawIntegrityAttestationV1.model_validate(registration.document)
        if (
            attestation.session_id != registration.session_id
            or attestation.manifest_digest != registration.manifest_digest
            or attestation.attestation_digest != registration.attestation_digest
        ):
            raise ValueError("raw-integrity attestation columns disagree with its document")
        document_micros = attestation.verified_utc_ns // 1_000
        if registration.verified_at.tzinfo is None or registration.verified_at.utcoffset() is None:
            raise ValueError("raw-integrity verification time must be timezone-aware")
        registered_micros = (
            registration.verified_at.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
        ) // timedelta(microseconds=1)
        if document_micros != registered_micros:
            raise ValueError("raw-integrity verification time disagrees with its document")
        values = {
            "session_id": registration.session_id,
            "manifest_digest": registration.manifest_digest,
            "attestation_digest": registration.attestation_digest,
            "document": registration.document,
            "verified_at": registration.verified_at,
        }
        with self._sessions.begin() as session:
            capture = session.get(CaptureSession, registration.session_id)
            if capture is None:
                raise CatalogNotFoundError(f"capture session is absent: {registration.session_id}")
            if not capture.raw_available or capture.manifest_digest != registration.manifest_digest:
                raise InvalidStateError(
                    "raw-integrity attestation disagrees with the available capture"
                )
            inserted = session.execute(
                insert(RawIntegrityAttestation)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[RawIntegrityAttestation.attestation_digest])
                .returning(RawIntegrityAttestation.id)
            ).scalar_one_or_none()
            if inserted is not None:
                return inserted
            existing = session.execute(
                select(RawIntegrityAttestation)
                .where(
                    RawIntegrityAttestation.attestation_digest == registration.attestation_digest
                )
                .with_for_update()
            ).scalar_one()
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise ProductConflictError("raw-integrity attestation digest conflicts")
            return existing.id

    def register_stage_derivation(self, registration: StageDerivationRegistration) -> int:
        """Create or replay one immutable computation identity under concurrency."""

        key = StageDerivationKeyV1.model_validate(registration.key_document)
        if key.derivation_digest != registration.derivation_key:
            raise ValueError("stage derivation key document digest does not match")
        if (
            key.stage_key != registration.stage_key
            or key.algorithm_version != registration.algorithm_version
            or key.implementation_digest != registration.implementation_digest
            or key.configuration_digest != registration.configuration_digest
            or key.environment_digest != registration.environment_digest
            or key.scope.canonical_digest != registration.scope_digest
            or key.input_closure_digest != registration.input_closure_digest
        ):
            raise ValueError("stage derivation columns disagree with the key document")
        values = {
            "derivation_key": registration.derivation_key,
            "stage_key": registration.stage_key,
            "algorithm_version": registration.algorithm_version,
            "implementation_digest": registration.implementation_digest,
            "configuration_digest": registration.configuration_digest,
            "environment_digest": registration.environment_digest,
            "scope_digest": registration.scope_digest,
            "input_closure_digest": registration.input_closure_digest,
            "key_document": registration.key_document,
            "producing_release_id": registration.producing_release_id,
        }
        with self._sessions.begin() as session:
            inserted = session.execute(
                insert(StageDerivation)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[StageDerivation.derivation_key])
                .returning(StageDerivation.id)
            ).scalar_one_or_none()
            if inserted is not None:
                return inserted
            existing = session.execute(
                select(StageDerivation)
                .where(StageDerivation.derivation_key == registration.derivation_key)
                .with_for_update()
            ).scalar_one()
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise ProductConflictError("stage derivation key conflicts with catalog")
            return existing.id

    def register_stage_derivation_output(
        self, registration: StageDerivationOutputRegistration
    ) -> StageDerivationOutputRecord:
        values = {
            "derivation_id": registration.derivation_id,
            "kind": registration.kind,
            "schema_version": registration.schema_version,
            "role": registration.role,
            "status": registration.status,
            "media_type": registration.media_type,
            "logical_uri": registration.logical_uri,
            "digest": registration.digest,
            "byte_size": registration.byte_size,
            "summary": registration.summary,
        }
        with self._sessions.begin() as session:
            inserted = session.execute(
                insert(StageDerivationOutput)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[
                        StageDerivationOutput.derivation_id,
                        StageDerivationOutput.kind,
                        StageDerivationOutput.schema_version,
                    ]
                )
                .returning(StageDerivationOutput.id)
            ).scalar_one_or_none()
            output = (
                session.get(StageDerivationOutput, inserted)
                if inserted is not None
                else session.execute(
                    select(StageDerivationOutput)
                    .where(
                        StageDerivationOutput.derivation_id == registration.derivation_id,
                        StageDerivationOutput.kind == registration.kind,
                        StageDerivationOutput.schema_version == registration.schema_version,
                    )
                    .with_for_update()
                ).scalar_one()
            )
            if output is None:
                raise CatalogNotFoundError("stage derivation output insertion disappeared")
            if any(getattr(output, key) != value for key, value in values.items()):
                raise ProductConflictError("stage derivation output conflicts with catalog")
            return _stage_derivation_output_record(session, output)

    def stage_derivation_outputs(
        self, derivation_key: str
    ) -> tuple[StageDerivationOutputRecord, ...]:
        with self._sessions() as session:
            rows = tuple(
                session.scalars(
                    select(StageDerivationOutput)
                    .join(
                        StageDerivation,
                        StageDerivation.id == StageDerivationOutput.derivation_id,
                    )
                    .where(
                        StageDerivation.derivation_key == derivation_key,
                        StageDerivationOutput.available.is_(True),
                    )
                    .order_by(StageDerivationOutput.kind, StageDerivationOutput.schema_version)
                )
            )
            return tuple(_stage_derivation_output_record(session, item) for item in rows)

    def register_frequency_calibration_set(
        self, registration: FrequencyCalibrationSetRegistration
    ) -> FrequencyCalibrationSetRecord:
        if not registration.calibrations:
            raise ValueError("calibration set must not be empty")
        calibration_ids = tuple(item.calibration_id for item in registration.calibrations)
        if len(set(calibration_ids)) != len(calibration_ids):
            raise ValueError("calibration IDs must be unique within a set")
        try:
            with self._sessions.begin() as session:
                inserted = session.execute(
                    insert(FrequencyCalibrationSet)
                    .values(
                        id=registration.set_id,
                        digest=registration.set_digest,
                        promotion_id=registration.promotion_id,
                        sealed_utc_ns=registration.sealed_utc_ns,
                        evidence_uri=registration.evidence_uri,
                        evidence_digest=registration.evidence_digest,
                        sealed_at=None,
                    )
                    .on_conflict_do_nothing()
                    .returning(FrequencyCalibrationSet.id)
                ).scalar_one_or_none()
                calibration_set = session.get(FrequencyCalibrationSet, registration.set_id)
                if calibration_set is None or (
                    calibration_set.digest != registration.set_digest
                    or calibration_set.promotion_id != registration.promotion_id
                    or calibration_set.sealed_utc_ns != registration.sealed_utc_ns
                    or calibration_set.evidence_uri != registration.evidence_uri
                    or calibration_set.evidence_digest != registration.evidence_digest
                ):
                    raise ProductConflictError("calibration-set identity conflicts")
                if inserted is None:
                    existing = _frequency_calibration_set_record(session, calibration_set)
                    if existing.registration != registration:
                        raise ProductConflictError("calibration-set membership conflicts")
                    return existing
                for ordinal, calibration in enumerate(registration.calibrations):
                    row = _register_frequency_calibration(session, calibration)
                    session.add(
                        FrequencyCalibrationSetMember(
                            set_id=registration.set_id,
                            calibration_id=row.id,
                            ordinal=ordinal,
                        )
                    )
                session.flush()
                session.execute(
                    update(FrequencyCalibrationSet)
                    .where(
                        FrequencyCalibrationSet.id == registration.set_id,
                        FrequencyCalibrationSet.sealed_at.is_(None),
                    )
                    .values(sealed_at=func.clock_timestamp())
                )
                session.flush()
                session.refresh(calibration_set)
                return _frequency_calibration_set_record(session, calibration_set)
        except IntegrityError as error:
            raise ProductConflictError("calibration registration conflicts") from error

    def frequency_calibration_set_by_promotion_id(
        self,
        promotion_id: str,
    ) -> FrequencyCalibrationSetRecord:
        with self._sessions() as session:
            row = session.execute(
                select(FrequencyCalibrationSet).where(
                    FrequencyCalibrationSet.promotion_id == promotion_id,
                    FrequencyCalibrationSet.sealed_at.is_not(None),
                )
            ).scalar_one_or_none()
            if row is None:
                raise CatalogNotFoundError("sealed calibration promotion is absent")
            return _frequency_calibration_set_record(session, row)

    def resolve_frequency_calibration(
        self,
        *,
        radio_serial: str,
        receiver_id: int,
        physical_receiver_id: str,
        hardware_epoch_id: str,
        capture_start_utc_ns: int,
        capture_end_utc_ns: int,
    ) -> FrequencyCalibrationResolution:
        if capture_start_utc_ns < 0 or capture_end_utc_ns <= capture_start_utc_ns:
            raise ValueError("capture interval must be non-empty")
        with self._sessions() as session:
            rows = session.execute(
                select(FrequencyCalibration, FrequencyCalibrationSet)
                .join(ReceiverPath, ReceiverPath.id == FrequencyCalibration.receiver_path_id)
                .join(Radio, Radio.id == ReceiverPath.radio_id)
                .join(HardwareEpoch, HardwareEpoch.id == FrequencyCalibration.hardware_epoch_id)
                .join(
                    FrequencyCalibrationSetMember,
                    FrequencyCalibrationSetMember.calibration_id == FrequencyCalibration.id,
                )
                .join(
                    FrequencyCalibrationSet,
                    FrequencyCalibrationSet.id == FrequencyCalibrationSetMember.set_id,
                )
                .where(
                    Radio.serial == radio_serial,
                    ReceiverPath.receiver_id == receiver_id,
                    ReceiverPath.physical_receiver_id == physical_receiver_id,
                    HardwareEpoch.external_id == hardware_epoch_id,
                    FrequencyCalibrationSet.promotion_id.is_not(None),
                    FrequencyCalibrationSet.sealed_utc_ns.is_not(None),
                    FrequencyCalibrationSet.sealed_at.is_not(None),
                    HardwareEpoch.started_utc_ns <= capture_start_utc_ns,
                    (
                        HardwareEpoch.ended_utc_ns.is_(None)
                        | (capture_end_utc_ns <= HardwareEpoch.ended_utc_ns)
                    ),
                    FrequencyCalibration.valid_from_utc_ns <= capture_start_utc_ns,
                    (
                        FrequencyCalibration.valid_until_utc_ns.is_(None)
                        | (capture_end_utc_ns <= FrequencyCalibration.valid_until_utc_ns)
                    ),
                )
            ).all()
            if not rows:
                raise CatalogNotFoundError("no calibration covers the exact receiver-path dwell")
            if len(rows) != 1:
                raise InvalidStateError("calibration resolution is ambiguous")
            calibration, calibration_set = rows[0]
            calibration_record = FrequencyCalibrationRecord(
                database_id=calibration.id,
                registration=_frequency_calibration_registration(session, calibration),
            )
            set_record = _frequency_calibration_set_record(session, calibration_set)
            return FrequencyCalibrationResolution(
                calibration=calibration_record,
                calibration_set=set_record,
            )

    def create_scientific_campaign(
        self, registration: ScientificCampaignRegistration
    ) -> ScientificCampaignRecord:
        """Create an in-progress WP11 campaign, idempotently by exact identity."""

        with self._sessions.begin() as session:
            session.execute(
                insert(ScientificCampaign)
                .values(
                    id=registration.campaign_id,
                    capture_uri=registration.capture_uri,
                    capture_digest=registration.capture_digest,
                )
                .on_conflict_do_nothing(index_elements=[ScientificCampaign.id])
            )
            campaign = session.execute(
                select(ScientificCampaign)
                .where(ScientificCampaign.id == registration.campaign_id)
                .with_for_update()
            ).scalar_one()
            if (
                campaign.capture_uri != registration.capture_uri
                or campaign.capture_digest != registration.capture_digest
            ):
                raise ProductConflictError(
                    f"scientific campaign {registration.campaign_id!r} conflicts with catalog"
                )
            return _scientific_campaign_record(session, campaign)

    def add_scientific_campaign_stream(
        self,
        *,
        campaign_id: str,
        stream: ScientificCampaignStreamRegistration,
    ) -> ScientificCampaignRecord:
        """Bind one fully materialized stream while fencing retention claims."""

        with self._sessions.begin() as session:
            campaign = session.execute(
                select(ScientificCampaign)
                .where(ScientificCampaign.id == campaign_id)
                .with_for_update()
            ).scalar_one_or_none()
            if campaign is None:
                raise CatalogNotFoundError(f"scientific campaign is absent: {campaign_id}")
            if campaign.state != "in_progress":
                existing = _matching_campaign_stream(session, campaign_id, stream)
                if existing is None or not _campaign_stream_matches(existing, stream):
                    raise InvalidStateError(f"scientific campaign is immutable: {campaign_id}")
                return _scientific_campaign_record(session, campaign)

            existing = _matching_campaign_stream(session, campaign_id, stream)
            if existing is not None:
                return _scientific_campaign_record(session, campaign)
            _validate_campaign_stream_lineage(session, campaign_id, stream)
            session.add(
                ScientificCampaignStream(
                    campaign_id=campaign_id,
                    **_campaign_stream_values(stream),
                )
            )
            session.flush()
            return _scientific_campaign_record(session, campaign)

    def seal_scientific_campaign(
        self,
        *,
        campaign_id: str,
        seal: ScientificCampaignSeal,
    ) -> ScientificCampaignRecord:
        """Atomically seal exactly 40 members; exact retries are idempotent."""

        if seal.result_status not in {"pass", "fail", "inconclusive"}:
            raise ValueError(f"unknown scientific campaign result: {seal.result_status!r}")
        if not seal.outer_seal_uri or not seal.outer_seal_digest.startswith("sha256:"):
            raise ValueError("scientific campaign requires an authoritative outer seal")
        with self._sessions.begin() as session:
            campaign = session.execute(
                select(ScientificCampaign)
                .where(ScientificCampaign.id == campaign_id)
                .with_for_update()
            ).scalar_one_or_none()
            if campaign is None:
                raise CatalogNotFoundError(f"scientific campaign is absent: {campaign_id}")
            if campaign.state == "sealed":
                if not _campaign_seal_matches(campaign, seal):
                    raise ProductConflictError(
                        f"sealed scientific campaign {campaign_id!r} conflicts with retry"
                    )
                return _scientific_campaign_record(session, campaign)
            members = tuple(
                session.scalars(
                    select(ScientificCampaignStream)
                    .where(ScientificCampaignStream.campaign_id == campaign_id)
                    .order_by(ScientificCampaignStream.ordinal)
                )
            )
            ordinals = tuple(member.ordinal for member in members)
            if len(members) != 40 or ordinals != tuple(range(40)):
                raise InvalidStateError(
                    f"scientific campaign requires exactly 40 ordered streams: {len(members)}"
                )
            campaign.state = "sealed"
            campaign.result_status = seal.result_status
            campaign.scientific_uri = seal.scientific_uri
            campaign.scientific_digest = seal.scientific_digest
            campaign.presentation_uri = seal.presentation_uri
            campaign.presentation_digest = seal.presentation_digest
            campaign.outer_seal_uri = seal.outer_seal_uri
            campaign.outer_seal_digest = seal.outer_seal_digest
            campaign.sealed_at = _database_now(session)
            session.flush()
            return _scientific_campaign_record(session, campaign)

    def scientific_campaign(self, campaign_id: str) -> ScientificCampaignRecord | None:
        with self._sessions() as session:
            campaign = session.get(ScientificCampaign, campaign_id)
            return None if campaign is None else _scientific_campaign_record(session, campaign)

    def scientific_campaigns(
        self, *, cursor: int, limit: int
    ) -> tuple[ScientificCampaignRecord, ...]:
        """Return authoritative sealed campaigns newest first."""

        with self._sessions() as session:
            campaigns = tuple(
                session.scalars(
                    select(ScientificCampaign)
                    .where(
                        ScientificCampaign.state == "sealed",
                        ScientificCampaign.seal_authority_version == 1,
                    )
                    .order_by(ScientificCampaign.sealed_at.desc(), ScientificCampaign.id)
                    .offset(cursor)
                    .limit(limit)
                )
            )
            return tuple(_scientific_campaign_record(session, item) for item in campaigns)

    def scientific_campaign_count(self) -> int:
        with self._sessions() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(ScientificCampaign)
                    .where(
                        ScientificCampaign.state == "sealed",
                        ScientificCampaign.seal_authority_version == 1,
                    )
                )
                or 0
            )

    def frequency_calibration(self, database_id: int) -> FrequencyCalibrationRecord:
        """Read one immutable authoritative calibration by catalog identity."""

        with self._sessions() as session:
            calibration = session.get(FrequencyCalibration, database_id)
            if calibration is None:
                raise CatalogNotFoundError(f"frequency calibration is absent: {database_id}")
            return FrequencyCalibrationRecord(
                database_id=calibration.id,
                registration=_frequency_calibration_registration(session, calibration),
            )

    def create_analysis_run(
        self,
        *,
        run_id: str,
        session_id: str,
        pipeline_release_id: str,
        input_manifest_digest: str,
        jobs: Iterable[JobDefinition],
        trigger: str = "automatic",
        pipeline_lane: PipelineLane | str = PipelineLane.STANDARD,
        promotion_policy: PromotionPolicy | str = PromotionPolicy.CURRENT,
        expanded_plan_digest: str | None = None,
        raw_integrity_attestation_digest: str | None = None,
        require_integrity_prerequisite: bool = False,
        subject_bindings: tuple[RunSubjectBindingRegistration, ...] = (),
    ) -> None:
        try:
            canonical_promotion_policy = PromotionPolicy(promotion_policy)
        except ValueError as error:
            raise ValueError(
                f"unknown analysis-run promotion policy: {promotion_policy!r}"
            ) from error
        try:
            canonical_lane = PipelineLane(pipeline_lane)
        except ValueError as error:
            raise ValueError(f"unknown analysis pipeline lane: {pipeline_lane!r}") from error
        definitions = tuple(jobs)
        allowed_resources = {"streaming", "cpu", "memory", "heavy"}
        if any(definition.resource_class not in allowed_resources for definition in definitions):
            raise ValueError("job resource class is outside the finite scheduler vocabulary")
        allowed_iq_access = {"legacy", "none", "receiver_path"}
        if any(definition.iq_access not in allowed_iq_access for definition in definitions):
            raise ValueError("job IQ access is outside the finite scheduler vocabulary")
        typed = any(definition.scope is not None for definition in definitions)
        if typed and any(definition.scope is None for definition in definitions):
            raise ValueError("typed and legacy job scopes cannot be mixed")
        if typed:
            if len(pipeline_release_id) != 40 or any(
                character not in "0123456789abcdef" for character in pipeline_release_id
            ):
                raise ValueError("typed runs require an exact lowercase 40-character Git SHA")
            node_ids = [definition.node_id for definition in definitions]
            if any(node_id is None for node_id in node_ids) or len(set(node_ids)) != len(node_ids):
                raise ValueError("typed jobs require unique node IDs")
            known_nodes = {str(node_id) for node_id in node_ids}
            missing_nodes = sorted(
                dependency
                for definition in definitions
                for dependency in definition.depends_on_node_ids
                if dependency not in known_nodes
            )
            if missing_nodes:
                raise ValueError(
                    "job dependency nodes are absent from the run: " + ", ".join(missing_nodes)
                )
            _require_acyclic_job_nodes(definitions)
            if any(definition.dependencies for definition in definitions):
                raise ValueError(
                    "typed jobs use exact depends_on_node_ids, not legacy dependencies"
                )
            for definition in definitions:
                if not set(definition.ordering_only_node_ids).issubset(
                    definition.depends_on_node_ids
                ):
                    raise ValueError("ordering-only dependency is not an exact dependency")
        else:
            by_identity = {
                (definition.stage_key, definition.scope_key): definition
                for definition in definitions
            }
            if len(by_identity) != len(definitions):
                raise ValueError("job stage/scope identities must be unique within a run")
            missing = sorted(
                {
                    f"{dependency}@{definition.scope_key}"
                    for definition in definitions
                    for dependency in definition.dependencies
                    if (dependency, definition.scope_key) not in by_identity
                }
            )
            if missing:
                raise ValueError(f"job dependencies are absent from the run: {', '.join(missing)}")
        if require_integrity_prerequisite and raw_integrity_attestation_digest is None:
            raise ValueError("typed run creation requires a raw-integrity attestation")
        if typed:
            expected_bindings = {
                definition.scope.canonical_digest: definition.scope
                for definition in definitions
                if definition.scope is not None
                and definition.scope.kind.value in {"receiver_path", "paired"}
            }
            supplied_bindings = {
                item.scope.canonical_digest: item.scope for item in subject_bindings
            }
            if len(supplied_bindings) != len(subject_bindings) or set(supplied_bindings) != set(
                expected_bindings
            ):
                raise ValueError(
                    "typed run requires one exact subject snapshot per receiver-path/paired scope"
                )
            if any(
                supplied_bindings[digest] != scope for digest, scope in expected_bindings.items()
            ):
                raise ValueError("subject snapshot scope identity conflicts")
        elif subject_bindings:
            raise ValueError("legacy runs cannot carry typed subject snapshots")
        requested_identity_digest = _requested_analysis_run_identity_digest(
            session_id=session_id,
            pipeline_release_id=pipeline_release_id,
            input_manifest_digest=input_manifest_digest,
            pipeline_lane=canonical_lane,
            promotion_policy=canonical_promotion_policy,
            expanded_plan_digest=expanded_plan_digest,
            definitions=definitions,
            subject_bindings=subject_bindings,
        )

        try:
            with self._sessions.begin() as session:
                capture = session.get(CaptureSession, session_id)
                if capture is None:
                    raise CatalogNotFoundError(f"capture session is absent: {session_id}")
                if capture.bundle_uri is None or capture.manifest_digest is None:
                    raise InvalidStateError(
                        f"capture session has no committed recording identity: {session_id}"
                    )
                if not capture.raw_available or capture.state in {
                    SessionState.PURGING.value,
                    SessionState.PURGED.value,
                }:
                    raise InvalidStateError(
                        f"capture session raw recording is unavailable: {session_id}"
                    )
                if capture.manifest_digest != input_manifest_digest:
                    raise InvalidStateError(
                        f"analysis input digest disagrees with capture session {session_id}"
                    )
                attestation = None
                release = session.get(PipelineRelease, pipeline_release_id)
                if release is None:
                    raise CatalogNotFoundError(f"pipeline release is absent: {pipeline_release_id}")
                if typed and release.authority_version != 1:
                    raise InvalidStateError(
                        "typed run requires a freshly registered exact release authority"
                    )
                if raw_integrity_attestation_digest is not None:
                    attestation = session.execute(
                        select(RawIntegrityAttestation)
                        .where(
                            RawIntegrityAttestation.attestation_digest
                            == raw_integrity_attestation_digest
                        )
                        .with_for_update()
                    ).scalar_one_or_none()
                    if attestation is None:
                        raise InvalidStateError("raw-integrity attestation is absent")
                    if (
                        attestation.session_id != session_id
                        or attestation.manifest_digest != input_manifest_digest
                    ):
                        raise InvalidStateError(
                            "raw-integrity attestation disagrees with analysis input"
                        )
                candidates = session.scalars(
                    select(AnalysisRun)
                    .where(
                        AnalysisRun.session_id == session_id,
                        AnalysisRun.pipeline_release_id == pipeline_release_id,
                        AnalysisRun.input_manifest_digest == input_manifest_digest,
                        AnalysisRun.pipeline_lane == canonical_lane.value,
                        AnalysisRun.promotion_policy == canonical_promotion_policy.value,
                        AnalysisRun.expanded_plan_digest == expanded_plan_digest,
                        AnalysisRun.state.in_(
                            (
                                AnalysisRunState.PENDING.value,
                                AnalysisRunState.RUNNING.value,
                                AnalysisRunState.SUCCEEDED.value,
                            )
                        ),
                    )
                    .order_by(
                        case(
                            (
                                AnalysisRun.state.in_(
                                    (
                                        AnalysisRunState.PENDING.value,
                                        AnalysisRunState.RUNNING.value,
                                    )
                                ),
                                0,
                            ),
                            else_=1,
                        ),
                        AnalysisRun.created_at.desc(),
                        AnalysisRun.id,
                    )
                )
                for candidate in candidates:
                    if (
                        _persisted_analysis_run_identity_digest(session, candidate)
                        == requested_identity_digest
                    ):
                        raise IdenticalRunExistsError(
                            run_id=candidate.id,
                            state=candidate.state,
                            pipeline_lane=candidate.pipeline_lane,
                        )
                run = AnalysisRun(
                    id=run_id,
                    session_id=session_id,
                    pipeline_release_id=pipeline_release_id,
                    trigger=trigger,
                    pipeline_lane=canonical_lane.value,
                    promotion_policy=canonical_promotion_policy.value,
                    state=AnalysisRunState.PENDING.value,
                    input_manifest_digest=input_manifest_digest,
                    expanded_plan_digest=expanded_plan_digest,
                    raw_integrity_attestation_id=None if attestation is None else attestation.id,
                )
                session.add(run)
                session.flush()
                job_by_identity: dict[tuple[str, str], ProcessingJob] = {}
                job_by_node: dict[str, ProcessingJob] = {}
                for definition in definitions:
                    scope = None
                    scope_key = definition.scope_key
                    if definition.scope is not None:
                        if definition.scope.session_id != session_id:
                            raise InvalidStateError("job scope belongs to a different session")
                        scope = _reconcile_analysis_scope(session, definition.scope)
                        scope_key = definition.scope.canonical_digest
                    job = ProcessingJob(
                        run_id=run_id,
                        stage_key=definition.stage_key,
                        node_id=definition.node_id,
                        resource_class=definition.resource_class,
                        iq_access=definition.iq_access,
                        scope_key=scope_key,
                        scope_id=None if scope is None else scope.id,
                        priority=definition.priority,
                        max_attempts=definition.max_attempts,
                    )
                    session.add(job)
                    job_by_identity[(definition.stage_key, scope_key)] = job
                    if definition.node_id is not None:
                        job_by_node[definition.node_id] = job
                session.flush()
                for definition in definitions:
                    if definition.scope is not None:
                        assert definition.node_id is not None
                        for dependency in definition.depends_on_node_ids:
                            session.add(
                                ProcessingJobDependency(
                                    job_id=job_by_node[definition.node_id].id,
                                    depends_on_job_id=job_by_node[dependency].id,
                                    requires_product=(
                                        dependency not in definition.ordering_only_node_ids
                                    ),
                                )
                            )
                    else:
                        for dependency in definition.dependencies:
                            session.add(
                                ProcessingJobDependency(
                                    job_id=job_by_identity[
                                        (definition.stage_key, definition.scope_key)
                                    ].id,
                                    depends_on_job_id=job_by_identity[
                                        (dependency, definition.scope_key)
                                    ].id,
                                )
                            )
                for registration in subject_bindings:
                    scope = _reconcile_analysis_scope(session, registration.scope)
                    kind, binding_digest = _validate_subject_binding_document(
                        session,
                        registration.scope,
                        registration.document,
                        run_id=run_id,
                        manifest_digest=input_manifest_digest,
                        attestation_digest=raw_integrity_attestation_digest,
                    )
                    snapshot_digest = canonical_digest(
                        {
                            "schema_version": 1,
                            "run_id": run_id,
                            "scope": registration.scope.model_dump(mode="json"),
                            "kind": kind,
                            "binding_digest": binding_digest,
                            "document": registration.document,
                        }
                    )
                    session.add(
                        RunSubjectBinding(
                            run_id=run_id,
                            scope_id=scope.id,
                            kind=kind,
                            binding_digest=binding_digest,
                            snapshot_digest=snapshot_digest,
                            document=registration.document,
                        )
                    )
        except IntegrityError as error:
            if _constraint_name(error) in {
                "uq_analysis_run_active_session",
                "uq_analysis_run_active_session_lane",
            }:
                raise ActiveRunExistsError(
                    f"session {session_id!r} already has an active {canonical_lane.value} run"
                ) from error
            raise

    def active_jobs(self, *, limit: int = 200) -> tuple[ActiveJobRecord, ...]:
        """Return a bounded snapshot of pending jobs and live leases."""

        if limit < 1 or limit > 200:
            raise ValueError("active job limit must be in [1, 200]")
        with self._sessions.begin() as session:
            now = _database_now(session)
            rows = session.execute(
                select(ProcessingJob, AnalysisRun, AnalysisScope, RadioStream.radio_id)
                .join(AnalysisRun, AnalysisRun.id == ProcessingJob.run_id)
                .outerjoin(AnalysisScope, AnalysisScope.id == ProcessingJob.scope_id)
                .outerjoin(
                    RadioStream,
                    and_(
                        RadioStream.session_id == AnalysisScope.session_id,
                        RadioStream.id == AnalysisScope.stream_id,
                    ),
                )
                .where(
                    (ProcessingJob.state == JobState.PENDING.value)
                    | (
                        (ProcessingJob.state == JobState.LEASED.value)
                        & (ProcessingJob.lease_expires_at > now)
                    )
                )
                .order_by(
                    case((ProcessingJob.state == JobState.LEASED.value, 0), else_=1),
                    ProcessingJob.priority.desc(),
                    ProcessingJob.created_at,
                    ProcessingJob.id,
                )
                .limit(limit)
            )
            return tuple(
                ActiveJobRecord(
                    job_id=job.id,
                    run_id=run.id,
                    session_id=run.session_id,
                    pipeline_release_id=run.pipeline_release_id,
                    stage_key=job.stage_key,
                    node_id=job.node_id,
                    state=job.state,
                    resource_class=job.resource_class,
                    scope_kind=None if scope is None else scope.kind,
                    stream_id=None if scope is None else scope.stream_id,
                    radio_id=(
                        scope.radio_id
                        if scope is not None and scope.radio_id is not None
                        else stream_radio_id
                    ),
                    receiver_id=None if scope is None else scope.receiver_id,
                    worker_id=job.lease_owner,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
                for job, run, scope, stream_radio_id in rows
            )

    def claim_job(
        self,
        *,
        worker_id: str,
        lease_for: timedelta,
        authority: WorkerReleaseAuthority | None = None,
        resource_classes: tuple[str, ...] | None = None,
    ) -> JobLease | None:
        _require_positive_duration(lease_for)
        if resource_classes is not None and (
            not resource_classes or len(set(resource_classes)) != len(resource_classes)
        ):
            raise ValueError("worker resource classes must be non-empty and unique")
        allowed_resources = {"streaming", "cpu", "memory", "heavy"}
        if resource_classes is not None and not set(resource_classes).issubset(allowed_resources):
            raise ValueError("worker resource class is outside the scheduler vocabulary")
        with self._sessions.begin() as session:
            now = _database_now(session)
            if authority is not None:
                # Serialize claims with an administrative fence for this exact
                # release. The lock is held only for the short claim transaction.
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": f"processing-release:{authority.pipeline_release_id}"},
                )
            eligible_resources = (
                tuple(sorted(allowed_resources))
                if resource_classes is None
                else tuple(sorted(resource_classes))
            )
            available_resources: list[str] = []
            for resource_class in eligible_resources:
                limit = session.scalar(
                    select(ProcessingResourceCapacity.maximum_leases).where(
                        ProcessingResourceCapacity.resource_class == resource_class
                    )
                )
                if limit is None:
                    raise InvalidStateError(f"resource capacity is absent: {resource_class}")
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": f"processing-resource:{resource_class}"},
                )
                leased = session.scalar(
                    select(func.count())
                    .select_from(ProcessingJob)
                    .where(
                        ProcessingJob.state == JobState.LEASED.value,
                        ProcessingJob.resource_class == resource_class,
                        ProcessingJob.lease_expires_at > now,
                    )
                )
                if int(leased or 0) < limit:
                    available_resources.append(resource_class)
            eligible_resources = tuple(available_resources)
            if not eligible_resources:
                return None
            dependency_job = aliased(ProcessingJob)
            unsatisfied_dependency = exists(
                select(1)
                .select_from(ProcessingJobDependency)
                .join(
                    dependency_job,
                    dependency_job.id == ProcessingJobDependency.depends_on_job_id,
                )
                .where(
                    ProcessingJobDependency.job_id == ProcessingJob.id,
                    dependency_job.state != JobState.SUCCEEDED.value,
                )
            )
            statement = (
                select(ProcessingJob)
                .join(AnalysisRun, AnalysisRun.id == ProcessingJob.run_id)
                .join(PipelineRelease, PipelineRelease.id == AnalysisRun.pipeline_release_id)
                .where(
                    ProcessingJob.state == JobState.PENDING.value,
                    ProcessingJob.available_at <= now,
                    ProcessingJob.attempt_count < ProcessingJob.max_attempts,
                    AnalysisRun.state.in_(
                        [AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value]
                    ),
                    ~unsatisfied_dependency,
                )
                .order_by(
                    ProcessingJob.priority.desc(),
                    ProcessingJob.created_at,
                    ProcessingJob.id,
                )
                .with_for_update(skip_locked=True, of=ProcessingJob)
                .limit(1)
            )
            if authority is not None:
                statement = statement.where(
                    PipelineRelease.id == authority.pipeline_release_id,
                    PipelineRelease.code_revision == authority.code_revision,
                    PipelineRelease.environment_digest == authority.environment_digest,
                    PipelineRelease.graph_digest == authority.graph_digest,
                    PipelineRelease.configuration_digest == authority.configuration_digest,
                    PipelineRelease.executable_digest == authority.executable_digest,
                    PipelineRelease.authority_version == 1,
                )
            else:
                # Legacy jobs retain their historical claim path. Typed v2 jobs
                # never execute unless the worker proves an exact release authority.
                statement = statement.where(ProcessingJob.node_id.is_(None))
            statement = statement.where(ProcessingJob.resource_class.in_(eligible_resources))
            job = session.execute(statement).scalar_one_or_none()
            if job is None:
                return None

            expires_at = now + lease_for
            job.state = JobState.LEASED.value
            job.attempt_count += 1
            job.lease_owner = worker_id
            job.lease_expires_at = expires_at
            job.heartbeat_at = now
            run = session.get(AnalysisRun, job.run_id)
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {job.run_id}")
            if run.state == AnalysisRunState.PENDING.value:
                run.state = AnalysisRunState.RUNNING.value
                run.started_at = now
            session.add(
                ProcessingJobAttempt(
                    job_id=job.id,
                    attempt_number=job.attempt_count,
                    worker_id=worker_id,
                    state=AttemptState.LEASED.value,
                    started_at=now,
                    lease_expires_at=expires_at,
                )
            )
            raw_dependency_node_ids = tuple(
                session.execute(
                    select(dependency_job.node_id)
                    .join(
                        ProcessingJobDependency,
                        ProcessingJobDependency.depends_on_job_id == dependency_job.id,
                    )
                    .where(
                        ProcessingJobDependency.job_id == job.id,
                        ProcessingJobDependency.requires_product.is_(True),
                    )
                    .order_by(dependency_job.node_id)
                ).scalars()
            )
            if job.node_id is not None and any(item is None for item in raw_dependency_node_ids):
                raise InvalidStateError("typed job has an untyped product dependency")
            dependency_node_ids = tuple(
                item for item in raw_dependency_node_ids if item is not None
            )
            return JobLease(
                job_id=job.id,
                run_id=job.run_id,
                stage_key=job.stage_key,
                scope_key=job.scope_key,
                attempt_number=job.attempt_count,
                worker_id=worker_id,
                lease_expires_at=expires_at,
                scope_id=job.scope_id,
                scope=(
                    None
                    if job.scope_id is None
                    else _scope_identity(session.get(AnalysisScope, job.scope_id))
                ),
                node_id=job.node_id,
                dependency_node_ids=dependency_node_ids,
                resource_class=job.resource_class,
                iq_access=job.iq_access,
            )

    def record_pending_worker_incompatibility(
        self, *, worker_id: str, authority: WorkerReleaseAuthority
    ) -> bool:
        """Record one bounded operational event without claiming or consuming an attempt."""

        with self._sessions.begin() as session:
            release_id = session.scalar(
                select(AnalysisRun.pipeline_release_id)
                .join(ProcessingJob, ProcessingJob.run_id == AnalysisRun.id)
                .join(PipelineRelease, PipelineRelease.id == AnalysisRun.pipeline_release_id)
                .where(
                    ProcessingJob.state == JobState.PENDING.value,
                    AnalysisRun.state.in_(
                        (AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value)
                    ),
                    (
                        (PipelineRelease.id != authority.pipeline_release_id)
                        | (PipelineRelease.code_revision != authority.code_revision)
                        | (PipelineRelease.environment_digest != authority.environment_digest)
                        | (PipelineRelease.graph_digest != authority.graph_digest)
                        | (PipelineRelease.configuration_digest != authority.configuration_digest)
                        | (PipelineRelease.executable_digest != authority.executable_digest)
                    ),
                )
                .order_by(AnalysisRun.created_at, AnalysisRun.id)
                .limit(1)
            )
            if release_id is None:
                return False
            session.add(
                WorkerIncompatibilityEvent(
                    worker_id=worker_id,
                    pipeline_release_id=release_id,
                    reason="release_authority_mismatch",
                    worker_authority={
                        "pipeline_release_id": authority.pipeline_release_id,
                        "code_revision": authority.code_revision,
                        "environment_digest": authority.environment_digest,
                        "graph_digest": authority.graph_digest,
                        "configuration_digest": authority.configuration_digest,
                        "executable_digest": authority.executable_digest,
                    },
                )
            )
            return True

    def fail_one_unserviceable_run(
        self, *, worker_id: str, authority: WorkerReleaseAuthority
    ) -> str | None:
        """Fail one active run that this deployment can never claim.

        A release-filtered worker must not leave incompatible work pending
        forever.  The operation is deliberately bounded to one run, skips
        locked rows, and refuses runs with a live lease so a rolling worker
        shutdown cannot steal in-flight work.  Pending work is failed without
        manufacturing scientific attempts.
        """

        with self._sessions.begin() as session:
            now = _database_now(session)
            live_lease = exists().where(
                ProcessingJob.run_id == AnalysisRun.id,
                ProcessingJob.state == JobState.LEASED.value,
                ProcessingJob.lease_expires_at > now,
            )
            exact_authority = and_(
                PipelineRelease.id == authority.pipeline_release_id,
                PipelineRelease.code_revision == authority.code_revision,
                PipelineRelease.environment_digest == authority.environment_digest,
                PipelineRelease.graph_digest == authority.graph_digest,
                PipelineRelease.configuration_digest == authority.configuration_digest,
                PipelineRelease.executable_digest == authority.executable_digest,
                PipelineRelease.authority_version == 1,
            )
            run = session.execute(
                select(AnalysisRun)
                .join(PipelineRelease, PipelineRelease.id == AnalysisRun.pipeline_release_id)
                .where(
                    AnalysisRun.state.in_(
                        (AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value)
                    ),
                    ~exact_authority,
                    ~live_lease,
                )
                .order_by(AnalysisRun.created_at, AnalysisRun.id)
                .with_for_update(skip_locked=True, of=AnalysisRun)
                .limit(1)
            ).scalar_one_or_none()
            if run is None:
                return None
            jobs = tuple(
                session.scalars(
                    select(ProcessingJob)
                    .where(ProcessingJob.run_id == run.id)
                    .order_by(ProcessingJob.id)
                    .with_for_update()
                )
            )
            failure = (
                "no eligible worker for pipeline release "
                f"{run.pipeline_release_id}; deployed release is "
                f"{authority.pipeline_release_id}"
            )
            for job in jobs:
                if job.state == JobState.LEASED.value:
                    attempt = _current_attempt(session, job)
                    attempt.state = AttemptState.EXPIRED.value
                    attempt.completed_at = now
                    attempt.error = failure
                    _clear_lease(job)
                if job.state in (JobState.PENDING.value, JobState.LEASED.value):
                    job.state = JobState.FAILED.value
                    job.error = failure
            run.state = AnalysisRunState.FAILED.value
            run.failure = failure
            run.sealed_at = now
            session.add(
                WorkerIncompatibilityEvent(
                    worker_id=worker_id,
                    pipeline_release_id=run.pipeline_release_id,
                    reason="unserviceable_deployed_release",
                    worker_authority={
                        "pipeline_release_id": authority.pipeline_release_id,
                        "code_revision": authority.code_revision,
                        "environment_digest": authority.environment_digest,
                        "graph_digest": authority.graph_digest,
                        "configuration_digest": authority.configuration_digest,
                        "executable_digest": authority.executable_digest,
                    },
                )
            )
            return run.id

    def heartbeat_job(
        self,
        *,
        job_id: int,
        worker_id: str,
        lease_for: timedelta,
    ) -> datetime:
        _require_positive_duration(lease_for)
        with self._sessions.begin() as session:
            now = _database_now(session)
            job = _locked_job(session, job_id)
            _require_live_lease(job, worker_id, now)
            expires_at = now + lease_for
            job.heartbeat_at = now
            job.lease_expires_at = expires_at
            attempt = _current_attempt(session, job)
            attempt.lease_expires_at = expires_at
            return expires_at

    def reclaim_expired_jobs(
        self,
        *,
        as_of: datetime | None = None,
        limit: int = 1000,
    ) -> tuple[int, ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("expired job reclaim limit must be in [1, 1000]")
        with self._sessions.begin() as session:
            now = _database_now(session)
            expiry_cutoff = now if as_of is None else _require_aware(as_of)
            jobs = session.execute(
                select(ProcessingJob)
                .where(
                    ProcessingJob.state == JobState.LEASED.value,
                    ProcessingJob.lease_expires_at <= expiry_cutoff,
                )
                .order_by(ProcessingJob.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
            ).scalars()
            reclaimed: list[int] = []
            for job in jobs:
                attempt = _current_attempt(session, job)
                attempt.state = AttemptState.EXPIRED.value
                attempt.completed_at = now
                attempt.error = "lease expired"
                job.lease_owner = None
                job.lease_expires_at = None
                job.heartbeat_at = None
                if job.attempt_count >= job.max_attempts:
                    job.state = JobState.FAILED.value
                    job.error = "maximum attempts exhausted after lease expiry"
                else:
                    job.state = JobState.PENDING.value
                    job.available_at = now
                reclaimed.append(job.id)
            return tuple(reclaimed)

    def complete_job(self, *, job_id: int, worker_id: str, outcome: str) -> None:
        with self._sessions.begin() as session:
            now = _database_now(session)
            job = _locked_job(session, job_id)
            _require_live_lease(job, worker_id, now)
            attempt = _current_attempt(session, job)
            attempt.state = AttemptState.SUCCEEDED.value
            attempt.outcome = outcome
            attempt.completed_at = now
            job.state = JobState.SUCCEEDED.value
            job.outcome = outcome
            job.error = None
            _clear_lease(job)

    def fail_job(
        self,
        *,
        job_id: int,
        worker_id: str,
        error: str,
        retryable: bool = True,
        retry_after: timedelta = timedelta(0),
    ) -> JobState:
        if retry_after < timedelta(0):
            raise ValueError("retry_after cannot be negative")
        with self._sessions.begin() as session:
            now = _database_now(session)
            job = _locked_job(session, job_id)
            _require_live_lease(job, worker_id, now)
            attempt = _current_attempt(session, job)
            attempt.state = AttemptState.FAILED.value
            attempt.error = error
            attempt.completed_at = now
            job.error = error
            _clear_lease(job)
            if retryable and job.attempt_count < job.max_attempts:
                job.state = JobState.PENDING.value
                job.available_at = now + retry_after
            else:
                job.state = JobState.FAILED.value
            return JobState(job.state)

    def defer_incompatible_job(
        self,
        *,
        job_id: int,
        worker_id: str,
        authority: WorkerReleaseAuthority,
        reason: str = "post_claim_release_authority_mismatch",
    ) -> None:
        """Release a typed lease without consuming a scientific attempt."""

        with self._sessions.begin() as session:
            now = _database_now(session)
            job = _locked_job(session, job_id)
            _require_live_lease(job, worker_id, now)
            if job.node_id is None:
                raise InvalidStateError("legacy jobs cannot use typed incompatibility deferral")
            attempt = _current_attempt(session, job)
            session.delete(attempt)
            job.attempt_count -= 1
            job.state = JobState.PENDING.value
            job.available_at = now
            job.error = None
            _clear_lease(job)
            run = session.get(AnalysisRun, job.run_id)
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {job.run_id}")
            other_progress = session.scalar(
                select(
                    exists().where(
                        ProcessingJob.run_id == run.id,
                        ProcessingJob.id != job.id,
                        (
                            (ProcessingJob.state != JobState.PENDING.value)
                            | (ProcessingJob.attempt_count > 0)
                        ),
                    )
                )
            )
            if not other_progress and run.state == AnalysisRunState.RUNNING.value:
                run.state = AnalysisRunState.PENDING.value
                run.started_at = None
            session.add(
                WorkerIncompatibilityEvent(
                    worker_id=worker_id,
                    pipeline_release_id=run.pipeline_release_id,
                    reason=reason,
                    worker_authority={
                        "pipeline_release_id": authority.pipeline_release_id,
                        "code_revision": authority.code_revision,
                        "environment_digest": authority.environment_digest,
                        "graph_digest": authority.graph_digest,
                        "configuration_digest": authority.configuration_digest,
                        "executable_digest": authority.executable_digest,
                    },
                )
            )

    def commit_stage_result(self, commit: StageResultCommit) -> tuple[int, ...]:
        """Atomically publish a complete typed result and finish its exact lease."""

        declared = tuple(sorted(set(commit.declared_products)))
        if declared != commit.declared_products:
            raise ValueError("declared product inventory must be unique and ordered")
        actual = tuple(sorted((item.kind, item.schema_version) for item in commit.products))
        if actual != declared or len(actual) != len(commit.products):
            raise ValueError("stage result does not contain its exact declared product set")
        consumed = tuple(sorted(set(commit.consumed_product_ids)))
        if consumed != commit.consumed_product_ids or any(item <= 0 for item in consumed):
            raise ValueError("consumed product IDs must be positive, unique and ordered")

        with self._sessions.begin() as session:
            now = _database_now(session)
            job = _locked_job(session, commit.job_id)
            if job.node_id is None:
                raise InvalidStateError("legacy jobs use register_product and complete_job")
            run = session.get(AnalysisRun, job.run_id)
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {job.run_id}")
            _require_exact_release_authority(session, run, commit.authority)
            attempt = _current_attempt(session, job)
            replay = job.state == JobState.SUCCEEDED.value
            if replay:
                if (
                    attempt.state != AttemptState.SUCCEEDED.value
                    or attempt.worker_id != commit.worker_id
                    or attempt.attempt_number != commit.attempt_number
                    or attempt.outcome != commit.outcome
                    or job.outcome != commit.outcome
                ):
                    raise ProductConflictError("stage-result replay conflicts with completion")
            else:
                _require_live_lease(job, commit.worker_id, now)
                if (
                    attempt.worker_id != commit.worker_id
                    or attempt.attempt_number != commit.attempt_number
                ):
                    raise LeaseLostError("stage-result attempt no longer owns the job")

            scope = None if job.scope_id is None else session.get(AnalysisScope, job.scope_id)
            exact_scope = None if scope is None else _scope_identity(scope)
            for product in commit.products:
                if (
                    product.run_id != job.run_id
                    or product.stage_key != job.stage_key
                    or product.status != commit.outcome
                    or product.input_product_ids != consumed
                    or product.scope != exact_scope
                ):
                    raise InvalidStateError("stage product disagrees with its exact leased result")

            input_products = tuple(
                session.scalars(
                    select(AnalysisProduct)
                    .where(AnalysisProduct.id.in_(consumed))
                    .order_by(AnalysisProduct.id)
                    .with_for_update()
                )
            )
            if len(input_products) != len(consumed):
                raise CatalogNotFoundError("one or more consumed products are absent")
            if any(item.run_id != run.id or not item.available for item in input_products):
                raise InvalidStateError("consumed products must be available in the same run")
            required_job_ids = set(
                session.scalars(
                    select(ProcessingJobDependency.depends_on_job_id).where(
                        ProcessingJobDependency.job_id == job.id,
                        ProcessingJobDependency.requires_product.is_(True),
                    )
                )
            )
            input_job_ids = set(
                session.scalars(
                    select(ProcessingJob.id).where(
                        ProcessingJob.run_id == run.id,
                        tuple_(ProcessingJob.stage_key, ProcessingJob.scope_key).in_(
                            tuple((item.stage_key, item.scope_key) for item in input_products)
                        ),
                    )
                )
            )
            if input_job_ids != required_job_ids:
                raise InvalidStateError(
                    "typed result does not consume its exact predecessor-job inventory"
                )

            product_ids = tuple(
                _register_typed_product_membership(
                    session,
                    product,
                    run=run,
                    producer_job=job,
                    input_product_ids=consumed,
                )
                for product in commit.products
            )
            existing_identities = tuple(
                session.execute(
                    select(AnalysisProduct.kind, AnalysisProduct.schema_version)
                    .where(
                        AnalysisProduct.run_id == run.id,
                        AnalysisProduct.stage_key == job.stage_key,
                        AnalysisProduct.scope_key == job.scope_key,
                    )
                    .order_by(AnalysisProduct.kind, AnalysisProduct.schema_version)
                )
            )
            if existing_identities != declared:
                raise ProductConflictError(
                    "catalog product inventory differs from declared stage result"
                )
            if not replay:
                attempt.state = AttemptState.SUCCEEDED.value
                attempt.outcome = commit.outcome
                attempt.completed_at = now
                job.state = JobState.SUCCEEDED.value
                job.outcome = commit.outcome
                job.error = None
                _clear_lease(job)
            return product_ids

    def register_product(self, product: ProductRegistration) -> int:
        input_product_ids = tuple(sorted(set(product.input_product_ids)))
        if any(product_id <= 0 for product_id in input_product_ids):
            raise ValueError("input product IDs must be positive")
        if product.derivation_mode not in {"legacy", "computed", "reused"}:
            raise ValueError("unknown product derivation mode")
        values = {
            "run_id": product.run_id,
            "stage_key": product.stage_key,
            "scope_key": product.scope_key,
            "kind": product.kind,
            "schema_version": product.schema_version,
            "role": product.role,
            "status": product.status,
            "media_type": product.media_type,
            "logical_uri": product.logical_uri,
            "digest": product.digest,
            "byte_size": product.byte_size,
            "coverage": product.coverage,
            "summary": product.summary,
            "derivation_output_id": product.derivation_output_id,
            "derivation_mode": product.derivation_mode,
            "reused_from_product_id": product.reused_from_product_id,
        }
        identity = {
            key: values[key]
            for key in ("run_id", "stage_key", "scope_key", "kind", "schema_version")
        }
        with self._sessions.begin() as session:
            run = session.get(AnalysisRun, product.run_id)
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {product.run_id}")
            scope = None
            scope_key = product.scope_key
            if product.scope is not None:
                if product.scope.session_id != run.session_id:
                    raise InvalidStateError("product scope belongs to a different session")
                scope = _reconcile_analysis_scope(session, product.scope)
                scope_key = product.scope.canonical_digest
                values["scope_key"] = scope_key
                values["scope_id"] = scope.id
                identity["scope_key"] = scope_key
            producer_job = session.execute(
                select(ProcessingJob)
                .where(
                    ProcessingJob.run_id == product.run_id,
                    ProcessingJob.stage_key == product.stage_key,
                    ProcessingJob.scope_key == scope_key,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if producer_job is None:
                raise InvalidStateError("product producer job is absent from the run plan")
            if producer_job.node_id is not None:
                raise InvalidStateError(
                    "typed products require atomic commit_stage_result publication"
                )
            if run.state not in (
                AnalysisRunState.PENDING.value,
                AnalysisRunState.RUNNING.value,
            ):
                raise LeaseLostError("analysis run no longer holds active publication authority")
            if scope is not None and producer_job.scope_id != scope.id:
                raise InvalidStateError("product producer scope disagrees with the run plan")
            input_products = tuple(
                session.scalars(
                    select(AnalysisProduct)
                    .where(AnalysisProduct.id.in_(input_product_ids))
                    .order_by(AnalysisProduct.id)
                    .with_for_update()
                )
            )
            if len(input_products) != len(input_product_ids):
                raise CatalogNotFoundError("one or more input products are absent")
            if any(
                input_product.run_id != product.run_id or not input_product.available
                for input_product in input_products
            ):
                raise InvalidStateError(
                    "input products must be available products from the same analysis run"
                )
            dependency_rows = tuple(
                session.execute(
                    select(
                        ProcessingJobDependency.depends_on_job_id,
                        ProcessingJobDependency.requires_product,
                    ).where(ProcessingJobDependency.job_id == producer_job.id)
                )
            )
            authorized_job_ids = {job_id for job_id, _ in dependency_rows}
            required_job_ids = {
                job_id for job_id, requires_product in dependency_rows if requires_product
            }
            input_job_ids: set[int] = set()
            if input_products:
                input_job_ids = set(
                    session.scalars(
                        select(ProcessingJob.id).where(
                            ProcessingJob.run_id == product.run_id,
                            tuple_(ProcessingJob.stage_key, ProcessingJob.scope_key).in_(
                                tuple((item.stage_key, item.scope_key) for item in input_products)
                            ),
                        )
                    )
                )
                if input_job_ids != authorized_job_ids.intersection(input_job_ids):
                    raise InvalidStateError(
                        "input product is not authorized by an exact producer-job dependency"
                    )
            if producer_job.node_id is not None and input_job_ids != required_job_ids:
                raise InvalidStateError(
                    "typed product lineage does not consume its exact required "
                    "predecessor inventory"
                )
            _validate_derivation_membership(session, product, values)
            statement = (
                insert(AnalysisProduct)
                .values(**values, lineage_sealed=False)
                .on_conflict_do_nothing(
                    index_elements=[
                        AnalysisProduct.run_id,
                        AnalysisProduct.stage_key,
                        AnalysisProduct.scope_key,
                        AnalysisProduct.kind,
                        AnalysisProduct.schema_version,
                    ]
                )
                .returning(AnalysisProduct.id)
            )
            product_id = session.execute(statement).scalar_one_or_none()
            if product_id is not None:
                if run.state not in {
                    AnalysisRunState.PENDING.value,
                    AnalysisRunState.RUNNING.value,
                }:
                    raise InvalidStateError("cannot add a product to a terminal analysis run")
                session.add_all(
                    ProductDependency(
                        product_id=product_id,
                        input_product_id=input_product_id,
                    )
                    for input_product_id in input_product_ids
                )
                session.flush()
                session.execute(
                    update(AnalysisProduct)
                    .where(AnalysisProduct.id == product_id)
                    .values(lineage_sealed=True)
                )
                return product_id
            existing = session.execute(
                select(AnalysisProduct).filter_by(**identity).with_for_update()
            ).scalar_one()
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise ProductConflictError(
                    f"product identity conflicts with existing product {existing.id}"
                )
            existing_inputs = tuple(
                session.scalars(
                    select(ProductDependency.input_product_id)
                    .where(ProductDependency.product_id == existing.id)
                    .order_by(ProductDependency.input_product_id)
                )
            )
            if existing_inputs != input_product_ids:
                raise ProductConflictError(
                    f"product dependency lineage conflicts with existing product {existing.id}"
                )
            if not existing.lineage_sealed:
                raise ProductConflictError(
                    f"product {existing.id} has an unsealed dependency lineage"
                )
            return existing.id

    def add_retention_hold(self, *, session_id: str, reason: str, created_by: str) -> int:
        with self._sessions.begin() as session:
            capture = session.execute(
                select(CaptureSession).where(CaptureSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if capture is None:
                raise CatalogNotFoundError(f"capture session is absent: {session_id}")
            existing = session.execute(
                select(RetentionHold)
                .where(
                    RetentionHold.session_id == session_id,
                    RetentionHold.released_at.is_(None),
                )
                .with_for_update()
            ).scalar_one_or_none()
            if existing is not None:
                return existing.id
            hold = RetentionHold(session_id=session_id, reason=reason, created_by=created_by)
            session.add(hold)
            session.flush()
            return hold.id

    def release_retention_hold(self, *, session_id: str) -> bool:
        with self._sessions.begin() as session:
            hold = session.execute(
                select(RetentionHold)
                .where(
                    RetentionHold.session_id == session_id,
                    RetentionHold.released_at.is_(None),
                )
                .with_for_update()
            ).scalar_one_or_none()
            if hold is None:
                return False
            hold.released_at = _database_now(session)
            return True

    def retention_candidates(self) -> tuple[CatalogRetentionCandidate, ...]:
        """Return eligible raw-session and superseded-product units oldest first."""

        with self._sessions() as session:
            now = _database_now(session)
            active_run = exists(
                select(1).where(
                    AnalysisRun.session_id == CaptureSession.id,
                    AnalysisRun.state.in_(
                        (AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value)
                    ),
                )
            )
            active_hold = exists(
                select(1).where(
                    RetentionHold.session_id == CaptureSession.id,
                    RetentionHold.released_at.is_(None),
                )
            )
            test_tag = exists(
                select(1).where(
                    SessionTag.session_id == CaptureSession.id,
                    func.upper(SessionTag.tag_name) == "TEST",
                )
            )
            accepted_analysis = exists(
                select(1).where(CurrentAnalysis.session_id == CaptureSession.id)
            )
            campaign_session = exists(
                select(1).where(
                    ScientificCampaignStream.session_id == CaptureSession.id,
                )
            )
            captures = session.execute(
                select(CaptureSession)
                .where(
                    CaptureSession.state.in_(
                        (SessionState.COMMITTED.value, SessionState.DEGRADED.value)
                    ),
                    CaptureSession.raw_available.is_(True),
                    CaptureSession.bundle_uri.is_not(None),
                    CaptureSession.allocated_bytes > 0,
                    CaptureSession.source_type != "test",
                    CaptureSession.purge_claim_token.is_(None),
                    ~active_hold,
                    ~test_tag,
                    ~active_run,
                    ~campaign_session,
                    accepted_analysis,
                )
                .order_by(CaptureSession.created_at, CaptureSession.id)
            ).scalars()
            candidates = [
                CatalogRetentionCandidate(
                    kind="session",
                    item_id=capture.id,
                    session_id=capture.id,
                    created_at=capture.created_at,
                    allocated_bytes=capture.allocated_bytes,
                    logical_uri=capture.bundle_uri or "",
                )
                for capture in captures
            ]

            campaign_product_closure = _scientific_campaign_product_closure()
            products = session.execute(
                select(AnalysisProduct, AnalysisRun)
                .join(AnalysisRun, AnalysisRun.id == AnalysisProduct.run_id)
                .join(CaptureSession, CaptureSession.id == AnalysisRun.session_id)
                .outerjoin(CurrentAnalysis, CurrentAnalysis.run_id == AnalysisRun.id)
                .where(
                    AnalysisProduct.available.is_(True),
                    AnalysisProduct.derivation_output_id.is_(None),
                    AnalysisProduct.byte_size > 0,
                    CurrentAnalysis.run_id.is_(None),
                    ~AnalysisProduct.id.in_(select(campaign_product_closure.c.product_id)),
                    AnalysisRun.state.not_in(
                        (AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value)
                    ),
                    CaptureSession.source_type != "test",
                    ~exists(
                        select(1).where(
                            SessionTag.session_id == CaptureSession.id,
                            func.upper(SessionTag.tag_name) == "TEST",
                        )
                    ),
                    (
                        AnalysisProduct.purge_claim_token.is_(None)
                        | (AnalysisProduct.purge_claim_expires_at <= now)
                    ),
                )
                .order_by(AnalysisProduct.created_at, AnalysisProduct.id)
            ).all()
            candidates.extend(
                CatalogRetentionCandidate(
                    kind="artifact",
                    item_id=str(product.id),
                    session_id=run.session_id,
                    created_at=product.created_at,
                    allocated_bytes=product.byte_size,
                    logical_uri=product.logical_uri,
                )
                for product, run in products
            )
            return tuple(
                sorted(candidates, key=lambda item: (item.created_at, item.kind, item.item_id))
            )

    def claim_session_for_purge(
        self,
        *,
        session_id: str,
        claim_token: str,
        lease_for: timedelta,
    ) -> CatalogSessionPurgeClaim | None:
        _require_positive_duration(lease_for)
        with self._sessions.begin() as session:
            now = _database_now(session)
            capture = session.execute(
                select(CaptureSession).where(CaptureSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if capture is None:
                raise CatalogNotFoundError(f"capture session is absent: {session_id}")
            if not _session_is_purge_eligible(session, capture):
                return None
            previous_state = capture.state
            capture.state = SessionState.PURGING.value
            capture.purge_previous_state = previous_state
            capture.purge_claim_token = claim_token
            capture.purge_claim_expires_at = now + lease_for
            return CatalogSessionPurgeClaim(
                session_id=capture.id,
                claim_token=claim_token,
                previous_state=previous_state,
                bundle_uri=capture.bundle_uri or "",
                allocated_bytes=capture.allocated_bytes,
                products=(),
            )

    def commit_session_purge(
        self,
        *,
        session_id: str,
        claim_token: str,
        staged_bytes: int,
        recording_manifest: dict[str, Any],
        recording_root: str,
        durable_hold_present: Callable[[str], bool],
    ) -> None:
        with self._sessions.begin() as session:
            now = _database_now(session)
            capture = _locked_purge_capture(session, session_id, claim_token, now)
            has_hold = session.scalar(
                select(
                    exists().where(
                        RetentionHold.session_id == session_id,
                        RetentionHold.released_at.is_(None),
                    )
                )
            )
            if has_hold or durable_hold_present(session_id):
                raise InvalidStateError("retention hold won the purge fence")
            if _campaign_references_session(session, session_id):
                raise InvalidStateError("scientific campaign won the purge fence")
            attributes = dict(capture.attributes)
            attributes.update(
                {
                    "recording_manifest": recording_manifest,
                    "recording_root": recording_root,
                    "retention_tombstone": {
                        "claim_token": claim_token,
                        "staged_bytes": staged_bytes,
                        "purged_at": now.isoformat(),
                    },
                }
            )
            capture.attributes = attributes
            capture.state = SessionState.PURGED.value
            capture.raw_available = False
            capture.purged_at = now
            capture.purge_claim_token = None
            capture.purge_claim_expires_at = None
            capture.purge_previous_state = None
            session.add(
                RetentionEvent(
                    session_id=session_id,
                    event_type="purge_staged",
                    bytes_reclaimed=0,
                    details={"claim_token": claim_token, "staged_bytes": staged_bytes},
                )
            )

    def release_session_purge_claim(self, *, session_id: str, claim_token: str) -> bool:
        with self._sessions.begin() as session:
            capture = session.execute(
                select(CaptureSession).where(CaptureSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if (
                capture is None
                or capture.state != SessionState.PURGING.value
                or capture.purge_claim_token != claim_token
            ):
                return False
            capture.state = capture.purge_previous_state or SessionState.COMMITTED.value
            capture.purge_claim_token = None
            capture.purge_claim_expires_at = None
            capture.purge_previous_state = None
            return True

    def claim_product_for_purge(
        self,
        *,
        product_id: int,
        claim_token: str,
        lease_for: timedelta,
    ) -> CatalogProductPurgeClaim | None:
        _require_positive_duration(lease_for)
        with self._sessions.begin() as session:
            now = _database_now(session)
            row = session.execute(
                select(AnalysisProduct, AnalysisRun, CaptureSession)
                .join(AnalysisRun, AnalysisRun.id == AnalysisProduct.run_id)
                .join(CaptureSession, CaptureSession.id == AnalysisRun.session_id)
                .outerjoin(CurrentAnalysis, CurrentAnalysis.run_id == AnalysisRun.id)
                .where(AnalysisProduct.id == product_id, CurrentAnalysis.run_id.is_(None))
                .with_for_update(of=AnalysisProduct)
            ).one_or_none()
            if row is None:
                return None
            product, run, capture = row
            if (
                not product.available
                or product.derivation_output_id is not None
                or product.byte_size <= 0
                or run.state in (AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value)
                or capture.source_type == "test"
                or _has_test_tag(session, capture.id)
                or _campaign_references_product(session, product.id)
                or (
                    product.purge_claim_token is not None
                    and product.purge_claim_expires_at is not None
                    and product.purge_claim_expires_at > now
                )
            ):
                return None
            product.purge_claim_token = claim_token
            product.purge_claim_expires_at = now + lease_for
            return CatalogProductPurgeClaim(
                product=_catalog_product_record(product),
                session_id=run.session_id,
                claim_token=claim_token,
            )

    def commit_product_purge(self, *, product_id: int, claim_token: str, staged_bytes: int) -> None:
        if staged_bytes < 0:
            raise ValueError("staged_bytes cannot be negative")
        with self._sessions.begin() as session:
            now = _database_now(session)
            session_id = session.scalar(
                select(AnalysisRun.session_id)
                .join(AnalysisProduct, AnalysisProduct.run_id == AnalysisRun.id)
                .where(AnalysisProduct.id == product_id)
            )
            if session_id is None:
                raise LeaseLostError(f"product purge lease is no longer owned: {product_id}")
            session.execute(
                select(CaptureSession.id).where(CaptureSession.id == session_id).with_for_update()
            ).scalar_one()
            product = session.execute(
                select(AnalysisProduct).where(AnalysisProduct.id == product_id).with_for_update()
            ).scalar_one_or_none()
            if (
                product is None
                or product.purge_claim_token != claim_token
                or product.purge_claim_expires_at is None
                or product.purge_claim_expires_at <= now
            ):
                raise LeaseLostError(f"product purge lease is no longer owned: {product_id}")
            if _campaign_references_product(session, product_id):
                raise InvalidStateError("scientific campaign won the product purge fence")
            product.available = False
            product.purged_at = now
            product.purge_claim_token = None
            product.purge_claim_expires_at = None
            session.add(
                RetentionEvent(
                    session_id=session_id,
                    event_type="artifact_purge_staged",
                    bytes_reclaimed=0,
                    details={
                        "product_id": product_id,
                        "claim_token": claim_token,
                        "staged_bytes": staged_bytes,
                    },
                )
            )

    def release_product_purge_claim(self, *, product_id: int, claim_token: str) -> bool:
        with self._sessions.begin() as session:
            product = session.execute(
                select(AnalysisProduct).where(AnalysisProduct.id == product_id).with_for_update()
            ).scalar_one_or_none()
            if product is None or product.purge_claim_token != claim_token:
                return False
            product.purge_claim_token = None
            product.purge_claim_expires_at = None
            return True

    def purge_disposition(self, *, kind: str, item_id: str, claim_token: str) -> str:
        """Describe recovery action: discard committed trash or restore an unfinished claim."""

        with self._sessions() as session:
            if kind == "session":
                capture = session.get(CaptureSession, item_id)
                if capture is not None and capture.state == SessionState.PURGED.value:
                    return "discard"
                if capture is not None and capture.purge_claim_token == claim_token:
                    return "restore"
                return "restore"
            if kind == "artifact":
                product = session.get(AnalysisProduct, int(item_id))
                if product is not None and not product.available:
                    return "discard"
                return "restore"
            raise ValueError(f"unknown purge kind: {kind}")

    def record_purge_discarded(
        self,
        *,
        session_id: str | None,
        kind: str,
        item_id: str,
        claim_token: str,
        bytes_reclaimed: int,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                RetentionEvent(
                    session_id=session_id,
                    event_type="trash_discarded",
                    bytes_reclaimed=bytes_reclaimed,
                    details={
                        "kind": kind,
                        "item_id": item_id,
                        "claim_token": claim_token,
                    },
                )
            )

    def reconcile_capture_session(
        self,
        *,
        session_id: str,
        source_type: str,
        bundle_uri: str,
        manifest_digest: str,
        allocated_bytes: int,
        attributes: dict[str, Any],
        tags: Iterable[str] = (),
        observed_start_at: datetime | None = None,
        observed_end_at: datetime | None = None,
        state: SessionState = SessionState.COMMITTED,
        streams: tuple[RadioStreamRegistration, ...] | None = None,
        path_authority: CapturePathAuthorityContract | None = None,
    ) -> bool:
        """Register one already committed bundle; return True only when inserted."""

        if allocated_bytes < 0:
            raise ValueError("allocated_bytes cannot be negative")
        if path_authority is not None:
            _validate_capture_authority_registration(
                path_authority,
                session_id=session_id,
                source_type=source_type,
                manifest_digest=manifest_digest,
                streams=streams,
            )
        canonical_tags = tuple(sorted(set(tags)))
        with self._sessions.begin() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": f"capture-session:{session_id}"},
            )
            capture = session.execute(
                select(CaptureSession).where(CaptureSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            profile_revision_id = (
                None
                if path_authority is None
                else _reconcile_manifest_profile_revision(
                    session, path_authority.verified_manifest_snapshot.recording_manifest
                )
            )
            if capture is not None:
                if (
                    capture.bundle_uri != bundle_uri
                    or capture.manifest_digest != manifest_digest
                    or capture.source_type != source_type
                    or capture.state == SessionState.PURGED.value
                ):
                    raise ProductConflictError(
                        f"recording bundle {session_id!r} conflicts with catalog identity"
                    )
                if profile_revision_id is not None and capture.profile_revision_id not in {
                    None,
                    profile_revision_id,
                }:
                    raise ProductConflictError("capture profile revision conflicts")
                if capture.profile_revision_id is None:
                    capture.profile_revision_id = profile_revision_id
                capture.allocated_bytes = allocated_bytes
                capture.raw_available = True
                capture.state = state.value
                if observed_start_at is not None:
                    capture.observed_start_at = observed_start_at
                if observed_end_at is not None:
                    capture.observed_end_at = observed_end_at
                _repair_capture_metadata(
                    session,
                    capture,
                    attributes=attributes,
                    tags=canonical_tags,
                )
                if streams is not None:
                    if path_authority is not None:
                        _reconcile_capture_path_authority(session, capture, path_authority)
                    _reconcile_radio_streams(
                        session,
                        session_id,
                        streams,
                        path_authority=path_authority,
                    )
                return False
            capture = CaptureSession(
                id=session_id,
                source_type=source_type,
                state=state.value,
                bundle_uri=bundle_uri,
                manifest_digest=manifest_digest,
                profile_revision_id=profile_revision_id,
                allocated_bytes=allocated_bytes,
                raw_available=True,
                attributes=attributes,
                observed_start_at=observed_start_at,
                observed_end_at=observed_end_at,
            )
            session.add(capture)
            session.flush()
            if streams is not None:
                if path_authority is not None:
                    _reconcile_capture_path_authority(session, capture, path_authority)
                _reconcile_radio_streams(
                    session,
                    session_id,
                    streams,
                    path_authority=path_authority,
                )
            _repair_capture_metadata(
                session,
                capture,
                attributes=attributes,
                tags=canonical_tags,
            )
            return True

    def capture_path_authority(self, session_id: str) -> CapturePathAuthorityRecord:
        with self._sessions() as session:
            row = session.get(CapturePathAuthority, session_id)
            if row is None:
                raise CatalogNotFoundError("capture path authority is absent")
            return _capture_path_authority_record(row)

    def seal_and_promote(
        self,
        *,
        run_id: str,
        manifest_uri: str,
        manifest_digest: str,
        summary: CurrentSummary,
    ) -> None:
        with self._sessions.begin() as session:
            now = _database_now(session)
            run = session.execute(
                select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update()
            ).scalar_one_or_none()
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {run_id}")
            if run.state not in {
                AnalysisRunState.PENDING.value,
                AnalysisRunState.RUNNING.value,
            }:
                raise PromotionError(f"analysis run is not active: {run.state}")
            unfinished = session.scalar(
                select(func.count())
                .select_from(ProcessingJob)
                .where(
                    ProcessingJob.run_id == run_id,
                    ProcessingJob.state != JobState.SUCCEEDED.value,
                )
            )
            if unfinished:
                raise PromotionError(f"analysis run has {unfinished} unfinished or failed jobs")

            run.state = AnalysisRunState.SUCCEEDED.value
            run.sealed_at = now
            run.manifest_uri = manifest_uri
            run.manifest_digest = manifest_digest
            if run.promotion_policy == PromotionPolicy.EVIDENCE_ONLY.value:
                return
            if run.promotion_policy != PromotionPolicy.CURRENT.value:
                raise PromotionError(
                    f"analysis run has unknown promotion policy: {run.promotion_policy!r}"
                )
            lane_values = {
                "session_id": run.session_id,
                "pipeline_lane": run.pipeline_lane,
                "run_id": run.id,
                "updated_at": now,
            }
            session.execute(
                insert(CurrentPipelineAnalysis)
                .values(**lane_values)
                .on_conflict_do_update(
                    index_elements=[
                        CurrentPipelineAnalysis.session_id,
                        CurrentPipelineAnalysis.pipeline_lane,
                    ],
                    set_={"run_id": run.id, "updated_at": now},
                )
            )
            if run.pipeline_lane == PipelineLane.RESEARCH.value:
                return
            current_values = {
                "session_id": run.session_id,
                "run_id": run.id,
                "updated_at": now,
            }
            session.execute(
                insert(CurrentAnalysis)
                .values(**current_values)
                .on_conflict_do_update(
                    index_elements=[CurrentAnalysis.session_id],
                    set_={"run_id": run.id, "updated_at": now},
                )
            )
            summary_values = {
                "session_id": run.session_id,
                "run_id": run.id,
                "mean_power_dbfs": summary.mean_power_dbfs,
                "best_qam_accuracy": summary.best_qam_accuracy,
                "best_cfo_hz": summary.best_cfo_hz,
                "doppler_slope_hz_s": summary.doppler_slope_hz_s,
                "candidate_count": summary.candidate_count,
                "coverage": summary.coverage,
                "details": summary.details,
                "updated_at": now,
            }
            session.execute(
                insert(AnalysisSummary)
                .values(**summary_values)
                .on_conflict_do_update(
                    index_elements=[AnalysisSummary.session_id],
                    set_={
                        key: value for key, value in summary_values.items() if key != "session_id"
                    },
                )
            )

    def fail_analysis_run(self, *, run_id: str, failure: str) -> None:
        with self._sessions.begin() as session:
            now = _database_now(session)
            run = session.execute(
                select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update()
            ).scalar_one_or_none()
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {run_id}")
            if run.state not in {
                AnalysisRunState.PENDING.value,
                AnalysisRunState.RUNNING.value,
            }:
                raise InvalidStateError(f"analysis run is not active: {run.state}")
            leased_jobs = session.execute(
                select(ProcessingJob)
                .where(
                    ProcessingJob.run_id == run_id,
                    ProcessingJob.state == JobState.LEASED.value,
                )
                .with_for_update()
            ).scalars()
            for job in leased_jobs:
                attempt = _current_attempt(session, job)
                attempt.state = AttemptState.FAILED.value
                attempt.completed_at = now
                attempt.error = "analysis run failed"
                job.state = JobState.CANCELLED.value
                _clear_lease(job)
            session.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.run_id == run_id,
                    ProcessingJob.state == JobState.PENDING.value,
                )
                .values(state=JobState.CANCELLED.value)
            )
            run.state = AnalysisRunState.FAILED.value
            run.failure = failure
            run.sealed_at = now

    def cancel_analysis_run(self, *, run_id: str, reason: str) -> bool:
        """Cancel queued work without stealing a live worker lease.

        Returns ``True`` for the transaction that changes the run and ``False``
        when the run was already cancelled. Completed attempts and products are
        intentionally preserved as immutable diagnostic evidence.
        """

        reason = reason.strip()
        if not reason:
            raise ValueError("analysis run cancellation reason cannot be empty")
        if len(reason) > 2048:
            raise ValueError("analysis run cancellation reason is too long")
        with self._sessions.begin() as session:
            now = _database_now(session)
            run = session.execute(
                select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update()
            ).scalar_one_or_none()
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {run_id}")
            if run.state == AnalysisRunState.CANCELLED.value:
                return False
            current = session.scalar(
                select(CurrentPipelineAnalysis.run_id).where(
                    CurrentPipelineAnalysis.run_id == run_id
                )
            )
            if current is not None:
                raise InvalidStateError("cannot cancel a session's current analysis run")
            if run.state not in {
                AnalysisRunState.PENDING.value,
                AnalysisRunState.RUNNING.value,
            }:
                raise InvalidStateError(f"analysis run is not active: {run.state}")
            jobs = tuple(
                session.scalars(
                    select(ProcessingJob)
                    .where(ProcessingJob.run_id == run_id)
                    .order_by(ProcessingJob.id)
                    .with_for_update()
                )
            )
            live_leases = tuple(
                job.id
                for job in jobs
                if job.state == JobState.LEASED.value
                and job.lease_expires_at is not None
                and job.lease_expires_at > now
            )
            if live_leases:
                raise InvalidStateError(
                    "analysis run has live worker leases: "
                    + ", ".join(str(job_id) for job_id in live_leases)
                )
            cancellation = f"analysis run cancelled: {reason}"
            for job in jobs:
                if job.state == JobState.LEASED.value:
                    attempt = _current_attempt(session, job)
                    attempt.state = AttemptState.EXPIRED.value
                    attempt.completed_at = now
                    attempt.error = cancellation
                    job.state = JobState.CANCELLED.value
                    job.error = cancellation
                    _clear_lease(job)
                elif job.state == JobState.PENDING.value:
                    job.state = JobState.CANCELLED.value
                    job.error = cancellation
            run.state = AnalysisRunState.CANCELLED.value
            run.failure = reason
            run.sealed_at = now
            return True

    def stop_and_fence_release(
        self,
        *,
        operation_id: str,
        pipeline_release_id: str,
        operator_id: str,
        reason: str,
        expected_run_ids: tuple[str, ...] | None,
    ) -> ProcessingFenceResult:
        """Atomically revoke an exact release's active processing authority.

        This is the catalog half of a fast cutover. Operators stop/kill the old
        worker cgroups first, then call this operation instead of waiting for
        leases to expire. A release-scoped advisory lock closes the claim race;
        job row locks close publication, heartbeat, and completion races.
        Scientific products and already-succeeded jobs are never modified.
        """

        operation_id = operation_id.strip()
        pipeline_release_id = pipeline_release_id.strip()
        operator_id = operator_id.strip()
        reason = reason.strip()
        if not operation_id or len(operation_id) > 128:
            raise ValueError("fence operation ID must contain at most 128 characters")
        if not pipeline_release_id or len(pipeline_release_id) > 128:
            raise ValueError("fence pipeline release ID must contain at most 128 characters")
        if not operator_id or len(operator_id) > 128:
            raise ValueError("fence operator ID must contain at most 128 characters")
        if not reason or len(reason) > 2048:
            raise ValueError("fence reason must contain at most 2048 characters")
        expected = None if expected_run_ids is None else tuple(sorted(set(expected_run_ids)))
        if expected_run_ids is not None and (
            not expected or expected != tuple(sorted(expected_run_ids))
        ):
            raise ValueError("expected run IDs must be non-empty, unique, and ordered")

        with self._sessions.begin() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"processing-release:{pipeline_release_id}"},
            )
            prior = session.get(ProcessingFenceEvent, operation_id)
            if prior is not None:
                if (
                    prior.pipeline_release_id != pipeline_release_id
                    or prior.operator_id != operator_id
                    or prior.reason != reason
                    or (expected is not None and tuple(prior.run_ids) != expected)
                ):
                    raise InvalidStateError("fence operation ID conflicts with its prior request")
                return _processing_fence_result(prior, changed=False)
            if session.get(PipelineRelease, pipeline_release_id) is None:
                raise CatalogNotFoundError(f"pipeline release is absent: {pipeline_release_id}")

            runs = tuple(
                session.scalars(
                    select(AnalysisRun)
                    .where(
                        AnalysisRun.pipeline_release_id == pipeline_release_id,
                        AnalysisRun.state.in_(
                            (AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value)
                        ),
                    )
                    .order_by(AnalysisRun.id)
                    .with_for_update()
                )
            )
            run_ids = tuple(run.id for run in runs)
            if expected is not None and run_ids != expected:
                raise InvalidStateError(
                    "active run inventory differs from exact confirmation; expected "
                    f"{expected!r}, found {run_ids!r}"
                )

            jobs = (
                ()
                if not run_ids
                else tuple(
                    session.scalars(
                        select(ProcessingJob)
                        .where(ProcessingJob.run_id.in_(run_ids))
                        .order_by(ProcessingJob.id)
                        .with_for_update()
                    )
                )
            )
            now = _database_now(session)
            cancellation = f"administratively fenced release {pipeline_release_id}: {reason}"
            cancelled_jobs = 0
            expired_attempts = 0
            preserved_succeeded = 0
            for job in jobs:
                if job.state == JobState.LEASED.value:
                    attempt = _current_attempt(session, job)
                    attempt.state = AttemptState.EXPIRED.value
                    attempt.completed_at = now
                    attempt.error = cancellation
                    job.state = JobState.CANCELLED.value
                    job.error = cancellation
                    _clear_lease(job)
                    cancelled_jobs += 1
                    expired_attempts += 1
                elif job.state == JobState.PENDING.value:
                    job.state = JobState.CANCELLED.value
                    job.error = cancellation
                    cancelled_jobs += 1
                elif job.state == JobState.SUCCEEDED.value:
                    preserved_succeeded += 1
            for run in runs:
                run.state = AnalysisRunState.CANCELLED.value
                run.failure = reason
                run.sealed_at = now
            preserved_products = (
                int(
                    session.scalar(
                        select(func.count())
                        .select_from(AnalysisProduct)
                        .where(AnalysisProduct.run_id.in_(run_ids))
                    )
                    or 0
                )
                if run_ids
                else 0
            )
            event = ProcessingFenceEvent(
                operation_id=operation_id,
                pipeline_release_id=pipeline_release_id,
                operator_id=operator_id,
                reason=reason,
                run_ids=list(run_ids),
                cancelled_run_count=len(runs),
                cancelled_job_count=cancelled_jobs,
                expired_attempt_count=expired_attempts,
                preserved_succeeded_job_count=preserved_succeeded,
                preserved_product_count=preserved_products,
            )
            session.add(event)
            session.flush()
            return _processing_fence_result(event, changed=True)

    def search_sessions(
        self, query: SessionSearch | None = None
    ) -> tuple[SessionSearchResult, ...]:
        query = SessionSearch() if query is None else query
        if query.limit <= 0 or query.limit > 1000:
            raise ValueError("search limit must be between 1 and 1000")
        if query.cursor < 0:
            raise ValueError("search cursor cannot be negative")
        with self._sessions() as session:
            active_hold = exists(
                select(1).where(
                    RetentionHold.session_id == CaptureSession.id,
                    RetentionHold.released_at.is_(None),
                )
            )
            statement: Select[tuple[CaptureSession, str, bool]] = (
                select(CaptureSession, CurrentAnalysis.run_id, active_hold.label("held"))
                .outerjoin(CurrentAnalysis, CurrentAnalysis.session_id == CaptureSession.id)
                .order_by(
                    func.coalesce(
                        CaptureSession.observed_start_at,
                        CaptureSession.created_at,
                    ).desc(),
                    CaptureSession.id,
                )
                .limit(query.limit)
                .offset(query.cursor)
            )
            if query.query is not None and query.query.strip():
                statement = statement.where(
                    func.lower(CaptureSession.id).contains(query.query.casefold().strip())
                )
            if query.source_type is not None:
                statement = statement.where(CaptureSession.source_type == query.source_type)
            if query.state is not None:
                statement = statement.where(CaptureSession.state == query.state)
            if query.created_after is not None:
                statement = statement.where(
                    func.coalesce(CaptureSession.observed_start_at, CaptureSession.created_at)
                    >= query.created_after
                )
            if query.created_before is not None:
                statement = statement.where(
                    func.coalesce(CaptureSession.observed_start_at, CaptureSession.created_at)
                    < query.created_before
                )
            if query.tag is not None:
                statement = statement.where(
                    exists(
                        select(1).where(
                            SessionTag.session_id == CaptureSession.id,
                            SessionTag.tag_name == query.tag,
                        )
                    )
                )
            if query.held is not None:
                statement = statement.where(active_hold if query.held else ~active_hold)
            rows = session.execute(statement).all()
            session_ids = tuple(row[0].id for row in rows)
            tags_by_session: dict[str, list[str]] = {session_id: [] for session_id in session_ids}
            if session_ids:
                for session_id, tag_name in session.execute(
                    select(SessionTag.session_id, SessionTag.tag_name)
                    .where(SessionTag.session_id.in_(session_ids))
                    .order_by(SessionTag.session_id, SessionTag.tag_name)
                ):
                    tags_by_session[session_id].append(tag_name)
            return tuple(
                SessionSearchResult(
                    session_id=capture.id,
                    source_type=capture.source_type,
                    state=capture.state,
                    created_at=capture.observed_start_at or capture.created_at,
                    bundle_uri=capture.bundle_uri,
                    held=held,
                    tags=tuple(tags_by_session[capture.id]),
                    current_run_id=current_run_id,
                )
                for capture, current_run_id, held in rows
            )

    def recording_list_page(
        self,
        *,
        query: str | None,
        include_test: bool,
        analysis_state: str | None,
        storage_state: str | None,
        held: bool | None,
        tag: str | None,
        cursor: int,
        limit: int,
    ) -> RecordingListPage:
        """Return one list page without opening recording or analysis artifacts."""

        if cursor < 0:
            raise ValueError("recording cursor cannot be negative")
        if not 1 <= limit <= 100:
            raise ValueError("recording limit must be between 1 and 100")
        needle = query.casefold().strip() if query else None
        with self._sessions.begin() as session:
            _begin_consistent_read(session)
            active_hold = exists(
                select(1).where(
                    RetentionHold.session_id == CaptureSession.id,
                    RetentionHold.released_at.is_(None),
                )
            )
            tag_match = exists(
                select(1).where(
                    SessionTag.session_id == CaptureSession.id,
                    SessionTag.tag_name == tag,
                )
            )
            search_match = None
            if needle:
                presentation = CaptureSession.attributes["presentation"]
                search_match = (
                    func.lower(CaptureSession.id).contains(needle)
                    | func.lower(presentation["title"].astext).contains(needle)
                    | func.lower(presentation["profile_name"].astext).contains(needle)
                    | exists(
                        select(1).where(
                            SessionTag.session_id == CaptureSession.id,
                            func.lower(SessionTag.tag_name).contains(needle),
                        )
                    )
                )
            filters = []
            if not include_test:
                filters.append(CaptureSession.source_type != "test")
            if storage_state == "purged":
                filters.append(CaptureSession.state == "purged")
            elif storage_state == "available":
                filters.append(CaptureSession.state != "purged")
            if held is not None:
                filters.append(active_hold if held else ~active_hold)
            if tag is not None:
                filters.append(tag_match)
            if search_match is not None:
                filters.append(search_match)

            current_run = aliased(CurrentAnalysis)
            run = aliased(AnalysisRun)
            latest_run_id = (
                select(AnalysisRun.id)
                .where(AnalysisRun.session_id == CaptureSession.id)
                .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
                .limit(1)
                .correlate(CaptureSession)
                .scalar_subquery()
            )
            effective_run_id = func.coalesce(current_run.run_id, latest_run_id)
            base = (
                select(CaptureSession.id)
                .outerjoin(current_run, current_run.session_id == CaptureSession.id)
                .outerjoin(run, run.id == effective_run_id)
                .where(*filters)
            )
            if analysis_state is not None:
                outcome_exists = exists(
                    select(1).where(
                        ProcessingJob.run_id == run.id,
                        ProcessingJob.outcome.is_not(None),
                    )
                )
                partial_exists = exists(
                    select(1).where(
                        ProcessingJob.run_id == run.id,
                        ProcessingJob.outcome.in_(("partial_coverage", "insufficient_data")),
                    )
                )
                only_no_result = ~exists(
                    select(1).where(
                        ProcessingJob.run_id == run.id,
                        ProcessingJob.outcome.is_not(None),
                        ProcessingJob.outcome.not_in(("no_result", "insufficient_data")),
                    )
                )
                is_current = current_run.run_id.is_not(None)
                analysis_predicates = {
                    "queued": run.state == "pending",
                    "running": run.state == "running",
                    "failed": run.state == "failed",
                    "no_result": is_current & outcome_exists & only_no_result,
                    "partial": is_current & partial_exists & ~only_no_result,
                    "complete": (
                        is_current
                        & (run.state == "succeeded")
                        & ~partial_exists
                        & ~(outcome_exists & only_no_result)
                    ),
                }
                predicate = analysis_predicates.get(analysis_state)
                if predicate is None:
                    predicate = run.id.is_(None)
                base = base.where(predicate)

            total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
            ordered = (
                base.order_by(
                    func.coalesce(
                        CaptureSession.observed_start_at, CaptureSession.created_at
                    ).desc(),
                    CaptureSession.id,
                )
                .offset(cursor)
                .limit(limit)
            )
            selected_ids = tuple(session.scalars(ordered))
            rows = _recording_list_rows(session, selected_ids)
            return RecordingListPage(rows=rows, total=total)

    def current_run_id(
        self,
        session_id: str,
        pipeline_lane: PipelineLane | str = PipelineLane.STANDARD,
    ) -> str | None:
        lane = PipelineLane(pipeline_lane)
        with self._sessions() as session:
            return session.scalar(
                select(CurrentPipelineAnalysis.run_id).where(
                    CurrentPipelineAnalysis.session_id == session_id,
                    CurrentPipelineAnalysis.pipeline_lane == lane.value,
                )
            )

    def active_run_id(
        self,
        session_id: str,
        pipeline_lane: PipelineLane | str = PipelineLane.STANDARD,
    ) -> str | None:
        """Return the lane's unique pending/running run without changing state."""

        lane = PipelineLane(pipeline_lane)
        with self._sessions() as session:
            return session.scalar(
                select(AnalysisRun.id).where(
                    AnalysisRun.session_id == session_id,
                    AnalysisRun.pipeline_lane == lane.value,
                    AnalysisRun.state.in_(
                        (AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value)
                    ),
                )
            )

    def presentation_snapshot(
        self,
        session_id: str,
        pipeline_lane: PipelineLane | str = PipelineLane.STANDARD,
    ) -> CatalogSessionReadSnapshot | None:
        """Resolve one immutable current-run view in a read-only transaction."""

        lane = PipelineLane(pipeline_lane)
        with self._sessions.begin() as session:
            _begin_consistent_read(session)
            return _presentation_snapshot(session, session_id, pipeline_lane=lane)

    def presentation_snapshots(
        self, *, limit: int = 1000
    ) -> tuple[CatalogSessionReadSnapshot, ...]:
        if limit <= 0 or limit > 1000:
            raise ValueError("presentation snapshot limit must be between 1 and 1000")
        with self._sessions.begin() as session:
            _begin_consistent_read(session)
            session_ids = tuple(
                session.scalars(
                    select(CaptureSession.id)
                    .order_by(CaptureSession.created_at.desc(), CaptureSession.id)
                    .limit(limit)
                )
            )
            return tuple(
                snapshot
                for session_id in session_ids
                if (snapshot := _presentation_snapshot(session, session_id)) is not None
            )

    def presentation_snapshot_for_product(
        self, product_id: int
    ) -> CatalogSessionReadSnapshot | None:
        """Resolve a product only when its run is the session's current run."""

        with self._sessions.begin() as session:
            _begin_consistent_read(session)
            session_id = session.scalar(
                select(CurrentAnalysis.session_id)
                .join(AnalysisProduct, AnalysisProduct.run_id == CurrentAnalysis.run_id)
                .where(AnalysisProduct.id == product_id)
            )
            if session_id is None:
                return None
            return _presentation_snapshot(session, session_id)

    def backlog_snapshot(self) -> CatalogBacklogSnapshot:
        with self._sessions.begin() as session:
            _begin_consistent_read(session)
            now = _database_now(session)
            queued = session.scalar(
                select(func.count())
                .select_from(ProcessingJob)
                .where(ProcessingJob.state == JobState.PENDING.value)
            )
            running = session.scalar(
                select(func.count())
                .select_from(ProcessingJob)
                .where(
                    ProcessingJob.state == JobState.LEASED.value,
                    ProcessingJob.lease_expires_at > now,
                )
            )
            failed = session.scalar(
                select(func.count())
                .select_from(ProcessingJob)
                .where(ProcessingJob.state == JobState.FAILED.value)
            )
            oldest = session.scalar(
                select(func.min(ProcessingJob.created_at)).where(
                    ProcessingJob.state == JobState.PENDING.value
                )
            )
            return CatalogBacklogSnapshot(
                queued=int(queued or 0),
                running=int(running or 0),
                failed=int(failed or 0),
                oldest_queued_seconds=(
                    None if oldest is None else max(0.0, (now - oldest).total_seconds())
                ),
            )

    def ready_run_ids(self, *, limit: int = 100) -> tuple[str, ...]:
        """Return active runs whose non-empty job DAG is fully successful.

        Workers use this narrow recovery query to seal runs after a restart in
        the crash window between completing the final job and atomic promotion.
        """

        if limit <= 0 or limit > 1000:
            raise ValueError("ready-run limit must be between 1 and 1000")
        with self._sessions.begin() as session:
            _begin_consistent_read(session)
            has_jobs = exists(select(1).where(ProcessingJob.run_id == AnalysisRun.id))
            has_unfinished_jobs = exists(
                select(1).where(
                    ProcessingJob.run_id == AnalysisRun.id,
                    ProcessingJob.state != JobState.SUCCEEDED.value,
                )
            )
            return tuple(
                session.scalars(
                    select(AnalysisRun.id)
                    .where(
                        AnalysisRun.state.in_(
                            [AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value]
                        ),
                        has_jobs,
                        ~has_unfinished_jobs,
                    )
                    .order_by(AnalysisRun.created_at, AnalysisRun.id)
                    .limit(limit)
                )
            )

    def failed_run_ids(self, *, limit: int = 100) -> tuple[str, ...]:
        """Return active runs containing a terminally failed processing job."""

        if limit <= 0 or limit > 1000:
            raise ValueError("failed-run limit must be between 1 and 1000")
        with self._sessions.begin() as session:
            _begin_consistent_read(session)
            has_failed_job = exists(
                select(1).where(
                    ProcessingJob.run_id == AnalysisRun.id,
                    ProcessingJob.state == JobState.FAILED.value,
                )
            )
            return tuple(
                session.scalars(
                    select(AnalysisRun.id)
                    .where(
                        AnalysisRun.state.in_(
                            [AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value]
                        ),
                        has_failed_job,
                    )
                    .order_by(AnalysisRun.created_at, AnalysisRun.id)
                    .limit(limit)
                )
            )

    def run_execution_info(self, run_id: str) -> RunExecutionInfo:
        with self._sessions() as session:
            row = session.execute(
                select(AnalysisRun, CaptureSession, PipelineRelease)
                .join(CaptureSession, CaptureSession.id == AnalysisRun.session_id)
                .join(PipelineRelease, PipelineRelease.id == AnalysisRun.pipeline_release_id)
                .where(AnalysisRun.id == run_id)
            ).one_or_none()
            if row is None:
                raise CatalogNotFoundError(f"analysis run is absent: {run_id}")
            run, capture, release = row
            if capture.bundle_uri is None:
                raise InvalidStateError(
                    f"capture session has no committed bundle URI: {capture.id}"
                )
            return RunExecutionInfo(
                run_id=run.id,
                session_id=run.session_id,
                pipeline_release_id=run.pipeline_release_id,
                pipeline_configuration=release.configuration,
                input_manifest_digest=run.input_manifest_digest,
                trigger=run.trigger,
                promotion_policy=run.promotion_policy,
                pipeline_lane=run.pipeline_lane,
                bundle_uri=capture.bundle_uri,
                code_revision=release.code_revision,
                environment_digest=release.environment_digest,
                graph_digest=release.graph_digest,
                configuration_digest=release.configuration_digest,
                executable_digest=release.executable_digest,
                expanded_plan_digest=run.expanded_plan_digest,
                raw_integrity_attestation_digest=(
                    None
                    if run.raw_integrity_attestation_id is None
                    else session.scalar(
                        select(RawIntegrityAttestation.attestation_digest).where(
                            RawIntegrityAttestation.id == run.raw_integrity_attestation_id
                        )
                    )
                ),
                raw_integrity_attestation=(
                    None
                    if run.raw_integrity_attestation_id is None
                    else session.scalar(
                        select(RawIntegrityAttestation.document).where(
                            RawIntegrityAttestation.id == run.raw_integrity_attestation_id
                        )
                    )
                ),
            )

    def run_subject_binding(self, run_id: str, scope: ScopeIdentityV1) -> RunSubjectBindingRecord:
        """Read and independently replay one immutable run-owned snapshot."""

        with self._sessions() as session:
            row = session.execute(
                select(RunSubjectBinding, AnalysisScope)
                .join(AnalysisScope, AnalysisScope.id == RunSubjectBinding.scope_id)
                .where(
                    RunSubjectBinding.run_id == run_id,
                    AnalysisScope.canonical_digest == scope.canonical_digest,
                )
            ).one_or_none()
            if row is None:
                raise CatalogNotFoundError("run subject binding is absent")
            binding, stored_scope = row
            exact_scope = _scope_identity(stored_scope)
            if exact_scope != scope:
                raise InvalidStateError("run subject scope digest aliases different content")
            expected_snapshot = canonical_digest(
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "scope": scope.model_dump(mode="json"),
                    "kind": binding.kind,
                    "binding_digest": binding.binding_digest,
                    "document": binding.document,
                }
            )
            if expected_snapshot != binding.snapshot_digest:
                raise InvalidStateError("run subject snapshot digest does not replay")
            return RunSubjectBindingRecord(
                run_id=run_id,
                scope=scope,
                kind=binding.kind,
                binding_digest=binding.binding_digest,
                snapshot_digest=binding.snapshot_digest,
                document=binding.document,
            )

    def run_manifest_reference(self, run_id: str) -> RunManifestReference:
        with self._sessions() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {run_id}")
            if run.manifest_uri is None or run.manifest_digest is None:
                raise InvalidStateError(f"analysis run is not sealed: {run_id}")
            return RunManifestReference(
                logical_uri=run.manifest_uri,
                digest=run.manifest_digest,
            )

    def run_seal_snapshot(self, run_id: str) -> RunSealSnapshot:
        execution = self.run_execution_info(run_id)
        with self._sessions() as session:
            jobs = tuple(
                CatalogJobRecord(
                    job_id=job.id,
                    stage_key=job.stage_key,
                    scope_key=job.scope_key,
                    state=job.state,
                    outcome=job.outcome,
                    scope_id=job.scope_id,
                    scope=(
                        None
                        if job.scope_id is None
                        else _scope_identity(session.get(AnalysisScope, job.scope_id))
                    ),
                    node_id=job.node_id,
                    resource_class=job.resource_class,
                    iq_access=job.iq_access,
                )
                for job in session.scalars(
                    select(ProcessingJob)
                    .where(ProcessingJob.run_id == run_id)
                    .order_by(ProcessingJob.id)
                )
            )
            products = tuple(
                CatalogProductRecord(
                    product_id=product.id,
                    run_id=product.run_id,
                    stage_key=product.stage_key,
                    scope_key=product.scope_key,
                    kind=product.kind,
                    schema_version=product.schema_version,
                    role=product.role,
                    status=product.status,
                    media_type=product.media_type,
                    logical_uri=product.logical_uri,
                    digest=product.digest,
                    byte_size=product.byte_size,
                    available=product.available,
                    coverage=product.coverage,
                    summary=product.summary,
                    scope_id=product.scope_id,
                    scope=(
                        None
                        if product.scope_id is None
                        else _scope_identity(session.get(AnalysisScope, product.scope_id))
                    ),
                    derivation_output_id=product.derivation_output_id,
                    derivation_mode=product.derivation_mode,
                    reused_from_product_id=product.reused_from_product_id,
                )
                for product in session.scalars(
                    select(AnalysisProduct)
                    .where(AnalysisProduct.run_id == run_id)
                    .order_by(
                        AnalysisProduct.stage_key,
                        AnalysisProduct.scope_key,
                        AnalysisProduct.kind,
                        AnalysisProduct.schema_version,
                    )
                )
            )
            return RunSealSnapshot(execution=execution, jobs=jobs, products=products)

    def product_dependency_closure(self, product_id: int) -> tuple[CatalogProductRecord, ...]:
        """Return the exact root-plus-input provenance closure in stable ID order."""

        with self._sessions() as session:
            products = _lock_campaign_product_closure(session, product_id)
            return tuple(_catalog_product_record(products[item]) for item in sorted(products))

    def product_direct_dependencies(self, product_id: int) -> tuple[CatalogProductRecord, ...]:
        """Return exact direct ProductReader inputs in stable product-ID order."""

        with self._sessions() as session:
            product = session.get(AnalysisProduct, product_id)
            if product is None:
                raise CatalogNotFoundError(f"analysis product is absent: {product_id}")
            inputs = tuple(
                session.scalars(
                    select(AnalysisProduct)
                    .join(
                        ProductDependency,
                        ProductDependency.input_product_id == AnalysisProduct.id,
                    )
                    .where(ProductDependency.product_id == product_id)
                    .order_by(AnalysisProduct.id)
                )
            )
            return tuple(_catalog_product_record(item) for item in inputs)

    def authorized_job_input_products(
        self, job_id: int
    ) -> tuple[tuple[str | None, CatalogProductRecord], ...]:
        """Return products from only the exact producer nodes in a job's persisted plan."""

        producer = aliased(ProcessingJob)
        with self._sessions() as session:
            job = session.get(ProcessingJob, job_id)
            if job is None:
                raise CatalogNotFoundError(f"processing job is absent: {job_id}")
            rows = session.execute(
                select(producer.node_id, AnalysisProduct)
                .join(
                    ProcessingJobDependency,
                    ProcessingJobDependency.depends_on_job_id == producer.id,
                )
                .join(
                    AnalysisProduct,
                    (AnalysisProduct.run_id == producer.run_id)
                    & (AnalysisProduct.stage_key == producer.stage_key)
                    & (AnalysisProduct.scope_key == producer.scope_key),
                )
                .where(
                    ProcessingJobDependency.job_id == job_id,
                    ProcessingJobDependency.requires_product.is_(True),
                    producer.state == JobState.SUCCEEDED.value,
                    AnalysisProduct.available.is_(True),
                )
                .order_by(
                    producer.node_id,
                    AnalysisProduct.kind,
                    AnalysisProduct.schema_version,
                    AnalysisProduct.id,
                )
            )
            return tuple(
                (node_id, _catalog_product_record(product, session=session))
                for node_id, product in rows
            )

    def run_state(self, run_id: str) -> AnalysisRunState:
        with self._sessions() as session:
            value = session.scalar(select(AnalysisRun.state).where(AnalysisRun.id == run_id))
            if value is None:
                raise CatalogNotFoundError(f"analysis run is absent: {run_id}")
            return AnalysisRunState(value)

    def job_state(self, job_id: int) -> JobState:
        with self._sessions() as session:
            value = session.scalar(select(ProcessingJob.state).where(ProcessingJob.id == job_id))
            if value is None:
                raise CatalogNotFoundError(f"processing job is absent: {job_id}")
            return JobState(value)

    def attempt_states(self, job_id: int) -> tuple[AttemptState, ...]:
        with self._sessions() as session:
            values = session.scalars(
                select(ProcessingJobAttempt.state)
                .where(ProcessingJobAttempt.job_id == job_id)
                .order_by(ProcessingJobAttempt.attempt_number)
            )
            return tuple(AttemptState(value) for value in values)


def _validate_subject_binding_document(
    session: Session,
    scope: ScopeIdentityV1,
    document: dict[str, Any],
    *,
    run_id: str,
    manifest_digest: str,
    attestation_digest: str | None,
) -> tuple[str, str]:
    run = session.get(AnalysisRun, run_id)
    release = None if run is None else session.get(PipelineRelease, run.pipeline_release_id)
    if run is None or release is None:
        raise InvalidStateError("subject snapshot run release is absent")
    if scope.kind.value == "receiver_path":
        binding_schema_version = document.get("schema_version")
        if binding_schema_version == 3:
            path_binding: (
                StandardPathInputBindV3 | StandardPathInputBindV4 | StandardPathInputBindV5
            ) = StandardPathInputBindV3.model_validate(document)
        elif binding_schema_version == 4:
            path_binding = StandardPathInputBindV4.model_validate(document)
        elif binding_schema_version == 5:
            path_binding = StandardPathInputBindV5.model_validate(document)
        else:
            raise InvalidStateError("receiver-path snapshot schema version is unsupported")
        lineage = session.get(
            CaptureReceiverLineage,
            (scope.session_id, scope.stream_id, scope.receiver_id),
        )
        stream = session.get(RadioStream, (scope.session_id, scope.stream_id))
        capture = session.get(CaptureSession, scope.session_id)
        profile = (
            None
            if capture is None or capture.profile_revision_id is None
            else session.get(CaptureProfileRevision, capture.profile_revision_id)
        )
        attestation = session.execute(
            select(RawIntegrityAttestation).where(
                RawIntegrityAttestation.attestation_digest == attestation_digest
            )
        ).scalar_one_or_none()
        raw_streams = () if attestation is None else attestation.document.get("streams", ())
        raw_stream = next(
            (item for item in raw_streams if item.get("stream_id") == scope.stream_id),
            None,
        )
        authority = session.get(CapturePathAuthority, scope.session_id)
        bounds = None if stream is None else _stream_observed_bounds_ns(stream.attributes)
        authority_contract: CapturePathAuthorityContract | None = None
        authority_manifest: (
            RecordingManifestV1
            | RecordingManifestV3
            | RecordingManifestV4
            | RecordingManifestV5
            | RecordingManifestV6
            | None
        ) = None
        manifest_stream = None
        if authority is not None:
            authority_contract = (
                parse_capture_hardware_binding(authority.document)
                if authority.authority_kind == "station"
                else FixturePathAuthorityV1.model_validate(authority.document)
            )
            authority_manifest = authority_contract.verified_manifest_snapshot.recording_manifest
            manifest_stream = next(
                (item for item in authority_manifest.streams if item.stream_id == scope.stream_id),
                None,
            )
        protected_fixture = (
            authority is not None
            and authority.authority_kind == "protected_test_fixture"
            and authority.evidence_only
            and not authority.physical_association_permitted
            and not authority.calibration_association_permitted
            and not authority.promotion_permitted
        )
        expected_resolution = "legacy_unresolved" if protected_fixture else "resolved"
        expected_starlink_tuning = (
            None
            if authority_manifest is None or scope.stream_id is None
            else resolve_manifest_starlink_tuning(authority_manifest).get(scope.stream_id)
        )
        expected_profile_revision_digest = None if profile is None else profile.digest
        if isinstance(authority_manifest, RecordingManifestV4) and manifest_stream is not None:
            expected_profile_revision_digest = next(
                (
                    leg.profile_revision.revision_digest
                    for leg in authority_manifest.capture_plan.radio_plans
                    if leg.radio_id == manifest_stream.radio.radio_id
                ),
                None,
            )
        expected_frequency = (
            None
            if lineage is None or bounds is None or manifest_stream is None
            else _frequency_reference_for_lineage(
                session,
                lineage,
                authority,
                tuned_center_frequency_hz=manifest_stream.applied_settings.center_frequency_hz
                if manifest_stream.applied_settings is not None
                else -1,
                capture_start_utc_ns=bounds[0],
                capture_end_utc_ns=bounds[1],
            )
        )
        if isinstance(path_binding, StandardPathInputBindV4):
            if isinstance(
                authority_manifest,
                (RecordingManifestV3, RecordingManifestV4),
            ) and isinstance(manifest_stream, RecordingStreamV3):
                manifest_timing = manifest_stream.timing
                manifest_settings = manifest_stream.applied_settings
                path_geometry_disagrees = (
                    path_binding.sample_rate_hz != manifest_settings.sample_rate_hz
                    or path_binding.rf_bandwidth_hz != manifest_settings.bandwidth_hz
                    or path_binding.declared_sample_count != manifest_stream.logical_sample_count
                    or path_binding.requested_sample_count != manifest_stream.requested_sample_count
                    or path_binding.logical_sample_count != manifest_stream.logical_sample_count
                    or path_binding.observed_sample_count != manifest_stream.observed_sample_count
                    or path_binding.missing_sample_count != manifest_stream.zero_fill_sample_count
                    or path_binding.observed_iq_digest != manifest_stream.observed_iq_sha256
                    or path_binding.logical_iq_digest != manifest_stream.logical_iq_sha256
                    or path_binding.timeline_sha256 != manifest_stream.timeline_sha256
                    or path_binding.gap_map_sha256 != manifest_stream.gap_map_sha256
                    or path_binding.validity_inventory_sha256
                    != manifest_stream.validity_inventory_sha256
                    or path_binding.first_device_sample_counter
                    != manifest_stream.continuity.first_device_sample_counter
                    or stream is None
                    or stream.captured_sample_count != manifest_stream.observed_sample_count
                    or path_binding.timing.first_estimate_utc_ns
                    != manifest_timing.first_sample.estimate_utc_ns
                    or path_binding.timing.first_earliest_utc_ns
                    != manifest_timing.first_sample.earliest_utc_ns
                    or path_binding.timing.first_latest_utc_ns
                    != manifest_timing.first_sample.latest_utc_ns
                    or path_binding.timing.last_estimate_utc_ns
                    != manifest_timing.last_sample.estimate_utc_ns
                    or path_binding.timing.last_earliest_utc_ns
                    != manifest_timing.last_sample.earliest_utc_ns
                    or path_binding.timing.last_latest_utc_ns
                    != manifest_timing.last_sample.latest_utc_ns
                )
            elif isinstance(authority_manifest, RecordingManifestV2) and isinstance(
                manifest_stream, RecordingStreamV2
            ):
                manifest_timing = manifest_stream.timing
                manifest_settings = manifest_stream.applied_settings
                continuity = manifest_stream.continuity
                invalid_digest_relation = (
                    path_binding.observed_iq_digest != path_binding.logical_iq_digest
                    if continuity.missing_sample_count == 0
                    else path_binding.observed_iq_digest == path_binding.logical_iq_digest
                )
                path_geometry_disagrees = (
                    manifest_settings is None
                    or manifest_timing is None
                    or path_binding.sample_rate_hz != manifest_settings.sample_rate_hz
                    or path_binding.rf_bandwidth_hz != manifest_settings.bandwidth_hz
                    or path_binding.declared_sample_count != continuity.device_span_sample_count
                    or path_binding.requested_sample_count != manifest_stream.requested_sample_count
                    or path_binding.logical_sample_count != continuity.device_span_sample_count
                    or path_binding.observed_sample_count != manifest_stream.captured_sample_count
                    or path_binding.missing_sample_count != continuity.missing_sample_count
                    or path_binding.timeline_sha256 != manifest_stream.timeline_sha256
                    or path_binding.gap_map_sha256 != manifest_stream.gap_map_sha256
                    or path_binding.validity_inventory_sha256
                    != path_binding.validity_inventory.inventory_digest
                    or path_binding.first_device_sample_counter
                    != continuity.first_device_sample_counter
                    or len(path_binding.validity_inventory.segments) != continuity.segment_count
                    or continuity.overflow_count != 0
                    or continuity.enqueue_failure_count != 0
                    or continuity.terminal_enqueue_failure is not None
                    or continuity.terminal_rejected_gap_count != 0
                    or continuity.terminal_rejected_missing_sample_count != 0
                    or continuity.terminal_rejected_overflow_count != 0
                    or invalid_digest_relation
                    or stream is None
                    or stream.captured_sample_count != manifest_stream.captured_sample_count
                    or path_binding.timing.first_estimate_utc_ns
                    != manifest_timing.first_sample.estimate_utc_ns
                    or path_binding.timing.first_earliest_utc_ns
                    != manifest_timing.first_sample.earliest_utc_ns
                    or path_binding.timing.first_latest_utc_ns
                    != manifest_timing.first_sample.latest_utc_ns
                    or path_binding.timing.last_estimate_utc_ns
                    != manifest_timing.last_sample.estimate_utc_ns
                    or path_binding.timing.last_earliest_utc_ns
                    != manifest_timing.last_sample.earliest_utc_ns
                    or path_binding.timing.last_latest_utc_ns
                    != manifest_timing.last_sample.latest_utc_ns
                )
            else:
                path_geometry_disagrees = True
        else:
            # V3 keeps the historical packed-observed-IQ count semantics and
            # cannot be used to reinterpret a V3 device-axis recording.
            path_geometry_disagrees = (
                isinstance(authority_manifest, (RecordingManifestV3, RecordingManifestV4))
                or isinstance(manifest_stream, RecordingStreamV3)
                or stream is None
                or path_binding.declared_sample_count != stream.captured_sample_count
            )
        if (
            path_binding.session_id != scope.session_id
            or path_binding.stream_id != scope.stream_id
            or path_binding.receiver_id != scope.receiver_id
            or path_binding.manifest_digest != manifest_digest
            or path_binding.raw_integrity_attestation_digest != attestation_digest
            or lineage is None
            or stream is None
            or profile is None
            or authority is None
            or authority_contract is None
            or authority_manifest is None
            or manifest_stream is None
            or bounds is None
            or expected_frequency is None
            or path_binding.capture_lineage_resolution != expected_resolution
            or (not protected_fixture and lineage.lineage_status != "resolved")
            or (protected_fixture and lineage.lineage_status != "unresolved")
            or path_binding.radio_id != lineage.radio_id
            or path_binding.physical_receiver_id != lineage.physical_receiver_id
            or path_binding.hardware_epoch_id != lineage.hardware_epoch_external_id
            or path_binding.profile_revision_digest != expected_profile_revision_digest
            or path_binding.capture_plan_digest != authority_manifest.capture_plan.plan_digest
            or expected_starlink_tuning is None
            or path_binding.starlink_channel != expected_starlink_tuning.channel
            or path_binding.starlink_edge is not expected_starlink_tuning.edge
            or path_binding.starlink_tuning_evidence_source
            != expected_starlink_tuning.evidence_source
            or path_binding.selected_stream_digest
            != canonical_digest(manifest_stream.model_dump(mode="json"))
            or manifest_stream.applied_settings is None
            or path_binding.receiver_settings_digest
            != canonical_digest(manifest_stream.applied_settings.model_dump(mode="json"))
            or path_binding.tuned_center_frequency_hz
            != manifest_stream.applied_settings.center_frequency_hz
            or path_binding.sample_rate_hz != stream.sample_rate_hz
            or path_geometry_disagrees
            or path_binding.frequency_reference != expected_frequency
            or path_binding.science_configuration_digest != release.configuration_digest
            or path_binding.science_implementation_digest != release.executable_digest
            or raw_stream is None
            or path_binding.compressed_chunk_closure_digest
            != raw_stream.get("compressed_closure_digest")
            or path_binding.uncompressed_chunk_closure_digest
            != raw_stream.get("uncompressed_closure_digest")
        ):
            raise InvalidStateError("receiver-path snapshot disagrees with run authority")
        return "receiver_path", path_binding.binding_digest
    if scope.kind.value == "paired":
        pair_binding = StandardPairInputBindV2.model_validate(document)
        if (
            pair_binding.session_id != scope.session_id
            or pair_binding.manifest_digest != manifest_digest
            or pair_binding.synchronization_inventory_digest
            != scope.synchronization_inventory_digest
            or attestation_digest not in pair_binding.raw_integrity_attestation_digests
        ):
            raise InvalidStateError("paired snapshot disagrees with run authority")
        return "paired", pair_binding.binding_digest
    raise ValueError("only receiver_path and paired scopes have subject snapshots")


def _frequency_reference_for_lineage(
    session: Session,
    lineage: CaptureReceiverLineage,
    authority: CapturePathAuthority | None,
    *,
    tuned_center_frequency_hz: int,
    capture_start_utc_ns: int,
    capture_end_utc_ns: int,
) -> ReceiverFrequencyReferenceV1:
    if (
        authority is None
        or not authority.calibration_association_permitted
        or lineage.receiver_path_id is None
        or lineage.hardware_epoch_id is None
    ):
        return ReceiverFrequencyReferenceV1(reference=FrequencyReference.UNCALIBRATED_PRIOR)
    rows = (
        session.execute(
            select(FrequencyCalibration)
            .join(
                FrequencyCalibrationSetMember,
                FrequencyCalibrationSetMember.calibration_id == FrequencyCalibration.id,
            )
            .join(
                FrequencyCalibrationSet,
                FrequencyCalibrationSet.id == FrequencyCalibrationSetMember.set_id,
            )
            .where(
                FrequencyCalibration.receiver_path_id == lineage.receiver_path_id,
                FrequencyCalibration.hardware_epoch_id == lineage.hardware_epoch_id,
                FrequencyCalibrationSet.promotion_id.is_not(None),
                FrequencyCalibrationSet.sealed_utc_ns.is_not(None),
                FrequencyCalibrationSet.sealed_at.is_not(None),
                FrequencyCalibration.valid_from_utc_ns <= capture_start_utc_ns,
                (
                    FrequencyCalibration.valid_until_utc_ns.is_(None)
                    | (capture_end_utc_ns <= FrequencyCalibration.valid_until_utc_ns)
                ),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return ReceiverFrequencyReferenceV1(reference=FrequencyReference.UNCALIBRATED_PRIOR)
    if len(rows) != 1:
        raise InvalidStateError("calibration resolution is ambiguous")
    calibration = rows[0]
    if calibration.calibration_digest is None or calibration.uncertainty_hz is None:
        raise InvalidStateError("resolved calibration lacks exact digest or uncertainty")
    return ReceiverFrequencyReferenceV1(
        reference=FrequencyReference.CALIBRATED,
        center_frequency_hz=tuned_center_frequency_hz + calibration.center_offset_hz,
        uncertainty_hz=calibration.uncertainty_hz,
        calibration_digest=calibration.calibration_digest,
    )


def _database_now(session: Session) -> datetime:
    value = session.scalar(select(func.clock_timestamp()))
    if value is None:
        raise RuntimeError("PostgreSQL did not return its current time")
    return _require_aware(value)


def _datetime_from_utc_ns(value: int) -> datetime:
    if value < 0:
        raise ValueError("UTC nanoseconds cannot be negative")
    seconds, nanoseconds = divmod(value, 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=nanoseconds // 1_000)


def _register_frequency_calibration(
    session: Session,
    registration: FrequencyCalibrationRegistration,
) -> FrequencyCalibration:
    valid_from = _datetime_from_utc_ns(registration.valid_from_utc_ns)
    valid_until = (
        None
        if registration.valid_until_utc_ns is None
        else _datetime_from_utc_ns(registration.valid_until_utc_ns)
    )
    created_at = _datetime_from_utc_ns(registration.created_utc_ns)
    if (
        registration.valid_until_utc_ns is not None
        and registration.valid_until_utc_ns <= registration.valid_from_utc_ns
    ):
        raise ValueError("calibration validity interval must be non-empty")
    if not all(
        math.isfinite(value)
        for value in (
            registration.center_hz,
            registration.uncertainty_lower_hz,
            registration.uncertainty_upper_hz,
        )
    ):
        raise ValueError("calibration frequencies must be finite")
    if (
        registration.uncertainty_lower_hz > registration.center_hz
        or registration.uncertainty_upper_hz < registration.center_hz
    ):
        raise ValueError("calibration uncertainty does not contain its center")
    radio = session.get(Radio, registration.radio_id)
    receiver_path = session.execute(
        select(ReceiverPath).where(
            ReceiverPath.radio_id == registration.radio_id,
            ReceiverPath.receiver_id == registration.receiver_id,
            ReceiverPath.physical_receiver_id == registration.physical_receiver_id,
        )
    ).scalar_one_or_none()
    epoch = session.execute(
        select(HardwareEpoch).where(HardwareEpoch.external_id == registration.hardware_epoch_id)
    ).scalar_one_or_none()
    if radio is None or receiver_path is None or epoch is None:
        raise CatalogNotFoundError("calibration receiver-path identity is absent")
    if (
        radio.serial != registration.radio_serial
        or receiver_path.physical_receiver_id != registration.physical_receiver_id
        or epoch.radio_id != radio.id
    ):
        raise ProductConflictError("calibration receiver-path identity conflicts")
    session.execute(
        insert(FrequencyCalibration)
        .values(
            external_id=registration.calibration_id,
            receiver_path_id=receiver_path.id,
            hardware_epoch_id=epoch.id,
            center_offset_hz=registration.center_hz,
            uncertainty_hz=max(
                registration.center_hz - registration.uncertainty_lower_hz,
                registration.uncertainty_upper_hz - registration.center_hz,
            ),
            uncertainty_lower_hz=registration.uncertainty_lower_hz,
            uncertainty_upper_hz=registration.uncertainty_upper_hz,
            valid_from_utc_ns=registration.valid_from_utc_ns,
            valid_until_utc_ns=registration.valid_until_utc_ns,
            valid_from=valid_from,
            valid_until=valid_until,
            evidence_uri=registration.evidence_uri,
            evidence_digest=registration.evidence_digest,
            calibration_digest=registration.calibration_digest,
            method=registration.method,
            created_utc_ns=registration.created_utc_ns,
            evidence=list(registration.evidence),
            created_at=created_at,
        )
        .on_conflict_do_nothing()
    )
    row = session.execute(
        select(FrequencyCalibration)
        .where(FrequencyCalibration.external_id == registration.calibration_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or _frequency_calibration_registration(session, row) != registration:
        raise ProductConflictError("calibration identity conflicts")
    return row


def _frequency_calibration_registration(
    session: Session,
    row: FrequencyCalibration,
) -> FrequencyCalibrationRegistration:
    receiver_path = session.get(ReceiverPath, row.receiver_path_id)
    epoch = (
        None if row.hardware_epoch_id is None else session.get(HardwareEpoch, row.hardware_epoch_id)
    )
    if receiver_path is None or epoch is None:
        raise InvalidStateError("calibration path or hardware epoch is unavailable")
    radio = session.get(Radio, receiver_path.radio_id)
    if (
        radio is None
        or receiver_path.physical_receiver_id is None
        or epoch.external_id is None
        or row.external_id is None
        or row.calibration_digest is None
        or row.uncertainty_lower_hz is None
        or row.uncertainty_upper_hz is None
        or row.valid_from_utc_ns is None
        or row.method is None
        or row.created_utc_ns is None
        or row.evidence_uri is None
        or row.evidence_digest is None
    ):
        raise InvalidStateError("calibration row lacks authoritative identity")
    return FrequencyCalibrationRegistration(
        calibration_id=row.external_id,
        calibration_digest=row.calibration_digest,
        radio_id=radio.id,
        radio_serial=radio.serial,
        receiver_id=receiver_path.receiver_id,
        physical_receiver_id=receiver_path.physical_receiver_id,
        hardware_epoch_id=epoch.external_id,
        center_hz=row.center_offset_hz,
        uncertainty_lower_hz=row.uncertainty_lower_hz,
        uncertainty_upper_hz=row.uncertainty_upper_hz,
        valid_from_utc_ns=row.valid_from_utc_ns,
        valid_until_utc_ns=row.valid_until_utc_ns,
        method=row.method,
        created_utc_ns=row.created_utc_ns,
        evidence_uri=row.evidence_uri,
        evidence_digest=row.evidence_digest,
        evidence=tuple(row.evidence),
    )


def _frequency_calibration_set_record(
    session: Session,
    calibration_set: FrequencyCalibrationSet,
) -> FrequencyCalibrationSetRecord:
    calibrations = tuple(
        _frequency_calibration_registration(session, row)
        for row in session.scalars(
            select(FrequencyCalibration)
            .join(
                FrequencyCalibrationSetMember,
                FrequencyCalibrationSetMember.calibration_id == FrequencyCalibration.id,
            )
            .where(FrequencyCalibrationSetMember.set_id == calibration_set.id)
            .order_by(FrequencyCalibrationSetMember.ordinal)
        )
    )
    if (
        calibration_set.promotion_id is None
        or calibration_set.sealed_utc_ns is None
        or calibration_set.sealed_at is None
    ):
        raise InvalidStateError("calibration set publication is not sealed")
    return FrequencyCalibrationSetRecord(
        registration=FrequencyCalibrationSetRegistration(
            set_id=calibration_set.id,
            set_digest=calibration_set.digest,
            promotion_id=calibration_set.promotion_id,
            sealed_utc_ns=calibration_set.sealed_utc_ns,
            evidence_uri=calibration_set.evidence_uri,
            evidence_digest=calibration_set.evidence_digest,
            calibrations=calibrations,
        )
    )


def _reconcile_analysis_scope(session: Session, scope: ScopeIdentityV1) -> AnalysisScope:
    capture = session.get(CaptureSession, scope.session_id)
    if capture is None or capture.manifest_digest is None:
        raise InvalidStateError("analysis scope capture identity is absent")
    if scope.stream_id is not None:
        stream = session.get(RadioStream, (scope.session_id, scope.stream_id))
        if stream is None:
            raise InvalidStateError("analysis scope stream is absent from the capture manifest")
        if scope.receiver_id is not None:
            lineage = session.get(
                CaptureReceiverLineage,
                (scope.session_id, scope.stream_id, scope.receiver_id),
            )
            radio = session.get(Radio, stream.radio_id)
            authority = session.get(CapturePathAuthority, scope.session_id)
            protected_fixture = (
                capture.source_type == "test"
                and authority is not None
                and authority.authority_kind == "protected_test_fixture"
                and authority.evidence_only
                and not authority.current_analysis_eligible
                and not authority.physical_association_permitted
                and not authority.calibration_association_permitted
                and not authority.promotion_permitted
                and lineage is not None
                and lineage.capture_authority_session_id == authority.session_id
                and lineage.lineage_status == "unresolved"
                and lineage.receiver_path_id is None
                and lineage.hardware_epoch_id is None
                and lineage.station_assignment_id is None
            )
            if (
                lineage is None
                or radio is None
                or lineage.manifest_digest != capture.manifest_digest
                or lineage.radio_id != stream.radio_id
                or lineage.radio_serial != radio.serial
                or (
                    not protected_fixture
                    and (
                        lineage.lineage_status != "resolved"
                        or lineage.receiver_path_id is None
                        or lineage.hardware_epoch_id is None
                        or lineage.station_assignment_id is None
                    )
                )
            ):
                raise InvalidStateError("receiver scope lacks capture-time manifest lineage")
            if protected_fixture:
                receiver_path = None
                epoch = None
            else:
                assert lineage is not None
                receiver_path = session.get(ReceiverPath, lineage.receiver_path_id)
                epoch = session.get(HardwareEpoch, lineage.hardware_epoch_id)
            if not protected_fixture and (
                receiver_path is None
                or epoch is None
                or receiver_path.radio_id != lineage.radio_id
                or receiver_path.receiver_id != lineage.receiver_id
                or receiver_path.physical_receiver_id != lineage.physical_receiver_id
                or epoch.radio_id != lineage.radio_id
                or epoch.external_id != lineage.hardware_epoch_external_id
                or not _hardware_epoch_covers_stream(epoch, stream)
            ):
                raise InvalidStateError("capture-time receiver physical lineage changed")
        if scope.radio_id is not None and stream.radio_id != scope.radio_id:
            raise InvalidStateError("radio scope disagrees with stream-to-radio lineage")
    elif scope.synchronization_inventory_digest != _catalog_sync_inventory_digest(
        session, scope.session_id
    ):
        raise InvalidStateError("paired scope is not the canonical capture inventory")
    document = scope.model_dump(mode="json")
    values = {
        "canonical_digest": scope.canonical_digest,
        "kind": scope.kind.value,
        "session_id": scope.session_id,
        "stream_id": scope.stream_id,
        "radio_id": scope.radio_id,
        "receiver_id": scope.receiver_id,
        "synchronization_inventory_digest": scope.synchronization_inventory_digest,
        "document": document,
    }
    inserted = session.execute(
        insert(AnalysisScope)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[AnalysisScope.canonical_digest])
        .returning(AnalysisScope.id)
    ).scalar_one_or_none()
    row = (
        session.get(AnalysisScope, inserted)
        if inserted is not None
        else session.execute(
            select(AnalysisScope)
            .where(AnalysisScope.canonical_digest == scope.canonical_digest)
            .with_for_update()
        ).scalar_one()
    )
    if row is None or any(getattr(row, key) != value for key, value in values.items()):
        raise ProductConflictError("analysis scope digest conflicts with catalog")
    return row


def _catalog_sync_inventory_digest(session: Session, session_id: str) -> str:
    capture = session.get(CaptureSession, session_id)
    if capture is None or capture.manifest_digest is None:
        raise InvalidStateError("paired scope capture identity is absent")
    streams = tuple(
        session.scalars(
            select(RadioStream)
            .where(RadioStream.session_id == session_id)
            .order_by(RadioStream.id, RadioStream.radio_id)
        )
    )
    if len(streams) != 2:
        raise InvalidStateError("paired scope requires exactly two manifest radio streams")
    sample_geometries = tuple(
        _catalog_sync_sample_geometry(
            captured_sample_count=stream.captured_sample_count,
            attributes=stream.attributes,
        )
        for stream in streams
    )
    native_modes = {native for native, _geometry in sample_geometries}
    if len(native_modes) != 1:
        raise InvalidStateError("paired scope mixes legacy and V3 sample geometry")
    document: list[dict[str, object]] = []
    for ordinal, (stream, (_native, sample_geometry)) in enumerate(
        zip(streams, sample_geometries, strict=True)
    ):
        if stream.manifest_ordinal != ordinal:
            raise InvalidStateError("capture stream topology has no canonical ordinal")
        radio = session.get(Radio, stream.radio_id)
        if radio is None:
            raise InvalidStateError("capture stream radio identity is absent")
        lineage_count = session.scalar(
            select(func.count())
            .select_from(CaptureReceiverLineage)
            .where(
                CaptureReceiverLineage.session_id == session_id,
                CaptureReceiverLineage.stream_id == stream.id,
                CaptureReceiverLineage.manifest_digest == capture.manifest_digest,
            )
        )
        if lineage_count != len(stream.receiver_ids):
            raise InvalidStateError("capture stream receiver lineage is incomplete")
        document.append(
            {
                "ordinal": ordinal,
                "stream_id": stream.id,
                "radio": {
                    "radio_id": radio.id,
                    "serial": radio.serial,
                    "uri": radio.uri,
                    "transport": radio.transport,
                },
                "receiver_ids": list(stream.receiver_ids),
                "sample_rate_hz": stream.sample_rate_hz,
                **sample_geometry,
                "timing": stream.attributes.get("timing"),
                "state": stream.state,
            }
        )
    return canonical_digest(document)


def _catalog_sync_sample_geometry(
    *,
    captured_sample_count: int,
    attributes: dict[str, Any],
) -> tuple[bool, dict[str, int]]:
    """Select the immutable synchronization geometry for one persisted stream.

    Frozen V1/V2 inventories retain their original captured-count key. V3 is
    identified only by its complete logical/observed/zero-fill closure and
    mirrors the additive native compiler document exactly.
    """

    keys = ("logical_sample_count", "observed_sample_count", "zero_fill_sample_count")
    present = tuple(key in attributes for key in keys)
    if any(present) and not all(present):
        raise InvalidStateError("V3 synchronization sample geometry is incomplete")
    if not any(present):
        return False, {"captured_sample_count": captured_sample_count}
    logical, observed, zero_fill = (attributes[key] for key in keys)
    if (
        any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in (logical, observed, zero_fill)
        )
        or logical <= 0
        or observed <= 0
        or zero_fill < 0
        or logical != observed + zero_fill
        or captured_sample_count != observed
    ):
        raise InvalidStateError("V3 synchronization sample geometry does not close")
    return True, {
        "logical_sample_count": logical,
        "observed_sample_count": observed,
    }


def _stream_observed_bounds_ns(attributes: dict[str, Any]) -> tuple[int, int] | None:
    exact_start = attributes.get("capture_start_utc_ns")
    exact_end = attributes.get("capture_end_utc_ns")
    if isinstance(exact_start, int) and isinstance(exact_end, int):
        if exact_end <= exact_start:
            return None
        return exact_start, exact_end
    timing = attributes.get("timing")
    if not isinstance(timing, dict):
        return None
    first = timing.get("first_sample")
    last = timing.get("last_sample")
    if not isinstance(first, dict) or not isinstance(last, dict):
        return None
    start = first.get("estimate_utc_ns")
    end = last.get("estimate_utc_ns")
    if not isinstance(start, int) or not isinstance(end, int) or end < start:
        return None
    return start, end


def _hardware_epoch_covers_stream(epoch: HardwareEpoch, stream: RadioStream) -> bool:
    bounds_ns = _stream_observed_bounds_ns(stream.attributes)
    if bounds_ns is not None:
        if epoch.started_utc_ns is None:
            return False
        start_ns, end_ns = bounds_ns
        return epoch.started_utc_ns <= start_ns and (
            epoch.ended_utc_ns is None or end_ns <= epoch.ended_utc_ns
        )
    return (
        stream.observed_start_at is not None
        and stream.observed_end_at is not None
        and epoch.started_at <= stream.observed_start_at
        and (epoch.ended_at is None or stream.observed_end_at <= epoch.ended_at)
    )


def _requested_analysis_run_identity_digest(
    *,
    session_id: str,
    pipeline_release_id: str,
    input_manifest_digest: str,
    pipeline_lane: PipelineLane,
    promotion_policy: PromotionPolicy,
    expanded_plan_digest: str | None,
    definitions: tuple[JobDefinition, ...],
    subject_bindings: tuple[RunSubjectBindingRegistration, ...],
) -> str:
    return _analysis_run_identity_digest(
        session_id=session_id,
        pipeline_release_id=pipeline_release_id,
        input_manifest_digest=input_manifest_digest,
        pipeline_lane=pipeline_lane.value,
        promotion_policy=promotion_policy.value,
        expanded_plan_digest=expanded_plan_digest,
        job_documents=_requested_job_identity_documents(definitions),
        binding_documents=tuple(
            {
                "scope_digest": registration.scope.canonical_digest,
                "document": _stable_subject_binding_document(registration.document),
            }
            for registration in subject_bindings
        ),
    )


def _persisted_analysis_run_identity_digest(session: Session, run: AnalysisRun) -> str:
    jobs = tuple(
        session.scalars(
            select(ProcessingJob).where(ProcessingJob.run_id == run.id).order_by(ProcessingJob.id)
        )
    )
    jobs_by_id = {job.id: job for job in jobs}
    dependencies_by_job: dict[int, list[tuple[ProcessingJob, bool]]] = {}
    for job_id, depends_on_job_id, requires_product in session.execute(
        select(
            ProcessingJobDependency.job_id,
            ProcessingJobDependency.depends_on_job_id,
            ProcessingJobDependency.requires_product,
        ).where(ProcessingJobDependency.job_id.in_(tuple(jobs_by_id)))
    ):
        dependencies_by_job.setdefault(job_id, []).append(
            (jobs_by_id[depends_on_job_id], requires_product)
        )
    bindings = tuple(
        session.execute(
            select(AnalysisScope.canonical_digest, RunSubjectBinding.document)
            .join(AnalysisScope, AnalysisScope.id == RunSubjectBinding.scope_id)
            .where(RunSubjectBinding.run_id == run.id)
            .order_by(AnalysisScope.canonical_digest)
        )
    )
    return _analysis_run_identity_digest(
        session_id=run.session_id,
        pipeline_release_id=run.pipeline_release_id,
        input_manifest_digest=run.input_manifest_digest,
        pipeline_lane=run.pipeline_lane,
        promotion_policy=run.promotion_policy,
        expanded_plan_digest=run.expanded_plan_digest,
        job_documents=tuple(
            _persisted_job_identity_document(job, dependencies_by_job.get(job.id, []))
            for job in jobs
        ),
        binding_documents=tuple(
            {
                "scope_digest": scope_digest,
                "document": _stable_subject_binding_document(document),
            }
            for scope_digest, document in bindings
        ),
    )


def _analysis_run_identity_digest(
    *,
    session_id: str,
    pipeline_release_id: str,
    input_manifest_digest: str,
    pipeline_lane: str,
    promotion_policy: str,
    expanded_plan_digest: str | None,
    job_documents: tuple[dict[str, Any], ...],
    binding_documents: tuple[dict[str, Any], ...],
) -> str:
    """Identify scientific work while excluding UUIDs, triggers and queue priority."""

    return canonical_digest(
        {
            "schema_version": 1,
            "session_id": session_id,
            "pipeline_release_id": pipeline_release_id,
            "input_manifest_digest": input_manifest_digest,
            "pipeline_lane": pipeline_lane,
            "promotion_policy": promotion_policy,
            "expanded_plan_digest": expanded_plan_digest,
            "jobs": sorted(job_documents, key=canonical_digest),
            "subject_bindings": sorted(binding_documents, key=canonical_digest),
        }
    )


def _requested_job_identity_documents(
    definitions: tuple[JobDefinition, ...],
) -> tuple[dict[str, Any], ...]:
    documents: list[dict[str, Any]] = []
    for definition in definitions:
        scope_key = (
            definition.scope_key if definition.scope is None else definition.scope.canonical_digest
        )
        if definition.node_id is None:
            dependencies = tuple(
                {
                    "node_id": None,
                    "stage_key": dependency,
                    "scope_key": scope_key,
                    "requires_product": False,
                }
                for dependency in definition.dependencies
            )
        else:
            dependencies = tuple(
                {
                    "node_id": dependency,
                    "stage_key": None,
                    "scope_key": None,
                    "requires_product": dependency not in definition.ordering_only_node_ids,
                }
                for dependency in definition.depends_on_node_ids
            )
        documents.append(
            {
                "node_id": definition.node_id,
                "stage_key": definition.stage_key,
                "scope_key": scope_key,
                "resource_class": definition.resource_class,
                "iq_access": definition.iq_access,
                "max_attempts": definition.max_attempts,
                "dependencies": sorted(dependencies, key=canonical_digest),
            }
        )
    return tuple(documents)


def _persisted_job_identity_document(
    job: ProcessingJob,
    dependencies: list[tuple[ProcessingJob, bool]],
) -> dict[str, Any]:
    dependency_documents = tuple(
        {
            "node_id": dependency.node_id,
            "stage_key": None if dependency.node_id is not None else dependency.stage_key,
            "scope_key": None if dependency.node_id is not None else dependency.scope_key,
            "requires_product": requires_product,
        }
        for dependency, requires_product in dependencies
    )
    return {
        "node_id": job.node_id,
        "stage_key": job.stage_key,
        "scope_key": job.scope_key,
        "resource_class": job.resource_class,
        "iq_access": job.iq_access,
        "max_attempts": job.max_attempts,
        "dependencies": sorted(dependency_documents, key=canonical_digest),
    }


def _stable_subject_binding_document(document: dict[str, Any]) -> dict[str, Any]:
    """Remove proof-instance fields without hiding scientific binding changes."""

    return {
        key: value
        for key, value in document.items()
        if key
        not in {
            "binding_digest",
            "raw_integrity_attestation_digest",
            "raw_integrity_attestation_digests",
        }
    }


def _require_acyclic_job_nodes(definitions: tuple[JobDefinition, ...]) -> None:
    dependencies = {str(item.node_id): set(item.depends_on_node_ids) for item in definitions}
    ready = sorted(node for node, values in dependencies.items() if not values)
    visited: set[str] = set()
    while ready:
        node = ready.pop(0)
        visited.add(node)
        for dependent, values in dependencies.items():
            if node in values:
                values.remove(node)
                if not values and dependent not in visited and dependent not in ready:
                    ready.append(dependent)
                    ready.sort()
    if len(visited) != len(dependencies):
        raise ValueError("typed job dependency graph contains a cycle")


def _is_exact_git_sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _scope_identity(scope: AnalysisScope | None) -> ScopeIdentityV1:
    if scope is None:
        raise CatalogNotFoundError("normalized analysis scope is absent")
    identity = ScopeIdentityV1.model_validate(scope.document)
    if identity.canonical_digest != scope.canonical_digest:
        raise InvalidStateError("normalized analysis scope digest is corrupt")
    return identity


def _stage_derivation_output_record(
    session: Session, output: StageDerivationOutput
) -> StageDerivationOutputRecord:
    derivation_key = session.scalar(
        select(StageDerivation.derivation_key).where(StageDerivation.id == output.derivation_id)
    )
    if derivation_key is None:
        raise CatalogNotFoundError("stage derivation is absent")
    return StageDerivationOutputRecord(
        output_id=output.id,
        derivation_id=output.derivation_id,
        derivation_key=derivation_key,
        kind=output.kind,
        schema_version=output.schema_version,
        role=output.role,
        status=output.status,
        media_type=output.media_type,
        logical_uri=output.logical_uri,
        digest=output.digest,
        byte_size=output.byte_size,
        summary=output.summary,
        available=output.available,
    )


def _require_exact_release_authority(
    session: Session,
    run: AnalysisRun,
    authority: WorkerReleaseAuthority,
) -> None:
    release = session.get(PipelineRelease, run.pipeline_release_id)
    if release is None or (
        release.id != authority.pipeline_release_id
        or release.code_revision != authority.code_revision
        or release.environment_digest != authority.environment_digest
        or release.graph_digest != authority.graph_digest
        or release.configuration_digest != authority.configuration_digest
        or release.executable_digest != authority.executable_digest
        or release.authority_version != 1
    ):
        raise LeaseLostError("stage-result authority no longer matches its run release")


def _register_typed_product_membership(
    session: Session,
    product: ProductRegistration,
    *,
    run: AnalysisRun,
    producer_job: ProcessingJob,
    input_product_ids: tuple[int, ...],
) -> int:
    values = {
        "run_id": product.run_id,
        "stage_key": product.stage_key,
        "scope_key": producer_job.scope_key,
        "scope_id": producer_job.scope_id,
        "kind": product.kind,
        "schema_version": product.schema_version,
        "role": product.role,
        "status": product.status,
        "media_type": product.media_type,
        "logical_uri": product.logical_uri,
        "digest": product.digest,
        "byte_size": product.byte_size,
        "coverage": product.coverage,
        "summary": product.summary,
        "derivation_output_id": product.derivation_output_id,
        "derivation_mode": product.derivation_mode,
        "reused_from_product_id": product.reused_from_product_id,
    }
    _validate_derivation_membership(session, product, values)
    identity_keys = ("run_id", "stage_key", "scope_key", "kind", "schema_version")
    identity = {key: values[key] for key in identity_keys}
    inserted = session.execute(
        insert(AnalysisProduct)
        .values(**values, lineage_sealed=False)
        .on_conflict_do_nothing(
            index_elements=[getattr(AnalysisProduct, key) for key in identity_keys]
        )
        .returning(AnalysisProduct.id)
    ).scalar_one_or_none()
    if inserted is not None:
        if run.state not in {
            AnalysisRunState.PENDING.value,
            AnalysisRunState.RUNNING.value,
        }:
            raise InvalidStateError("cannot add a product to a terminal analysis run")
        session.add_all(
            ProductDependency(product_id=inserted, input_product_id=input_product_id)
            for input_product_id in input_product_ids
        )
        session.flush()
        session.execute(
            update(AnalysisProduct)
            .where(AnalysisProduct.id == inserted)
            .values(lineage_sealed=True)
        )
        return inserted
    existing = session.execute(
        select(AnalysisProduct).filter_by(**identity).with_for_update()
    ).scalar_one()
    if any(getattr(existing, key) != value for key, value in values.items()):
        raise ProductConflictError(
            f"product identity conflicts with existing product {existing.id}"
        )
    existing_inputs = tuple(
        session.scalars(
            select(ProductDependency.input_product_id)
            .where(ProductDependency.product_id == existing.id)
            .order_by(ProductDependency.input_product_id)
        )
    )
    if existing_inputs != input_product_ids or not existing.lineage_sealed:
        raise ProductConflictError(
            f"product dependency lineage conflicts with existing product {existing.id}"
        )
    return existing.id


def _validate_derivation_membership(
    session: Session, product: ProductRegistration, values: dict[str, Any]
) -> None:
    if product.derivation_mode == "legacy":
        if product.derivation_output_id is not None or product.reused_from_product_id is not None:
            raise ValueError("legacy product cannot carry derivation lineage")
        return
    if product.derivation_output_id is None:
        raise ValueError("computed/reused product requires a derivation output")
    output = session.execute(
        select(StageDerivationOutput)
        .where(StageDerivationOutput.id == product.derivation_output_id)
        .with_for_update()
    ).scalar_one_or_none()
    if output is None or not output.available:
        raise InvalidStateError("derivation output is absent or unavailable")
    expected = {
        "kind": output.kind,
        "schema_version": output.schema_version,
        "role": output.role,
        "status": output.status,
        "media_type": output.media_type,
        "logical_uri": output.logical_uri,
        "digest": output.digest,
        "byte_size": output.byte_size,
        "summary": output.summary,
    }
    if any(values[key] != value for key, value in expected.items()):
        raise ProductConflictError("run product disagrees with immutable derivation output")
    derivation = session.get(StageDerivation, output.derivation_id)
    run = session.get(AnalysisRun, product.run_id)
    if derivation is None or run is None:
        raise InvalidStateError("derivation or run identity is absent")
    if (
        derivation.stage_key != product.stage_key
        or product.scope is None
        or derivation.scope_digest != product.scope.canonical_digest
    ):
        raise InvalidStateError("derivation stage/scope lineage disagrees with run membership")
    stage_configuration = _stage_configuration(run, session, product.stage_key)
    if derivation.configuration_digest != canonical_digest(stage_configuration):
        raise InvalidStateError("derivation configuration lineage disagrees with run release")
    if product.derivation_mode == "computed":
        if product.reused_from_product_id is not None:
            raise ValueError("computed product cannot identify a reuse source")
        if derivation.producing_release_id != run.pipeline_release_id:
            raise InvalidStateError("computed derivation belongs to a different release")
        return
    if product.reused_from_product_id is None:
        raise ValueError("reused product requires a source product")
    source = session.execute(
        select(AnalysisProduct)
        .where(AnalysisProduct.id == product.reused_from_product_id)
        .with_for_update()
    ).scalar_one_or_none()
    if (
        source is None
        or not source.available
        or source.derivation_output_id != product.derivation_output_id
        or source.run_id == product.run_id
    ):
        raise InvalidStateError("reuse source does not own the exact available derivation output")


def _stage_configuration(run: AnalysisRun, session: Session, stage_key: str) -> dict[str, Any]:
    release = session.get(PipelineRelease, run.pipeline_release_id)
    if release is None:
        raise InvalidStateError("run pipeline release is absent")
    stages = release.configuration.get("stages", release.configuration)
    if not isinstance(stages, dict):
        raise InvalidStateError("pipeline release stage configuration is invalid")
    value = stages.get(stage_key, {})
    if not isinstance(value, dict):
        raise InvalidStateError("pipeline stage configuration is invalid")
    return value


def _recording_list_rows(
    session: Session, session_ids: tuple[str, ...]
) -> tuple[RecordingListRow, ...]:
    if not session_ids:
        return ()
    captures = {
        item.id: item
        for item in session.scalars(
            select(CaptureSession).where(CaptureSession.id.in_(session_ids))
        )
    }
    tags: dict[str, list[str]] = {item: [] for item in session_ids}
    for session_id, tag_name in session.execute(
        select(SessionTag.session_id, SessionTag.tag_name)
        .where(SessionTag.session_id.in_(session_ids))
        .order_by(SessionTag.session_id, SessionTag.tag_name)
    ):
        tags[session_id].append(tag_name)
    holds: dict[str, str] = {
        session_id: reason
        for session_id, reason in session.execute(
            select(RetentionHold.session_id, RetentionHold.reason).where(
                RetentionHold.session_id.in_(session_ids), RetentionHold.released_at.is_(None)
            )
        )
    }
    radio_counts: dict[str, int] = {
        session_id: count
        for session_id, count in session.execute(
            select(RadioStream.session_id, func.count())
            .where(RadioStream.session_id.in_(session_ids))
            .group_by(RadioStream.session_id)
        )
    }
    current: dict[str, str] = {
        session_id: run_id
        for session_id, run_id in session.execute(
            select(CurrentAnalysis.session_id, CurrentAnalysis.run_id).where(
                CurrentAnalysis.session_id.in_(session_ids)
            )
        )
    }
    all_runs = tuple(
        session.scalars(
            select(AnalysisRun)
            .where(AnalysisRun.session_id.in_(session_ids))
            .order_by(AnalysisRun.session_id, AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        )
    )
    runs_by_session: dict[str, AnalysisRun] = {}
    runs_by_id = {item.id: item for item in all_runs}
    for item in all_runs:
        runs_by_session.setdefault(item.session_id, item)
    for session_id, run_id in current.items():
        runs_by_session[session_id] = runs_by_id[run_id]
    run_ids = tuple(item.id for item in runs_by_session.values())
    summaries = {
        item.run_id: item
        for item in session.scalars(
            select(AnalysisSummary).where(AnalysisSummary.run_id.in_(run_ids))
        )
    }
    product_counts: dict[str, int] = {
        run_id: count
        for run_id, count in session.execute(
            select(AnalysisProduct.run_id, func.count())
            .where(AnalysisProduct.run_id.in_(run_ids))
            .group_by(AnalysisProduct.run_id)
        )
    }
    outcomes: dict[str, list[str]] = {item: [] for item in run_ids}
    for run_id, outcome in session.execute(
        select(ProcessingJob.run_id, ProcessingJob.outcome).where(
            ProcessingJob.run_id.in_(run_ids), ProcessingJob.outcome.is_not(None)
        )
    ):
        outcomes[run_id].append(outcome)
    output = []
    for session_id in session_ids:
        capture = captures[session_id]
        run = runs_by_session.get(session_id)
        summary = None if run is None else summaries.get(run.id)
        output.append(
            RecordingListRow(
                session_id=session_id,
                source_type=capture.source_type,
                capture_state=capture.state,
                started_at=capture.observed_start_at or capture.created_at,
                ended_at=capture.observed_end_at,
                attributes=capture.attributes,
                tags=tuple(tags[session_id]),
                hold_reason=holds.get(session_id),
                radio_count=int(radio_counts.get(session_id, 0)),
                run_id=None if run is None else run.id,
                pipeline_release_id=None if run is None else run.pipeline_release_id,
                run_state=None if run is None else run.state,
                run_created_at=None if run is None else run.created_at,
                run_started_at=None if run is None else run.started_at,
                run_sealed_at=None if run is None else run.sealed_at,
                run_failure=None if run is None else run.failure,
                run_is_current=run is not None and current.get(session_id) == run.id,
                coverage=None if summary is None else summary.coverage,
                product_count=0 if run is None else int(product_counts.get(run.id, 0)),
                job_outcomes=() if run is None else tuple(outcomes[run.id]),
            )
        )
    return tuple(output)


def _begin_consistent_read(session: Session) -> None:
    session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))


def _presentation_snapshot(
    session: Session,
    session_id: str,
    *,
    pipeline_lane: PipelineLane = PipelineLane.STANDARD,
) -> CatalogSessionReadSnapshot | None:
    capture = session.get(CaptureSession, session_id)
    if capture is None:
        return None
    tags = tuple(
        session.scalars(
            select(SessionTag.tag_name)
            .where(SessionTag.session_id == session_id)
            .order_by(SessionTag.tag_name)
        )
    )
    hold_reason = session.scalar(
        select(RetentionHold.reason).where(
            RetentionHold.session_id == session_id,
            RetentionHold.released_at.is_(None),
        )
    )
    current_run_id = session.scalar(
        select(CurrentPipelineAnalysis.run_id).where(
            CurrentPipelineAnalysis.session_id == session_id,
            CurrentPipelineAnalysis.pipeline_lane == pipeline_lane.value,
        )
    )
    if current_run_id is None:
        run = session.execute(
            select(AnalysisRun)
            .where(
                AnalysisRun.session_id == session_id,
                AnalysisRun.pipeline_lane == pipeline_lane.value,
            )
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    else:
        run = session.get(AnalysisRun, current_run_id)

    analysis = None
    if run is not None:
        release = session.get(PipelineRelease, run.pipeline_release_id)
        if release is None:
            raise CatalogNotFoundError(f"pipeline release is absent for analysis run: {run.id}")
        is_current = run.id == current_run_id
        summary_row = (
            session.execute(
                select(AnalysisSummary).where(
                    AnalysisSummary.session_id == session_id,
                    AnalysisSummary.run_id == run.id,
                )
            ).scalar_one_or_none()
            if is_current
            else None
        )
        summary = (
            None
            if summary_row is None
            else CurrentSummary(
                mean_power_dbfs=summary_row.mean_power_dbfs,
                best_qam_accuracy=summary_row.best_qam_accuracy,
                best_cfo_hz=summary_row.best_cfo_hz,
                doppler_slope_hz_s=summary_row.doppler_slope_hz_s,
                candidate_count=summary_row.candidate_count,
                coverage=summary_row.coverage,
                details=summary_row.details,
            )
        )
        jobs = tuple(
            CatalogJobRecord(
                job_id=job.id,
                stage_key=job.stage_key,
                scope_key=job.scope_key,
                state=job.state,
                outcome=job.outcome,
            )
            for job in session.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.run_id == run.id)
                .order_by(ProcessingJob.id)
            )
        )
        selected_for_presentation = is_current or (
            capture.source_type == "test"
            and run.promotion_policy == PromotionPolicy.EVIDENCE_ONLY.value
            and run.state == AnalysisRunState.SUCCEEDED.value
            and run.sealed_at is not None
        )
        products = (
            tuple(
                _catalog_product_record(product)
                for product in session.scalars(
                    select(AnalysisProduct)
                    .where(AnalysisProduct.run_id == run.id)
                    .order_by(
                        AnalysisProduct.stage_key,
                        AnalysisProduct.scope_key,
                        AnalysisProduct.kind,
                        AnalysisProduct.schema_version,
                    )
                )
            )
            if selected_for_presentation
            else ()
        )
        analysis = CatalogRunReadSnapshot(
            run_id=run.id,
            pipeline_release_id=run.pipeline_release_id,
            pipeline_configuration=release.configuration,
            promotion_policy=run.promotion_policy,
            pipeline_lane=run.pipeline_lane,
            state=run.state,
            created_at=run.created_at,
            started_at=run.started_at,
            sealed_at=run.sealed_at,
            failure=run.failure,
            input_manifest_digest=run.input_manifest_digest,
            manifest_uri=run.manifest_uri,
            manifest_digest=run.manifest_digest,
            is_current=is_current,
            summary=summary,
            jobs=jobs,
            products=products,
        )
    return CatalogSessionReadSnapshot(
        session_id=capture.id,
        source_type=capture.source_type,
        state=capture.state,
        created_at=capture.observed_start_at or capture.created_at,
        bundle_uri=capture.bundle_uri,
        manifest_digest=capture.manifest_digest,
        attributes=capture.attributes,
        tags=tags,
        hold_reason=hold_reason,
        analysis=analysis,
    )


def _catalog_product_record(
    product: AnalysisProduct, *, session: Session | None = None
) -> CatalogProductRecord:
    return CatalogProductRecord(
        product_id=product.id,
        run_id=product.run_id,
        stage_key=product.stage_key,
        scope_key=product.scope_key,
        kind=product.kind,
        schema_version=product.schema_version,
        role=product.role,
        status=product.status,
        media_type=product.media_type,
        logical_uri=product.logical_uri,
        digest=product.digest,
        byte_size=product.byte_size,
        available=product.available,
        coverage=product.coverage,
        summary=product.summary,
        scope_id=product.scope_id,
        scope=(
            None
            if session is None or product.scope_id is None
            else _scope_identity(session.get(AnalysisScope, product.scope_id))
        ),
        derivation_output_id=product.derivation_output_id,
        derivation_mode=product.derivation_mode,
        reused_from_product_id=product.reused_from_product_id,
    )


def _has_test_tag(session: Session, session_id: str) -> bool:
    return bool(
        session.scalar(
            select(
                exists().where(
                    SessionTag.session_id == session_id,
                    func.upper(SessionTag.tag_name) == "TEST",
                )
            )
        )
    )


def _campaign_references_session(session: Session, session_id: str) -> bool:
    return bool(
        session.scalar(select(exists().where(ScientificCampaignStream.session_id == session_id)))
    )


def _campaign_references_product(session: Session, product_id: int) -> bool:
    closure = _scientific_campaign_product_closure()
    return bool(session.scalar(select(exists().where(closure.c.product_id == product_id))))


def _scientific_campaign_product_closure() -> Any:
    closure = select(ScientificCampaignStream.analysis_product_id.label("product_id")).cte(
        "scientific_campaign_product_closure", recursive=True
    )
    dependencies = select(ProductDependency.input_product_id.label("product_id")).join(
        closure, ProductDependency.product_id == closure.c.product_id
    )
    return closure.union(dependencies)


def _lock_campaign_product_closure(
    session: Session,
    root_product_id: int,
) -> dict[int, AnalysisProduct]:
    closure = select(literal(root_product_id, type_=BigInteger()).label("product_id")).cte(
        "campaign_add_product_closure", recursive=True
    )
    dependencies = select(ProductDependency.input_product_id.label("product_id")).join(
        closure, ProductDependency.product_id == closure.c.product_id
    )
    closure = closure.union(dependencies)
    product_ids = tuple(
        session.scalars(select(closure.c.product_id).distinct().order_by(closure.c.product_id))
    )
    products = tuple(
        session.scalars(
            select(AnalysisProduct)
            .where(AnalysisProduct.id.in_(product_ids))
            .order_by(AnalysisProduct.id)
            .with_for_update()
        )
    )
    by_id = {product.id: product for product in products}
    if len(by_id) != len(product_ids):
        raise CatalogNotFoundError("scientific campaign product dependency is absent")
    if any(not product.available or product.purge_claim_token is not None for product in products):
        raise InvalidStateError(
            "scientific campaign product dependency is unavailable or purge-claimed"
        )
    return by_id


def _session_is_purge_eligible(session: Session, capture: CaptureSession) -> bool:
    if (
        capture.state not in (SessionState.COMMITTED.value, SessionState.DEGRADED.value)
        or not capture.raw_available
        or capture.bundle_uri is None
        or capture.allocated_bytes <= 0
        or capture.source_type == "test"
        or capture.purge_claim_token is not None
        or _has_test_tag(session, capture.id)
        or _campaign_references_session(session, capture.id)
    ):
        return False
    if session.scalar(
        select(
            exists().where(
                RetentionHold.session_id == capture.id,
                RetentionHold.released_at.is_(None),
            )
        )
    ):
        return False
    if not session.scalar(select(exists().where(CurrentAnalysis.session_id == capture.id))):
        return False
    return not bool(
        session.scalar(
            select(
                exists().where(
                    AnalysisRun.session_id == capture.id,
                    AnalysisRun.state.in_(
                        (AnalysisRunState.PENDING.value, AnalysisRunState.RUNNING.value)
                    ),
                )
            )
        )
    )


def _campaign_stream_values(stream: ScientificCampaignStreamRegistration) -> dict[str, Any]:
    return {
        "ordinal": stream.ordinal,
        "session_id": stream.session_id,
        "stream_id": stream.stream_id,
        "analysis_run_id": stream.analysis_run_id,
        "analysis_run_uri": stream.analysis_run_uri,
        "analysis_run_digest": stream.analysis_run_digest,
        "pipeline_release_id": stream.pipeline_release_id,
        "analysis_product_id": stream.analysis_product_id,
        "frequency_calibration_id": stream.frequency_calibration_id,
        "capture_uri": stream.capture_uri,
        "capture_digest": stream.capture_digest,
        "calibration_uri": stream.calibration_uri,
        "calibration_digest": stream.calibration_digest,
        "scientific_uri": stream.scientific_uri,
        "scientific_digest": stream.scientific_digest,
        "status": stream.status,
    }


def _matching_campaign_stream(
    session: Session,
    campaign_id: str,
    stream: ScientificCampaignStreamRegistration,
) -> ScientificCampaignStream | None:
    matches = tuple(
        session.scalars(
            select(ScientificCampaignStream).where(
                ScientificCampaignStream.campaign_id == campaign_id,
                (
                    (ScientificCampaignStream.ordinal == stream.ordinal)
                    | (
                        (ScientificCampaignStream.session_id == stream.session_id)
                        & (ScientificCampaignStream.stream_id == stream.stream_id)
                    )
                    | (ScientificCampaignStream.analysis_product_id == stream.analysis_product_id)
                ),
            )
        )
    )
    exact = tuple(item for item in matches if _campaign_stream_matches(item, stream))
    if len(exact) == 1 and len(matches) == 1:
        return exact[0]
    if matches:
        raise ProductConflictError(
            f"scientific campaign stream conflicts at ordinal {stream.ordinal}"
        )
    return None


def _campaign_stream_matches(
    stored: ScientificCampaignStream,
    stream: ScientificCampaignStreamRegistration,
) -> bool:
    return all(
        getattr(stored, key) == value for key, value in _campaign_stream_values(stream).items()
    )


def _repair_capture_metadata(
    session: Session,
    capture: CaptureSession,
    *,
    attributes: dict[str, Any],
    tags: tuple[str, ...],
) -> None:
    conflicting = {
        key
        for key, value in attributes.items()
        if key in capture.attributes and capture.attributes[key] != value
    }
    if conflicting:
        raise ProductConflictError(
            "recording reconciliation attributes conflict: " + ", ".join(sorted(conflicting))
        )
    capture.attributes = {**capture.attributes, **attributes}
    for tag_name in tags:
        session.execute(
            insert(Tag).values(name=tag_name).on_conflict_do_nothing(index_elements=[Tag.name])
        )
        session.execute(
            insert(SessionTag)
            .values(session_id=capture.id, tag_name=tag_name)
            .on_conflict_do_nothing(index_elements=[SessionTag.session_id, SessionTag.tag_name])
        )
    protected_evidence = capture.source_type == "test" or bool(
        {"CALIBRATION", "ACCEPTANCE"}.intersection(tags)
    )
    if protected_evidence and not session.scalar(
        select(
            exists().where(
                RetentionHold.session_id == capture.id,
                RetentionHold.released_at.is_(None),
            )
        )
    ):
        session.add(
            RetentionHold(
                session_id=capture.id,
                reason=(
                    "automatic TEST corpus hold"
                    if capture.source_type == "test"
                    else "automatic selected qualification evidence hold"
                ),
                created_by="system",
            )
        )


def _reconcile_station_radio(session: Session, radio: StationRadioTopologyV1) -> Radio:
    evidence = radio.endpoint_evidence
    session.execute(
        insert(Radio)
        .values(
            id=radio.radio_id,
            serial=radio.radio_serial,
            uri=evidence.endpoint,
            transport=evidence.transport.value,
        )
        .on_conflict_do_nothing()
    )
    row = (
        session.execute(
            select(Radio)
            .where((Radio.id == radio.radio_id) | (Radio.serial == radio.radio_serial))
            .with_for_update()
        )
        .scalars()
        .all()
    )
    if len(row) != 1 or (
        row[0].id,
        row[0].serial,
        row[0].uri,
        row[0].transport,
    ) != (
        radio.radio_id,
        radio.radio_serial,
        evidence.endpoint,
        evidence.transport.value,
    ):
        raise ProductConflictError("station topology radio identity conflicts")
    return row[0]


def _reconcile_station_assignment_authorities(
    session: Session,
    radio: StationRadioTopologyV1,
    assignment: StationReceiverAssignmentV1,
) -> tuple[ReceiverPath, HardwareEpoch]:
    session.execute(
        insert(ReceiverPath)
        .values(
            radio_id=radio.radio_id,
            receiver_id=assignment.receiver_id,
            physical_receiver_id=assignment.physical_receiver_id,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ReceiverPath.radio_id,
                ReceiverPath.receiver_id,
                ReceiverPath.physical_receiver_id,
            ]
        )
    )
    receiver_path = session.execute(
        select(ReceiverPath)
        .where(
            ReceiverPath.radio_id == radio.radio_id,
            ReceiverPath.receiver_id == assignment.receiver_id,
            ReceiverPath.physical_receiver_id == assignment.physical_receiver_id,
        )
        .with_for_update()
    ).scalar_one()
    start = _datetime_from_utc_ns(assignment.valid_from_utc_ns)
    end = _datetime_from_utc_ns(assignment.valid_until_utc_ns)
    session.execute(
        insert(HardwareEpoch)
        .values(
            external_id=assignment.hardware_epoch_external_id,
            radio_id=radio.radio_id,
            started_at=start,
            ended_at=end,
            started_utc_ns=assignment.valid_from_utc_ns,
            ended_utc_ns=assignment.valid_until_utc_ns,
        )
        .on_conflict_do_nothing(index_elements=[HardwareEpoch.external_id])
    )
    epoch = session.execute(
        select(HardwareEpoch)
        .where(HardwareEpoch.external_id == assignment.hardware_epoch_external_id)
        .with_for_update()
    ).scalar_one()
    if (
        epoch.radio_id,
        epoch.started_utc_ns,
        epoch.ended_utc_ns,
    ) != (
        radio.radio_id,
        assignment.valid_from_utc_ns,
        assignment.valid_until_utc_ns,
    ):
        raise ProductConflictError("station hardware epoch identity conflicts")
    return receiver_path, epoch


def _topology_assignment_documents(
    topology: StationReceiverTopologyV1,
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            topology.topology_digest,
            radio.radio_id,
            radio.radio_serial,
            radio.endpoint_evidence.transport.value,
            radio.endpoint_evidence.endpoint,
            radio.endpoint_evidence.evidence_uri,
            radio.endpoint_evidence.evidence_digest,
            assignment.receiver_id,
            assignment.physical_receiver_id,
            assignment.hardware_epoch_external_id,
            assignment.valid_from_utc_ns,
            assignment.valid_until_utc_ns,
        )
        for radio in topology.radios
        for assignment in radio.receiver_assignments
    )


def _station_assignment_documents(
    assignments: tuple[StationReceiverAssignment, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            item.topology_digest,
            item.radio_id,
            item.radio_serial,
            item.radio_transport,
            item.radio_endpoint,
            item.endpoint_evidence_uri,
            item.endpoint_evidence_digest,
            item.receiver_id,
            item.physical_receiver_id,
            item.hardware_epoch_external_id,
            item.valid_from_utc_ns,
            item.valid_until_utc_ns,
        )
        for item in assignments
    )


def _validate_capture_authority_registration(
    authority: CapturePathAuthorityContract,
    *,
    session_id: str,
    source_type: str,
    manifest_digest: str,
    streams: tuple[RadioStreamRegistration, ...] | None,
) -> None:
    snapshot = authority.verified_manifest_snapshot
    if (
        authority.session_id != session_id
        or authority.manifest_digest != manifest_digest
        or snapshot.session_id != session_id
        or snapshot.manifest_digest != manifest_digest
        or snapshot.source_type.value != source_type
    ):
        raise InvalidStateError("capture authority disagrees with capture identity")
    if isinstance(
        authority,
        (
            CaptureHardwareBindingV1,
            CaptureHardwareBindingV2,
            CaptureHardwareBindingV3,
            CaptureHardwareBindingV4,
            CaptureHardwareBindingV5,
            CaptureHardwareBindingV6,
        ),
    ):
        if source_type not in {"live", "import"}:
            raise InvalidStateError("station hardware authority cannot authorize TEST input")
    elif source_type != "test":
        raise InvalidStateError("protected fixture authority is TEST-only")
    if streams is None:
        raise InvalidStateError("authoritative capture requires complete stream inventory")
    manifest_streams = tuple(
        sorted(
            snapshot.recording_manifest.streams,
            key=lambda item: (item.stream_id, item.radio.radio_id),
        )
    )
    if len(streams) != len(manifest_streams):
        raise ProductConflictError("capture stream inventory differs from verified manifest")
    verified_by_stream = {item.stream_id: item for item in snapshot.streams}
    for ordinal, (registration, manifest_stream) in enumerate(
        zip(streams, manifest_streams, strict=True)
    ):
        verified_stream = verified_by_stream[manifest_stream.stream_id]
        applied = manifest_stream.applied_settings
        if applied is None:
            raise InvalidStateError("authoritative capture requires applied receiver settings")
        applied_document = registration.attributes.get("applied_settings")
        if not isinstance(applied_document, dict):
            raise ProductConflictError("capture lacks exact applied settings document")
        expected = (
            manifest_stream.stream_id,
            ordinal,
            manifest_stream.radio.radio_id,
            manifest_stream.radio.serial,
            manifest_stream.radio.uri,
            manifest_stream.radio.transport.value,
            tuple(applied.receiver_ids),
            applied.sample_rate_hz,
            manifest_stream.captured_sample_count,
            manifest_stream.state.value,
            manifest_stream.requested_settings.model_dump(mode="json"),
            applied.model_dump(mode="json"),
            None
            if manifest_stream.timing is None
            else manifest_stream.timing.model_dump(mode="json"),
            verified_stream.applied_settings_digest,
        )
        observed = (
            registration.stream_id,
            registration.manifest_ordinal,
            registration.radio_id,
            registration.radio_serial,
            registration.radio_uri,
            registration.radio_transport,
            tuple(registration.receiver_ids),
            registration.sample_rate_hz,
            registration.captured_sample_count,
            registration.state,
            registration.attributes.get("requested_settings"),
            applied_document,
            registration.attributes.get("timing"),
            canonical_digest(applied_document),
        )
        if observed != expected:
            raise ProductConflictError(
                "capture stream metadata differs from exact applied manifest inventory"
            )
        if isinstance(manifest_stream, RecordingStreamV3):
            sample_ns = (1_000_000_000 + applied.sample_rate_hz - 1) // applied.sample_rate_hz
            expected_attributes = {
                "requested_settings": manifest_stream.requested_settings.model_dump(mode="json"),
                "applied_settings": applied.model_dump(mode="json"),
                "timing": manifest_stream.timing.model_dump(mode="json"),
                "capture_start_utc_ns": manifest_stream.timing.first_sample.earliest_utc_ns,
                "capture_end_utc_ns": (
                    manifest_stream.timing.last_sample.latest_utc_ns + sample_ns
                ),
                "continuity": manifest_stream.continuity.model_dump(mode="json"),
                "timeline_relative_path": manifest_stream.timeline_relative_path,
                "timeline_sha256": manifest_stream.timeline_sha256,
                "logical_sample_count": manifest_stream.logical_sample_count,
                "observed_sample_count": manifest_stream.observed_sample_count,
                "zero_fill_sample_count": manifest_stream.zero_fill_sample_count,
                "observed_iq_sha256": manifest_stream.observed_iq_sha256,
                "logical_iq_sha256": manifest_stream.logical_iq_sha256,
                "gap_map_relative_path": manifest_stream.gap_map_relative_path,
                "gap_map_sha256": manifest_stream.gap_map_sha256,
                "validity_inventory_relative_path": (
                    manifest_stream.validity_inventory_relative_path
                ),
                "validity_inventory_sha256": manifest_stream.validity_inventory_sha256,
            }
            if registration.attributes != expected_attributes:
                raise ProductConflictError(
                    "V3 capture registration differs from exact device-axis authority"
                )
        expected_chunks = tuple(
            (
                item.chunk_index,
                (
                    item.device_sample_start
                    if isinstance(manifest_stream, RecordingStreamV3)
                    else item.sample_start
                ),
                item.sample_count,
                item.compressed_sha256,
                item.uncompressed_sha256,
                item.compressed_bytes,
                item.uncompressed_bytes,
            )
            for item in manifest_stream.chunks
        )
        observed_chunks = tuple(
            (
                item.chunk_index,
                item.sample_start,
                item.sample_count,
                item.compressed_digest,
                item.uncompressed_digest,
                item.compressed_bytes,
                item.uncompressed_bytes,
            )
            for item in registration.chunks
        )
        if observed_chunks != expected_chunks:
            raise ProductConflictError("capture chunks differ from verified manifest")


def _reconcile_manifest_profile_revision(
    session: Session,
    manifest: (
        RecordingManifestV1
        | RecordingManifestV3
        | RecordingManifestV4
        | RecordingManifestV5
        | RecordingManifestV6
    ),
) -> int:
    if isinstance(manifest, RecordingManifestV4):
        profile_id = manifest.capture_plan.dwell_class.value
        revision_digest = manifest.capture_plan.plan_digest
        document = manifest.capture_plan.model_dump(mode="json")
    else:
        revision = manifest.capture_plan.profile_revision
        profile_id = revision.profile.name
        revision_digest = revision.revision_digest
        document = revision.model_dump(mode="json")
    session.execute(
        insert(CaptureProfile).values(id=profile_id, name=profile_id).on_conflict_do_nothing()
    )
    stored_profile = session.get(CaptureProfile, profile_id)
    if stored_profile is None or stored_profile.name != profile_id:
        raise ProductConflictError("capture profile identity conflicts")
    revision_number = int(revision_digest.removeprefix("sha256:")[:7], 16)
    session.execute(
        insert(CaptureProfileRevision)
        .values(
            profile_id=profile_id,
            revision_number=revision_number,
            digest=revision_digest,
            document=document,
        )
        .on_conflict_do_nothing()
    )
    stored = session.execute(
        select(CaptureProfileRevision)
        .where(
            CaptureProfileRevision.profile_id == profile_id,
            CaptureProfileRevision.digest == revision_digest,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if stored is None or (stored.revision_number != revision_number or stored.document != document):
        raise ProductConflictError("capture profile revision conflicts")
    return stored.id


def _reconcile_capture_path_authority(
    session: Session,
    capture: CaptureSession,
    authority: CapturePathAuthorityContract,
) -> CapturePathAuthority:
    if isinstance(
        authority,
        (
            CaptureHardwareBindingV1,
            CaptureHardwareBindingV2,
            CaptureHardwareBindingV3,
            CaptureHardwareBindingV4,
            CaptureHardwareBindingV5,
            CaptureHardwareBindingV6,
        ),
    ):
        topology_row = session.get(StationTopology, authority.topology_digest)
        if topology_row is None or not topology_row.assignment_sealed:
            raise InvalidStateError("capture station topology is not registered and sealed")
        topology = StationReceiverTopologyV1.model_validate(topology_row.document)
        authority.assert_matches_topology(topology)
        values = {
            "authority_kind": "station",
            "authority_digest": authority.binding_digest,
            "topology_digest": authority.topology_digest,
            "evidence_only": False,
            "current_analysis_eligible": True,
            "physical_association_permitted": True,
            "calibration_association_permitted": True,
            "promotion_permitted": True,
        }
    else:
        values = {
            "authority_kind": "protected_test_fixture",
            "authority_digest": authority.authority_digest,
            "topology_digest": None,
            "evidence_only": True,
            "current_analysis_eligible": False,
            "physical_association_permitted": False,
            "calibration_association_permitted": False,
            "promotion_permitted": False,
        }
    values.update(
        {
            "session_id": capture.id,
            "manifest_digest": authority.manifest_digest,
            "manifest_snapshot_digest": authority.manifest_snapshot_digest,
            "document": authority.model_dump(mode="json"),
        }
    )
    session.execute(
        insert(CapturePathAuthority)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[CapturePathAuthority.session_id])
    )
    stored = session.get(CapturePathAuthority, capture.id)
    if stored is None or any(getattr(stored, key) != value for key, value in values.items()):
        raise ProductConflictError("capture path authority conflicts")
    return stored


def _capture_path_authority_record(
    row: CapturePathAuthority,
) -> CapturePathAuthorityRecord:
    return CapturePathAuthorityRecord(
        session_id=row.session_id,
        manifest_digest=row.manifest_digest,
        authority_kind=row.authority_kind,
        authority_digest=row.authority_digest,
        topology_digest=row.topology_digest,
        evidence_only=row.evidence_only,
        current_analysis_eligible=row.current_analysis_eligible,
        physical_association_permitted=row.physical_association_permitted,
        calibration_association_permitted=row.calibration_association_permitted,
        promotion_permitted=row.promotion_permitted,
    )


def _reconcile_radio_streams(
    session: Session,
    session_id: str,
    registrations: tuple[RadioStreamRegistration, ...],
    *,
    path_authority: CapturePathAuthorityContract | None = None,
) -> None:
    if len({item.stream_id for item in registrations}) != len(registrations):
        raise ProductConflictError("recording manifest repeats a stream identity")
    ordinals = tuple(item.manifest_ordinal for item in registrations)
    if tuple(sorted(ordinals)) != tuple(range(len(registrations))):
        raise ProductConflictError("recording manifest stream ordinals are not canonical")
    lock_keys = {
        *(f"radio-id:{item.radio_id}" for item in registrations),
        *(f"radio-serial:{item.radio_serial}" for item in registrations),
    }
    for identity in sorted(lock_keys):
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {"identity": identity},
        )
    expected_ids = {item.stream_id for item in registrations}
    existing_ids = set(
        session.scalars(select(RadioStream.id).where(RadioStream.session_id == session_id))
    )
    if existing_ids - expected_ids:
        raise ProductConflictError("catalog contains streams absent from recording manifest")
    capture = session.get(CaptureSession, session_id)
    if capture is None or capture.manifest_digest is None:
        raise InvalidStateError("capture identity is absent while reconciling streams")
    for value in sorted(registrations, key=lambda item: item.manifest_ordinal):
        radio_matches = tuple(
            session.scalars(
                select(Radio)
                .where((Radio.id == value.radio_id) | (Radio.serial == value.radio_serial))
                .with_for_update()
            )
        )
        if not radio_matches:
            session.add(
                Radio(
                    id=value.radio_id,
                    serial=value.radio_serial,
                    uri=value.radio_uri,
                    transport=value.radio_transport,
                )
            )
            session.flush()
        elif len(radio_matches) != 1 or (
            radio_matches[0].id,
            radio_matches[0].serial,
            radio_matches[0].uri,
            radio_matches[0].transport,
        ) != (
            value.radio_id,
            value.radio_serial,
            value.radio_uri,
            value.radio_transport,
        ):
            raise ProductConflictError("recording radio identity conflicts with catalog")

        stored = session.get(RadioStream, (session_id, value.stream_id))
        stream_values = (
            value.radio_id,
            value.manifest_ordinal,
            value.state,
            list(value.receiver_ids),
            value.sample_rate_hz,
            value.captured_sample_count,
            value.observed_start_at,
            value.observed_end_at,
            value.attributes,
        )
        if stored is None:
            stored = RadioStream(
                id=value.stream_id,
                session_id=session_id,
                radio_id=value.radio_id,
                manifest_ordinal=value.manifest_ordinal,
                state=value.state,
                receiver_ids=list(value.receiver_ids),
                sample_rate_hz=value.sample_rate_hz,
                captured_sample_count=value.captured_sample_count,
                observed_start_at=value.observed_start_at,
                observed_end_at=value.observed_end_at,
                attributes=value.attributes,
            )
            session.add(stored)
            session.flush()
        elif (
            stored.radio_id,
            stored.manifest_ordinal,
            stored.state,
            stored.receiver_ids,
            stored.sample_rate_hz,
            stored.captured_sample_count,
            stored.observed_start_at,
            stored.observed_end_at,
            stored.attributes,
        ) != stream_values:
            raise ProductConflictError("recording stream metadata conflicts with catalog")

        stream_identity = {
            "ordinal": value.manifest_ordinal,
            "stream_id": value.stream_id,
            "radio": {
                "radio_id": value.radio_id,
                "serial": value.radio_serial,
                "uri": value.radio_uri,
                "transport": value.radio_transport,
            },
            "receiver_ids": list(value.receiver_ids),
            "requested_settings": value.attributes.get("requested_settings"),
            "applied_settings": value.attributes.get("applied_settings"),
            "sample_rate_hz": value.sample_rate_hz,
            "captured_sample_count": value.captured_sample_count,
            "timing": value.attributes.get("timing"),
            "state": value.state,
        }
        for receiver_id in value.receiver_ids:
            station_authority = (
                path_authority
                if isinstance(
                    path_authority,
                    (
                        CaptureHardwareBindingV1,
                        CaptureHardwareBindingV2,
                        CaptureHardwareBindingV3,
                        CaptureHardwareBindingV4,
                        CaptureHardwareBindingV5,
                        CaptureHardwareBindingV6,
                    ),
                )
                else None
            )
            captured_path = (
                None
                if station_authority is None
                else next(
                    (
                        item
                        for item in station_authority.paths
                        if item.stream_id == value.stream_id and item.receiver_id == receiver_id
                    ),
                    None,
                )
            )
            station_assignment = None
            receiver_path = None
            epoch = None
            if captured_path is not None:
                assert station_authority is not None
                station_assignment = session.execute(
                    select(StationReceiverAssignment)
                    .where(
                        StationReceiverAssignment.topology_digest
                        == station_authority.topology_digest,
                        StationReceiverAssignment.radio_id == captured_path.radio_id,
                        StationReceiverAssignment.radio_serial == captured_path.radio_serial,
                        StationReceiverAssignment.receiver_id == captured_path.receiver_id,
                        StationReceiverAssignment.physical_receiver_id
                        == captured_path.physical_receiver_id,
                        StationReceiverAssignment.hardware_epoch_external_id
                        == captured_path.hardware_epoch_external_id,
                        StationReceiverAssignment.radio_transport
                        == captured_path.radio_transport.value,
                        StationReceiverAssignment.radio_endpoint == captured_path.radio_endpoint,
                        StationReceiverAssignment.endpoint_evidence_uri
                        == captured_path.endpoint_evidence_uri,
                        StationReceiverAssignment.endpoint_evidence_digest
                        == captured_path.endpoint_evidence_digest,
                        StationReceiverAssignment.valid_from_utc_ns
                        <= captured_path.capture_start_utc_ns,
                        captured_path.capture_end_utc_ns
                        <= StationReceiverAssignment.valid_until_utc_ns,
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if station_assignment is None:
                    raise InvalidStateError(
                        "capture path is absent from the registered station topology"
                    )
                receiver_path = session.get(ReceiverPath, station_assignment.receiver_path_id)
                epoch = session.get(HardwareEpoch, station_assignment.hardware_epoch_id)
                if receiver_path is None or epoch is None:
                    raise InvalidStateError("station assignment normalization is incomplete")
            resolved = captured_path is not None
            lineage_values = {
                "session_id": session_id,
                "stream_id": value.stream_id,
                "receiver_id": receiver_id,
                "radio_id": value.radio_id,
                "radio_serial": value.radio_serial,
                "manifest_digest": capture.manifest_digest,
                "stream_identity_digest": canonical_digest(stream_identity),
                "lineage_status": "resolved" if resolved else "unresolved",
                "physical_receiver_id": (
                    None if receiver_path is None else receiver_path.physical_receiver_id
                ),
                "hardware_epoch_external_id": (None if epoch is None else epoch.external_id),
                "receiver_path_id": None if receiver_path is None else receiver_path.id,
                "hardware_epoch_id": None if epoch is None else epoch.id,
                "capture_authority_session_id": (None if path_authority is None else session_id),
                "station_assignment_id": (
                    None if station_assignment is None else station_assignment.id
                ),
            }
            session.execute(
                insert(CaptureReceiverLineage)
                .values(**lineage_values)
                .on_conflict_do_nothing(
                    index_elements=[
                        CaptureReceiverLineage.session_id,
                        CaptureReceiverLineage.stream_id,
                        CaptureReceiverLineage.receiver_id,
                    ]
                )
            )
            lineage = session.get(
                CaptureReceiverLineage,
                (session_id, value.stream_id, receiver_id),
            )
            if lineage is None or any(
                getattr(lineage, key) != expected for key, expected in lineage_values.items()
            ):
                raise ProductConflictError("capture receiver lineage conflicts with manifest")

        chunks = tuple(
            session.scalars(
                select(RecordingChunk)
                .where(
                    RecordingChunk.session_id == session_id,
                    RecordingChunk.stream_id == value.stream_id,
                )
                .order_by(RecordingChunk.chunk_index)
            )
        )
        by_index = {item.chunk_index: item for item in chunks}
        expected_indexes = {item.chunk_index for item in value.chunks}
        if set(by_index) - expected_indexes or len(expected_indexes) != len(value.chunks):
            raise ProductConflictError("catalog recording chunks conflict with manifest inventory")
        for chunk in value.chunks:
            chunk_values = (
                chunk.sample_start,
                chunk.sample_count,
                chunk.logical_uri,
                chunk.compressed_digest,
                chunk.uncompressed_digest,
                chunk.compressed_bytes,
                chunk.uncompressed_bytes,
            )
            stored_chunk = by_index.get(chunk.chunk_index)
            if stored_chunk is None:
                session.add(
                    RecordingChunk(
                        session_id=session_id,
                        stream_id=value.stream_id,
                        chunk_index=chunk.chunk_index,
                        sample_start=chunk.sample_start,
                        sample_count=chunk.sample_count,
                        logical_uri=chunk.logical_uri,
                        compressed_digest=chunk.compressed_digest,
                        uncompressed_digest=chunk.uncompressed_digest,
                        compressed_bytes=chunk.compressed_bytes,
                        uncompressed_bytes=chunk.uncompressed_bytes,
                    )
                )
            elif (
                stored_chunk.sample_start,
                stored_chunk.sample_count,
                stored_chunk.logical_uri,
                stored_chunk.compressed_digest,
                stored_chunk.uncompressed_digest,
                stored_chunk.compressed_bytes,
                stored_chunk.uncompressed_bytes,
            ) != chunk_values:
                raise ProductConflictError("recording chunk metadata conflicts with catalog")


def _validate_campaign_stream_lineage(
    session: Session,
    campaign_id: str,
    stream: ScientificCampaignStreamRegistration,
) -> None:
    if not 0 <= stream.ordinal < 40:
        raise ValueError("scientific campaign stream ordinal must be in [0, 40)")
    if stream.status not in {"pass", "fail", "inconclusive", "insufficient"}:
        raise ValueError(f"unknown scientific stream status: {stream.status!r}")
    capture = session.execute(
        select(CaptureSession).where(CaptureSession.id == stream.session_id).with_for_update()
    ).scalar_one_or_none()
    radio_stream = session.get(RadioStream, (stream.session_id, stream.stream_id))
    run = session.get(AnalysisRun, stream.analysis_run_id)
    closure_products = _lock_campaign_product_closure(session, stream.analysis_product_id)
    product = closure_products.get(stream.analysis_product_id)
    calibration = session.get(FrequencyCalibration, stream.frequency_calibration_id)
    if (
        capture is None
        or radio_stream is None
        or run is None
        or product is None
        or calibration is None
    ):
        raise CatalogNotFoundError("scientific campaign stream lineage is incomplete")
    receiver_path = session.get(ReceiverPath, calibration.receiver_path_id)
    if receiver_path is None:
        raise CatalogNotFoundError("scientific campaign calibration receiver path is absent")
    if (
        radio_stream.session_id != capture.id
        or run.session_id != capture.id
        or product.run_id != run.id
    ):
        raise ProductConflictError("scientific campaign stream lineage crosses catalog identities")
    if (
        capture.state not in {SessionState.COMMITTED.value, SessionState.DEGRADED.value}
        or not capture.raw_available
        or capture.purge_claim_token is not None
        or capture.bundle_uri != stream.capture_uri
        or capture.manifest_digest != stream.capture_digest
    ):
        raise InvalidStateError("scientific campaign capture is unavailable or disagrees")
    if (
        run.state != AnalysisRunState.SUCCEEDED.value
        or run.promotion_policy != PromotionPolicy.EVIDENCE_ONLY.value
    ):
        raise InvalidStateError("scientific campaign analysis run must be sealed evidence-only")
    if (
        run.manifest_uri != stream.analysis_run_uri
        or run.manifest_digest != stream.analysis_run_digest
        or run.pipeline_release_id != stream.pipeline_release_id
    ):
        raise ProductConflictError("scientific campaign analysis run evidence disagrees")
    session_peers = tuple(
        session.scalars(
            select(ScientificCampaignStream).where(
                ScientificCampaignStream.campaign_id == campaign_id,
                ScientificCampaignStream.session_id == stream.session_id,
            )
        )
    )
    for peer in session_peers:
        peer_run = session.get(AnalysisRun, peer.analysis_run_id)
        if peer_run is None:
            raise CatalogNotFoundError("paired scientific campaign run is absent")
        if (
            peer.analysis_run_id != run.id
            or peer.analysis_run_uri != stream.analysis_run_uri
            or peer.analysis_run_digest != stream.analysis_run_digest
            or peer.pipeline_release_id != stream.pipeline_release_id
            or peer_run.pipeline_release_id != stream.pipeline_release_id
        ):
            raise ProductConflictError(
                "paired scientific campaign streams require one exact analysis run"
            )
    if (
        not product.available
        or product.purge_claim_token is not None
        or product.scope_key != radio_stream.id
        or (product.kind, product.schema_version)
        not in {
            ("starlink.matched-acceptance", 1),
            ("starlink.trusted-matched-recovery", 2),
        }
        or product.role != "scientific"
        or product.logical_uri != stream.scientific_uri
        or product.digest != stream.scientific_digest
    ):
        raise InvalidStateError("scientific campaign product is unavailable or disagrees")
    if (
        receiver_path.radio_id != radio_stream.radio_id
        or receiver_path.receiver_id not in radio_stream.receiver_ids
        or calibration.evidence_uri != stream.calibration_uri
        or calibration.evidence_digest != stream.calibration_digest
    ):
        raise ProductConflictError("scientific campaign calibration evidence disagrees")
    observed_at = capture.observed_start_at
    observed_end_at = capture.observed_end_at
    if (
        observed_at is None
        or observed_end_at is None
        or calibration.valid_from > observed_at
        or (calibration.valid_until is not None and observed_end_at > calibration.valid_until)
    ):
        raise InvalidStateError("scientific campaign calibration does not cover capture interval")


def _campaign_seal_matches(campaign: ScientificCampaign, seal: ScientificCampaignSeal) -> bool:
    return (
        campaign.scientific_uri == seal.scientific_uri
        and campaign.scientific_digest == seal.scientific_digest
        and campaign.presentation_uri == seal.presentation_uri
        and campaign.presentation_digest == seal.presentation_digest
        and campaign.result_status == seal.result_status
        and campaign.outer_seal_uri == seal.outer_seal_uri
        and campaign.outer_seal_digest == seal.outer_seal_digest
    )


def _scientific_campaign_record(
    session: Session, campaign: ScientificCampaign
) -> ScientificCampaignRecord:
    streams = tuple(
        ScientificCampaignStreamRegistration(
            ordinal=item.ordinal,
            session_id=item.session_id,
            stream_id=item.stream_id,
            analysis_run_id=item.analysis_run_id,
            analysis_run_uri=item.analysis_run_uri,
            analysis_run_digest=item.analysis_run_digest,
            pipeline_release_id=item.pipeline_release_id,
            analysis_product_id=item.analysis_product_id,
            frequency_calibration_id=item.frequency_calibration_id,
            capture_uri=item.capture_uri,
            capture_digest=item.capture_digest,
            calibration_uri=item.calibration_uri,
            calibration_digest=item.calibration_digest,
            scientific_uri=item.scientific_uri,
            scientific_digest=item.scientific_digest,
            status=item.status,
        )
        for item in session.scalars(
            select(ScientificCampaignStream)
            .where(ScientificCampaignStream.campaign_id == campaign.id)
            .order_by(ScientificCampaignStream.ordinal)
        )
    )
    return ScientificCampaignRecord(
        campaign_id=campaign.id,
        state=campaign.state,
        capture_uri=campaign.capture_uri,
        capture_digest=campaign.capture_digest,
        scientific_uri=campaign.scientific_uri,
        scientific_digest=campaign.scientific_digest,
        presentation_uri=campaign.presentation_uri,
        presentation_digest=campaign.presentation_digest,
        outer_seal_uri=campaign.outer_seal_uri,
        outer_seal_digest=campaign.outer_seal_digest,
        result_status=campaign.result_status,
        seal_authority_version=campaign.seal_authority_version,
        created_at=campaign.created_at,
        sealed_at=campaign.sealed_at,
        streams=streams,
    )


def _locked_purge_capture(
    session: Session,
    session_id: str,
    claim_token: str,
    now: datetime,
) -> CaptureSession:
    capture = session.execute(
        select(CaptureSession).where(CaptureSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if (
        capture is None
        or capture.state != SessionState.PURGING.value
        or capture.purge_claim_token != claim_token
        or capture.purge_claim_expires_at is None
        or capture.purge_claim_expires_at <= now
    ):
        raise LeaseLostError(f"session purge lease is no longer owned: {session_id}")
    return capture


def _locked_job(session: Session, job_id: int) -> ProcessingJob:
    job = session.execute(
        select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
    ).scalar_one_or_none()
    if job is None:
        raise CatalogNotFoundError(f"processing job is absent: {job_id}")
    return job


def _processing_fence_result(
    event: ProcessingFenceEvent, *, changed: bool
) -> ProcessingFenceResult:
    return ProcessingFenceResult(
        operation_id=event.operation_id,
        pipeline_release_id=event.pipeline_release_id,
        run_ids=tuple(event.run_ids),
        changed=changed,
        cancelled_run_count=event.cancelled_run_count,
        cancelled_job_count=event.cancelled_job_count,
        expired_attempt_count=event.expired_attempt_count,
        preserved_succeeded_job_count=event.preserved_succeeded_job_count,
        preserved_product_count=event.preserved_product_count,
    )


def _require_live_lease(job: ProcessingJob, worker_id: str, now: datetime) -> None:
    if (
        job.state != JobState.LEASED.value
        or job.lease_owner != worker_id
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
    ):
        raise LeaseLostError(f"worker {worker_id!r} no longer owns live job lease {job.id}")


def _current_attempt(session: Session, job: ProcessingJob) -> ProcessingJobAttempt:
    attempt = session.execute(
        select(ProcessingJobAttempt)
        .where(
            ProcessingJobAttempt.job_id == job.id,
            ProcessingJobAttempt.attempt_number == job.attempt_count,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if attempt is None:
        raise InvalidStateError(f"job {job.id} has no current attempt")
    return attempt


def _clear_lease(job: ProcessingJob) -> None:
    job.lease_owner = None
    job.lease_expires_at = None
    job.heartbeat_at = None


def _acquisition_operation_record(
    operation: AcquisitionOperation,
) -> AcquisitionOperationRecord:
    return AcquisitionOperationRecord(
        operation_id=operation.id,
        operation_key=operation.operation_key,
        kind=operation.kind,
        state=operation.state,
        payload=operation.payload,
        scheduled_for=operation.scheduled_for,
        available_at=operation.available_at,
        priority=operation.priority,
        attempt_count=operation.attempt_count,
        max_attempts=operation.max_attempts,
        worker_id=operation.lease_owner,
        lease_expires_at=operation.lease_expires_at,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
        error=operation.error,
    )


def _lock_acquisition_cadence(session: Session) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": _ACQUISITION_CADENCE_LOCK_KEY},
    )


def _requeue_acquisition_operation(
    session: Session,
    operation: AcquisitionOperation,
    *,
    now: datetime,
    available_at: datetime,
    error: str,
) -> str:
    """Requeue a lease while preserving the newest same-kind cadence intent."""

    pending = None
    if operation.kind in _ACQUISITION_CADENCE_KINDS:
        pending = session.scalar(
            select(AcquisitionOperation)
            .where(
                AcquisitionOperation.kind == operation.kind,
                AcquisitionOperation.state == "pending",
                AcquisitionOperation.id != operation.id,
            )
            .order_by(
                AcquisitionOperation.scheduled_for.desc(),
                AcquisitionOperation.id.desc(),
            )
            .with_for_update()
        )
    if pending is not None:
        operation_rank = (operation.scheduled_for, operation.operation_key)
        pending_rank = (pending.scheduled_for, pending.operation_key)
        if operation_rank <= pending_rank:
            _clear_acquisition_lease(operation)
            operation.state = "cancelled"
            operation.outcome = (
                f"superseded by newer {operation.kind} intent {pending.operation_key}"
            )
            operation.error = None
            operation.completed_at = now
            operation.updated_at = now
            return operation.state
        pending.state = "cancelled"
        pending.outcome = f"superseded by newer {operation.kind} intent {operation.operation_key}"
        pending.error = None
        pending.completed_at = now
        pending.updated_at = now
        # Free the partial unique-index slot while the selected operation is
        # still a coherent leased row, then make that selected row pending.
        session.flush()

    _clear_acquisition_lease(operation)
    operation.state = "pending"
    operation.available_at = available_at
    operation.error = error
    operation.updated_at = now
    return operation.state


def _locked_acquisition_operation(session: Session, operation_id: int) -> AcquisitionOperation:
    operation = session.scalar(
        select(AcquisitionOperation)
        .where(AcquisitionOperation.id == operation_id)
        .with_for_update()
    )
    if operation is None:
        raise CatalogNotFoundError(f"acquisition operation is absent: {operation_id}")
    return operation


def _require_live_acquisition_lease(
    operation: AcquisitionOperation, worker_id: str, now: datetime
) -> None:
    if (
        operation.state != "leased"
        or operation.lease_owner != worker_id
        or operation.lease_expires_at is None
        or operation.lease_expires_at <= now
    ):
        raise LeaseLostError(f"acquisition operation {operation.id} is not leased by {worker_id!r}")


def _clear_acquisition_lease(operation: AcquisitionOperation) -> None:
    operation.lease_owner = None
    operation.lease_expires_at = None
    operation.heartbeat_at = None


def _require_positive_duration(value: timedelta) -> None:
    if value <= timedelta(0):
        raise ValueError("lease duration must be positive")


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)
