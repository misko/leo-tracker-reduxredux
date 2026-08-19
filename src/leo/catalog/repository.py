"""Transactional PostgreSQL catalog operations.

Every public mutation owns one short transaction. Processing work happens
outside these methods while a worker holds a renewable lease.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, exists, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, sessionmaker

from leo.catalog.errors import (
    ActiveRunExistsError,
    CatalogNotFoundError,
    InvalidStateError,
    LeaseLostError,
    ProductConflictError,
    PromotionError,
)
from leo.catalog.models import (
    AnalysisProduct,
    AnalysisRun,
    AnalysisSummary,
    CaptureSession,
    CurrentAnalysis,
    FrequencyCalibration,
    PipelineRelease,
    ProcessingJob,
    ProcessingJobAttempt,
    ProcessingJobDependency,
    RadioStream,
    ReceiverPath,
    RetentionEvent,
    RetentionHold,
    ScientificCampaign,
    ScientificCampaignStream,
    SessionTag,
    Tag,
)
from leo.catalog.states import (
    AnalysisRunState,
    AttemptState,
    JobState,
    PromotionPolicy,
    SessionState,
)
from leo.catalog.types import (
    CatalogBacklogSnapshot,
    CatalogJobRecord,
    CatalogProductPurgeClaim,
    CatalogProductRecord,
    CatalogRetentionCandidate,
    CatalogRunReadSnapshot,
    CatalogSessionPurgeClaim,
    CatalogSessionReadSnapshot,
    CurrentSummary,
    JobDefinition,
    JobLease,
    ProductRegistration,
    RunExecutionInfo,
    RunSealSnapshot,
    ScientificCampaignRecord,
    ScientificCampaignRegistration,
    ScientificCampaignSeal,
    ScientificCampaignStreamRegistration,
    SessionSearch,
    SessionSearchResult,
)


class CatalogRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

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
            session.add(
                CaptureSession(
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
            )
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

    def add_pipeline_release(
        self,
        *,
        release_id: str,
        code_revision: str,
        environment_digest: str,
        graph_digest: str,
        configuration: dict[str, Any] | None = None,
    ) -> None:
        values = {
            "id": release_id,
            "code_revision": code_revision,
            "environment_digest": environment_digest,
            "graph_digest": graph_digest,
            "configuration": {} if configuration is None else configuration,
        }
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
            _validate_campaign_stream_lineage(session, stream)
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
            campaign.sealed_at = _database_now(session)
            session.flush()
            return _scientific_campaign_record(session, campaign)

    def scientific_campaign(self, campaign_id: str) -> ScientificCampaignRecord | None:
        with self._sessions() as session:
            campaign = session.get(ScientificCampaign, campaign_id)
            return None if campaign is None else _scientific_campaign_record(session, campaign)

    def create_analysis_run(
        self,
        *,
        run_id: str,
        session_id: str,
        pipeline_release_id: str,
        input_manifest_digest: str,
        jobs: Iterable[JobDefinition],
        trigger: str = "automatic",
        promotion_policy: PromotionPolicy | str = PromotionPolicy.CURRENT,
    ) -> None:
        try:
            canonical_promotion_policy = PromotionPolicy(promotion_policy)
        except ValueError as error:
            raise ValueError(
                f"unknown analysis-run promotion policy: {promotion_policy!r}"
            ) from error
        definitions = tuple(jobs)
        by_identity = {
            (definition.stage_key, definition.scope_key): definition for definition in definitions
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
                run = AnalysisRun(
                    id=run_id,
                    session_id=session_id,
                    pipeline_release_id=pipeline_release_id,
                    trigger=trigger,
                    promotion_policy=canonical_promotion_policy.value,
                    state=AnalysisRunState.PENDING.value,
                    input_manifest_digest=input_manifest_digest,
                )
                session.add(run)
                session.flush()
                job_by_identity: dict[tuple[str, str], ProcessingJob] = {}
                for definition in definitions:
                    job = ProcessingJob(
                        run_id=run_id,
                        stage_key=definition.stage_key,
                        scope_key=definition.scope_key,
                        priority=definition.priority,
                        max_attempts=definition.max_attempts,
                    )
                    session.add(job)
                    job_by_identity[(definition.stage_key, definition.scope_key)] = job
                session.flush()
                for definition in definitions:
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
        except IntegrityError as error:
            if _constraint_name(error) == "uq_analysis_run_active_session":
                raise ActiveRunExistsError(
                    f"session {session_id!r} already has an active analysis run"
                ) from error
            raise

    def claim_job(self, *, worker_id: str, lease_for: timedelta) -> JobLease | None:
        _require_positive_duration(lease_for)
        with self._sessions.begin() as session:
            now = _database_now(session)
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
            return JobLease(
                job_id=job.id,
                run_id=job.run_id,
                stage_key=job.stage_key,
                scope_key=job.scope_key,
                attempt_number=job.attempt_count,
                worker_id=worker_id,
                lease_expires_at=expires_at,
            )

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

    def reclaim_expired_jobs(self, *, as_of: datetime | None = None) -> tuple[int, ...]:
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

    def register_product(self, product: ProductRegistration) -> int:
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
        }
        identity = {
            key: values[key]
            for key in ("run_id", "stage_key", "scope_key", "kind", "schema_version")
        }
        with self._sessions.begin() as session:
            run = session.get(AnalysisRun, product.run_id)
            if run is None:
                raise CatalogNotFoundError(f"analysis run is absent: {product.run_id}")
            statement = (
                insert(AnalysisProduct)
                .values(**values)
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
                return product_id
            existing = session.execute(
                select(AnalysisProduct).filter_by(**identity).with_for_update()
            ).scalar_one()
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise ProductConflictError(
                    f"product identity conflicts with existing product {existing.id}"
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

            products = session.execute(
                select(AnalysisProduct, AnalysisRun)
                .join(AnalysisRun, AnalysisRun.id == AnalysisProduct.run_id)
                .join(CaptureSession, CaptureSession.id == AnalysisRun.session_id)
                .outerjoin(CurrentAnalysis, CurrentAnalysis.run_id == AnalysisRun.id)
                .where(
                    AnalysisProduct.available.is_(True),
                    AnalysisProduct.byte_size > 0,
                    CurrentAnalysis.run_id.is_(None),
                    ~exists(
                        select(1).where(
                            ScientificCampaignStream.analysis_product_id == AnalysisProduct.id
                        )
                    ),
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
            session_id = session.scalar(
                select(AnalysisRun.session_id).where(AnalysisRun.id == product.run_id)
            )
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
    ) -> bool:
        """Register one already committed bundle; return True only when inserted."""

        if allocated_bytes < 0:
            raise ValueError("allocated_bytes cannot be negative")
        canonical_tags = tuple(sorted(set(tags)))
        with self._sessions.begin() as session:
            capture = session.execute(
                select(CaptureSession).where(CaptureSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if capture is not None:
                if (
                    capture.bundle_uri != bundle_uri
                    or capture.manifest_digest != manifest_digest
                    or capture.state == SessionState.PURGED.value
                ):
                    raise ProductConflictError(
                        f"recording bundle {session_id!r} conflicts with catalog identity"
                    )
                capture.allocated_bytes = allocated_bytes
                capture.raw_available = True
                capture.state = state.value
                if observed_start_at is not None:
                    capture.observed_start_at = observed_start_at
                if observed_end_at is not None:
                    capture.observed_end_at = observed_end_at
                return False
            session.add(
                CaptureSession(
                    id=session_id,
                    source_type=source_type,
                    state=state.value,
                    bundle_uri=bundle_uri,
                    manifest_digest=manifest_digest,
                    allocated_bytes=allocated_bytes,
                    raw_available=True,
                    attributes=attributes,
                    observed_start_at=observed_start_at,
                    observed_end_at=observed_end_at,
                )
            )
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
            return True

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
                select(CurrentAnalysis.run_id).where(CurrentAnalysis.run_id == run_id)
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

    def search_sessions(
        self, query: SessionSearch | None = None
    ) -> tuple[SessionSearchResult, ...]:
        query = SessionSearch() if query is None else query
        if query.limit <= 0 or query.limit > 1000:
            raise ValueError("search limit must be between 1 and 1000")
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

    def current_run_id(self, session_id: str) -> str | None:
        with self._sessions() as session:
            return session.scalar(
                select(CurrentAnalysis.run_id).where(CurrentAnalysis.session_id == session_id)
            )

    def presentation_snapshot(self, session_id: str) -> CatalogSessionReadSnapshot | None:
        """Resolve one immutable current-run view in a read-only transaction."""

        with self._sessions.begin() as session:
            _begin_consistent_read(session)
            return _presentation_snapshot(session, session_id)

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
                .where(ProcessingJob.state == JobState.LEASED.value)
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
                bundle_uri=capture.bundle_uri,
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


def _database_now(session: Session) -> datetime:
    value = session.scalar(select(func.clock_timestamp()))
    if value is None:
        raise RuntimeError("PostgreSQL did not return its current time")
    return _require_aware(value)


def _begin_consistent_read(session: Session) -> None:
    session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))


def _presentation_snapshot(
    session: Session,
    session_id: str,
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
        select(CurrentAnalysis.run_id).where(CurrentAnalysis.session_id == session_id)
    )
    if current_run_id is None:
        run = session.execute(
            select(AnalysisRun)
            .where(AnalysisRun.session_id == session_id)
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
            if is_current
            else ()
        )
        analysis = CatalogRunReadSnapshot(
            run_id=run.id,
            pipeline_release_id=run.pipeline_release_id,
            pipeline_configuration=release.configuration,
            promotion_policy=run.promotion_policy,
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


def _catalog_product_record(product: AnalysisProduct) -> CatalogProductRecord:
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
    return bool(
        session.scalar(
            select(exists().where(ScientificCampaignStream.analysis_product_id == product_id))
        )
    )


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


def _validate_campaign_stream_lineage(
    session: Session,
    stream: ScientificCampaignStreamRegistration,
) -> None:
    if not 0 <= stream.ordinal < 40:
        raise ValueError("scientific campaign stream ordinal must be in [0, 40)")
    if stream.status not in {"pass", "fail", "inconclusive", "insufficient"}:
        raise ValueError(f"unknown scientific stream status: {stream.status!r}")
    capture = session.execute(
        select(CaptureSession).where(CaptureSession.id == stream.session_id).with_for_update()
    ).scalar_one_or_none()
    radio_stream = session.get(RadioStream, stream.stream_id)
    run = session.get(AnalysisRun, stream.analysis_run_id)
    product = session.execute(
        select(AnalysisProduct)
        .where(AnalysisProduct.id == stream.analysis_product_id)
        .with_for_update()
    ).scalar_one_or_none()
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
    if run.state != AnalysisRunState.SUCCEEDED.value:
        raise InvalidStateError("scientific campaign analysis run is not sealed")
    if (
        run.manifest_uri != stream.analysis_run_uri
        or run.manifest_digest != stream.analysis_run_digest
    ):
        raise ProductConflictError("scientific campaign analysis run evidence disagrees")
    if (
        not product.available
        or product.purge_claim_token is not None
        or product.scope_key != radio_stream.id
        or product.kind != "starlink.matched-acceptance"
        or product.schema_version != 1
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
        result_status=campaign.result_status,
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
