"""Resumable long-duration acquisition soak evidence.

The harness deliberately uses the normal acquisition application and recording
store.  Its only special behaviour is how it schedules trials and persists
qualification evidence: one immutable file per trial plus one small aggregate
that is atomically replaced.  Recording retention is not changed here.
"""

from __future__ import annotations

import os
import platform
import resource
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from leo.acquisition import AcquisitionApplication, AdmissionEstimate, CaptureSessionResult
from leo.contracts.profile import CapturePlanV1
from leo.contracts.recording import RecordingManifestV1, RecordingManifestV3
from leo.contracts.states import CaptureState, StreamState
from leo.radio import RadioSource
from leo.storage import BundleNotFoundError, PublishedBundle, RecordingStore

SoakId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
SourceFactory = Callable[[str], RadioSource]
BacklogObserver = Callable[[], "ProcessingBacklogObservationV1"]
PostCommitObserver = Callable[[PublishedBundle], "PostCommitObservationV1"]
MonotonicNs = Callable[[], int]
UtcNs = Callable[[], int]
Wait = Callable[[Event, float], bool]
PeakRssBytes = Callable[[], int]

_MAX_DEFINITION_BYTES = 64 * 1024
_MAX_TRIAL_BYTES = 256 * 1024
_MAX_SUMMARY_BYTES = 64 * 1024
_POST_COMMIT_POLICY_VIOLATION = "post-commit observer failure count exceeds policy"


class SoakModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SoakConfigV1(SoakModel):
    """Scheduling controls; production uses 86,400 seconds and no trial limit."""

    schema_version: Literal[1] = 1
    duration_seconds: Annotated[float, Field(gt=0, le=7 * 24 * 60 * 60)] = 86_400
    cadence_seconds: Annotated[float, Field(ge=0, le=24 * 60 * 60)] = 0
    maximum_trials: Annotated[int | None, Field(gt=0)] = None


class SoakAcceptancePolicyV1(SoakModel):
    """Versioned, reviewable bounds for a successful soak.

    RSS is the process high-water mark.  Queue growth is measured from the
    observer reading taken when the soak definition is first created.
    """

    schema_version: Literal[1] = 1
    minimum_committed_fraction: Annotated[float, Field(ge=0, le=1)] = 1.0
    require_all_digests_valid: bool = True
    maximum_false_complete_count: Annotated[int, Field(ge=0)] = 0
    maximum_gap_count: Annotated[int, Field(ge=0)] = 0
    maximum_overflow_count: Annotated[int, Field(ge=0)] = 0
    maximum_admission_rejection_count: Annotated[int, Field(ge=0)] = 0
    maximum_peak_rss_growth_bytes: Annotated[int, Field(ge=0)] = 512 * 1024 * 1024
    maximum_processing_backlog_queued: Annotated[int, Field(ge=0)] = 10_000
    maximum_processing_backlog_growth: Annotated[int, Field(ge=0)] = 1_000
    maximum_storage_used_fraction: Annotated[float, Field(gt=0, le=1)] = 0.80
    minimum_dual_radio_overlap_fraction: Annotated[float, Field(ge=0, le=1)] = 0.99
    maximum_inter_capture_gap_seconds: Annotated[float | None, Field(ge=0)] = None
    maximum_post_commit_failure_count: Annotated[int | None, Field(ge=0)] = None


class ProcessingBacklogObservationV1(SoakModel):
    schema_version: Literal[1] = 1
    observed_utc_ns: Annotated[int, Field(ge=0)]
    available: bool = True
    queued: Annotated[int | None, Field(ge=0)] = None
    running: Annotated[int | None, Field(ge=0)] = None
    failed: Annotated[int | None, Field(ge=0)] = None
    oldest_queued_seconds: Annotated[float | None, Field(ge=0)] = None
    error: str | None = None

    @model_validator(mode="after")
    def _availability_is_consistent(self) -> Self:
        counts = (self.queued, self.running, self.failed)
        if self.available and any(value is None for value in counts):
            raise ValueError("available backlog observation requires all counts")
        if not self.available and self.error is None:
            raise ValueError("unavailable backlog observation requires an error")
        return self


class PostCommitObservationV1(SoakModel):
    """Result of catalog registration and processing-queue reconciliation."""

    schema_version: Literal[1] = 1
    observed_utc_ns: Annotated[int, Field(ge=0)]
    target_session_id: str
    attempted: bool
    succeeded: bool
    registered_session_ids: tuple[str, ...] = ()
    existing_session_ids: tuple[str, ...] = ()
    queued_run_ids: tuple[str, ...] = ()
    error: str | None = None

    @model_validator(mode="after")
    def _result_is_consistent(self) -> Self:
        if self.succeeded and (not self.attempted or self.error is not None):
            raise ValueError("successful post-commit observation must be attempted without error")
        if not self.succeeded and self.error is None:
            raise ValueError("unsuccessful post-commit observation requires an error")
        return self


class StorageObservationV1(SoakModel):
    schema_version: Literal[1] = 1
    observed_utc_ns: Annotated[int, Field(ge=0)]
    total_bytes: Annotated[int, Field(ge=0)]
    used_bytes: Annotated[int, Field(ge=0)]
    available_bytes: Annotated[int, Field(ge=0)]
    used_fraction: Annotated[float, Field(ge=0, le=1)]


class AdmissionObservationV1(SoakModel):
    schema_version: Literal[1] = 1
    evidence_scope: Literal["capture", "recovery"]
    admitted: bool
    required_free_bytes: Annotated[int, Field(ge=0)]
    available_free_bytes: Annotated[int, Field(ge=0)]
    used_fraction: Annotated[float | None, Field(ge=0, le=1)] = None
    warning: bool = False
    reason: str | None = None


class SoakDefinitionV1(SoakModel):
    kind: Literal["acquisition_soak_definition"] = "acquisition_soak_definition"
    schema_version: Literal[1] = 1
    soak_id: SoakId
    created_utc_ns: Annotated[int, Field(ge=0)]
    profile_name: str
    profile_revision_digest: str
    capture_plan_digest: str
    radio_ids: tuple[str, ...]
    recording_tag_policy: Literal["preserve_profile_tags_and_queue"] = (
        "preserve_profile_tags_and_queue"
    )
    configuration: SoakConfigV1
    policy: SoakAcceptancePolicyV1
    baseline_peak_rss_bytes: Annotated[int, Field(ge=0)]
    baseline_processing_backlog_queued: Annotated[int | None, Field(ge=0)] = None


class SoakTrialEvidenceV1(SoakModel):
    kind: Literal["acquisition_soak_trial"] = "acquisition_soak_trial"
    schema_version: Literal[1] = 1
    soak_id: SoakId
    trial_index: Annotated[int, Field(ge=0)]
    session_id: str
    recovered_after_interruption: bool
    scheduled_active_seconds: Annotated[float, Field(ge=0)]
    active_elapsed_seconds: Annotated[float, Field(ge=0)]
    capture_started_utc_ns: Annotated[int, Field(ge=0)]
    capture_finished_utc_ns: Annotated[int, Field(ge=0)]
    acquisition_elapsed_seconds: Annotated[float, Field(ge=0)]
    inter_capture_gap_seconds: Annotated[float | None, Field(ge=0)] = None
    recorded_span_seconds: Annotated[float, Field(ge=0)] = 0
    state: CaptureState
    bundle_uri: str | None = None
    manifest_sha256: str | None = None
    digest_valid: bool | None = None
    verification_error: str | None = None
    requested_sample_count: Annotated[int, Field(ge=0)] = 0
    captured_sample_count: Annotated[int, Field(ge=0)] = 0
    gap_count: Annotated[int, Field(ge=0)] = 0
    overflow_count: Annotated[int, Field(ge=0)] = 0
    estimated_start_skew_ns: Annotated[int | None, Field(ge=0)] = None
    start_skew_uncertainty_ns: Annotated[int | None, Field(ge=0)] = None
    estimated_overlap_ns: Annotated[int | None, Field(ge=0)] = None
    guaranteed_overlap_ns: Annotated[int | None, Field(ge=0)] = None
    overlap_fraction: Annotated[float | None, Field(ge=0, le=1)] = None
    false_complete_count: Annotated[int, Field(ge=0)] = 0
    recording_tags: tuple[str, ...] = ()
    post_commit: PostCommitObservationV1
    process_peak_rss_bytes: Annotated[int, Field(ge=0)]
    storage_before: StorageObservationV1
    storage_after: StorageObservationV1
    admission: AdmissionObservationV1
    processing_backlog_before: ProcessingBacklogObservationV1
    processing_backlog_after: ProcessingBacklogObservationV1
    errors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _evidence_is_consistent(self) -> Self:
        if self.capture_finished_utc_ns < self.capture_started_utc_ns:
            raise ValueError("capture finish precedes capture start")
        present = (self.bundle_uri is not None, self.manifest_sha256 is not None)
        if present[0] != present[1]:
            raise ValueError("bundle URI and manifest digest must appear together")
        if self.digest_valid is not None and self.bundle_uri is None:
            raise ValueError("digest result requires a bundle")
        if self.verification_error is not None and self.digest_valid is not False:
            raise ValueError("verification error requires an invalid digest result")
        return self


class SoakSummaryV1(SoakModel):
    """Bounded aggregate; trial evidence remains in immutable sibling files."""

    kind: Literal["acquisition_soak_summary"] = "acquisition_soak_summary"
    schema_version: Literal[1] = 1
    soak_id: SoakId
    updated_utc_ns: Annotated[int, Field(ge=0)]
    status: Literal["running", "interrupted", "failed", "complete"]
    completion_reason: Literal["duration", "trial_limit", "cancelled", "policy", "running"]
    complete: bool
    passed: bool
    completed_trial_count: Annotated[int, Field(ge=0)]
    committed_count: Annotated[int, Field(ge=0)]
    degraded_count: Annotated[int, Field(ge=0)]
    failed_count: Annotated[int, Field(ge=0)]
    committed_fraction: Annotated[float, Field(ge=0, le=1)]
    active_elapsed_seconds: Annotated[float, Field(ge=0)]
    recorded_seconds: Annotated[float, Field(ge=0)]
    duty_cycle: Annotated[float, Field(ge=0)]
    total_requested_sample_count: Annotated[int, Field(ge=0)]
    total_captured_sample_count: Annotated[int, Field(ge=0)]
    total_gap_count: Annotated[int, Field(ge=0)]
    total_overflow_count: Annotated[int, Field(ge=0)]
    false_complete_count: Annotated[int, Field(ge=0)]
    digest_invalid_count: Annotated[int, Field(ge=0)]
    admission_rejection_count: Annotated[int, Field(ge=0)]
    post_commit_success_count: Annotated[int, Field(ge=0)]
    post_commit_failure_count: Annotated[int, Field(ge=0)]
    queued_run_count: Annotated[int, Field(ge=0)]
    maximum_inter_capture_gap_seconds: Annotated[float | None, Field(ge=0)] = None
    minimum_overlap_fraction: Annotated[float | None, Field(ge=0, le=1)] = None
    maximum_start_skew_ns: Annotated[int | None, Field(ge=0)] = None
    maximum_peak_rss_bytes: Annotated[int, Field(ge=0)]
    peak_rss_growth_bytes: Annotated[int, Field(ge=0)]
    maximum_processing_backlog_queued: Annotated[int | None, Field(ge=0)] = None
    processing_backlog_growth: int | None = None
    maximum_storage_used_fraction: Annotated[float, Field(ge=0, le=1)]
    minimum_storage_available_bytes: Annotated[int, Field(ge=0)]
    last_trial_index: Annotated[int | None, Field(ge=0)] = None
    last_session_id: str | None = None
    evidence_directory: str
    policy: SoakAcceptancePolicyV1
    policy_violations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _status_is_consistent(self) -> Self:
        if self.passed and (not self.complete or self.status != "complete"):
            raise ValueError("only a completed soak can pass")
        if self.status == "running" and self.completion_reason != "running":
            raise ValueError("running summary has a terminal reason")
        return self


class AcquisitionSoakHarness:
    """Run and resume a bounded-evidence acquisition soak."""

    def __init__(
        self,
        store: RecordingStore,
        application: AcquisitionApplication,
        *,
        output_root: Path,
        backlog_observer: BacklogObserver | None = None,
        post_commit_observer: PostCommitObserver | None = None,
        monotonic_ns: MonotonicNs = time.monotonic_ns,
        utc_ns: UtcNs = time.time_ns,
        wait: Wait | None = None,
        peak_rss_bytes: PeakRssBytes | None = None,
    ) -> None:
        _reject_qnap_path(store.root)
        _reject_qnap_path(output_root)
        self.store = store
        self.application = application
        self.output_root = output_root
        self._backlog_observer = backlog_observer
        self._post_commit_observer = post_commit_observer
        self._monotonic_ns = monotonic_ns
        self._utc_ns = utc_ns
        self._wait = wait or _event_wait
        self._peak_rss_bytes = peak_rss_bytes or _process_peak_rss_bytes

    def run(
        self,
        plan: CapturePlanV1,
        source_factory: SourceFactory,
        *,
        soak_id: SoakId,
        configuration: SoakConfigV1 | None = None,
        policy: SoakAcceptancePolicyV1 | None = None,
        cancel: Event | None = None,
        resume: bool = True,
    ) -> SoakSummaryV1:
        config = configuration or SoakConfigV1()
        acceptance = policy or SoakAcceptancePolicyV1()
        if "QUALIFICATION" in plan.profile_revision.profile.tags:
            raise ValueError(
                "soak recording policy forbids the QUALIFICATION tag because soak "
                "captures must enter the normal processing queue"
            )
        event = cancel or Event()
        run_root = self.output_root / soak_id
        _reject_qnap_path(run_root)
        definition_path = run_root / "definition.json"
        summary_path = run_root / "summary.json"
        evidence_root = run_root / "trials"
        definition = self._definition(
            definition_path,
            plan,
            soak_id,
            config,
            acceptance,
            resume,
        )
        evidence_root.mkdir(parents=True, exist_ok=True)
        trials = _load_trials(evidence_root, soak_id)
        active_before_segment = max(
            (trial.active_elapsed_seconds for trial in trials),
            default=0.0,
        )
        segment_started_ns = self._monotonic_ns()
        summary = _summarize(
            definition,
            trials,
            evidence_root,
            updated_utc_ns=self._utc_ns(),
            active_elapsed_seconds=active_before_segment,
            status="running",
            completion_reason="running",
        )
        if trials and _requires_early_stop(summary.policy_violations):
            summary = summary.model_copy(
                update={
                    "status": "failed",
                    "completion_reason": "policy",
                    "complete": False,
                    "passed": False,
                }
            )
        _atomic_replace_model(summary_path, summary, _MAX_SUMMARY_BYTES)
        if summary.status == "failed":
            return summary

        while True:
            active_now = (
                active_before_segment + max(0, self._monotonic_ns() - segment_started_ns) / 1e9
            )
            reason = _completion_reason(config, len(trials), active_now)
            if reason is not None:
                summary = _summarize(
                    definition,
                    trials,
                    evidence_root,
                    updated_utc_ns=self._utc_ns(),
                    active_elapsed_seconds=active_now,
                    status="complete",
                    completion_reason=reason,
                )
                _atomic_replace_model(summary_path, summary, _MAX_SUMMARY_BYTES)
                return summary
            if event.is_set():
                summary = _summarize(
                    definition,
                    trials,
                    evidence_root,
                    updated_utc_ns=self._utc_ns(),
                    active_elapsed_seconds=active_now,
                    status="interrupted",
                    completion_reason="cancelled",
                )
                _atomic_replace_model(summary_path, summary, _MAX_SUMMARY_BYTES)
                return summary

            index = len(trials)
            scheduled_active = index * config.cadence_seconds
            delay = scheduled_active - active_now
            if delay > 0:
                self._wait(event, delay)
                continue
            if event.is_set():
                continue
            trial_started_monotonic_ns = self._monotonic_ns()
            active_at_start = (
                active_before_segment
                + max(0, trial_started_monotonic_ns - segment_started_ns) / 1e9
            )
            trial = self._run_or_recover_trial(
                definition,
                plan,
                source_factory,
                index=index,
                scheduled_active_seconds=scheduled_active,
                active_at_start=active_at_start,
                previous=trials[-1] if trials else None,
                cancel=event,
                trial_started_monotonic_ns=trial_started_monotonic_ns,
            )
            trial_path = evidence_root / f"trial-{index:08d}.json"
            _atomic_create_model(trial_path, trial, _MAX_TRIAL_BYTES)
            trials.append(trial)
            active_now = trial.active_elapsed_seconds
            summary = _summarize(
                definition,
                trials,
                evidence_root,
                updated_utc_ns=self._utc_ns(),
                active_elapsed_seconds=active_now,
                status="running",
                completion_reason="running",
            )
            if _requires_early_stop(summary.policy_violations):
                summary = summary.model_copy(
                    update={
                        "status": "failed",
                        "completion_reason": "policy",
                        "complete": False,
                        "passed": False,
                    }
                )
                _atomic_replace_model(summary_path, summary, _MAX_SUMMARY_BYTES)
                return summary
            _atomic_replace_model(summary_path, summary, _MAX_SUMMARY_BYTES)

    def _definition(
        self,
        path: Path,
        plan: CapturePlanV1,
        soak_id: str,
        config: SoakConfigV1,
        policy: SoakAcceptancePolicyV1,
        resume: bool,
    ) -> SoakDefinitionV1:
        if path.exists():
            if not resume:
                raise FileExistsError(f"soak definition already exists: {path}")
            existing = _read_model(path, SoakDefinitionV1, _MAX_DEFINITION_BYTES)
            observed = (
                existing.soak_id,
                existing.profile_revision_digest,
                existing.capture_plan_digest,
                existing.radio_ids,
                existing.configuration,
                existing.policy,
            )
            expected = (
                soak_id,
                plan.profile_revision.revision_digest,
                plan.plan_digest,
                plan.radio_ids,
                config,
                policy,
            )
            if observed != expected:
                raise ValueError("existing soak definition does not match this request")
            return existing
        if path.parent.exists() and any(path.parent.iterdir()):
            raise ValueError("soak directory has evidence but no definition")
        baseline_backlog = self._observe_backlog()
        definition = SoakDefinitionV1(
            soak_id=soak_id,
            created_utc_ns=self._utc_ns(),
            profile_name=plan.profile_revision.profile.name,
            profile_revision_digest=plan.profile_revision.revision_digest,
            capture_plan_digest=plan.plan_digest,
            radio_ids=plan.radio_ids,
            configuration=config,
            policy=policy,
            baseline_peak_rss_bytes=self._peak_rss_bytes(),
            baseline_processing_backlog_queued=(
                baseline_backlog.queued if baseline_backlog.available else None
            ),
        )
        _atomic_create_model(path, definition, _MAX_DEFINITION_BYTES)
        return definition

    def _run_or_recover_trial(
        self,
        definition: SoakDefinitionV1,
        plan: CapturePlanV1,
        source_factory: SourceFactory,
        *,
        index: int,
        scheduled_active_seconds: float,
        active_at_start: float,
        previous: SoakTrialEvidenceV1 | None,
        cancel: Event,
        trial_started_monotonic_ns: int,
    ) -> SoakTrialEvidenceV1:
        session_id = _session_id(definition.soak_id, index)
        storage_before = self._observe_storage()
        backlog_before = self._observe_backlog()
        admission = self.application.estimate(plan)
        capture_started_utc_ns = self._utc_ns()
        recovered = False
        incomplete_spool = False
        result: CaptureSessionResult | None = None
        try:
            bundle = self.store.inspect(session_id)
            recovered = True
        except BundleNotFoundError:
            bundle = None
            spool = self.store.spool_root / f"{session_id}.partial"
            incomplete_spool = spool.exists()
            if incomplete_spool:
                recovered = True
            elif admission.admitted:
                sources = {radio_id: source_factory(radio_id) for radio_id in plan.radio_ids}
                result = self.application.once(
                    plan,
                    sources,
                    session_id=session_id,
                    cancel=cancel,
                )
                bundle = result.bundle
        capture_finished_utc_ns = max(capture_started_utc_ns, self._utc_ns())
        ended_monotonic_ns = self._monotonic_ns()
        elapsed = max(0, ended_monotonic_ns - trial_started_monotonic_ns) / 1e9
        if recovered and bundle is not None:
            capture_started_utc_ns = bundle.manifest.created_utc_ns
            capture_finished_utc_ns = bundle.manifest.finalized_utc_ns
            elapsed = max(0, capture_finished_utc_ns - capture_started_utc_ns) / 1e9
        active_elapsed = max(active_at_start + elapsed, scheduled_active_seconds)
        post_commit = self._observe_post_commit(session_id, bundle)
        storage_after = self._observe_storage()
        backlog_after = self._observe_backlog()
        admission = admission if result is None else result.admission
        if bundle is None:
            state = CaptureState.FAILED if result is None else result.state
            if result is not None:
                errors = result.errors
            elif incomplete_spool:
                errors = ("incomplete spool from an interrupted soak trial",)
            else:
                detail = f": {admission.policy_reason}" if admission.policy_reason else ""
                errors = (f"storage admission rejected{detail}",)
            return SoakTrialEvidenceV1(
                soak_id=definition.soak_id,
                trial_index=index,
                session_id=session_id,
                recovered_after_interruption=recovered,
                scheduled_active_seconds=scheduled_active_seconds,
                active_elapsed_seconds=active_elapsed,
                capture_started_utc_ns=capture_started_utc_ns,
                capture_finished_utc_ns=capture_finished_utc_ns,
                acquisition_elapsed_seconds=elapsed,
                inter_capture_gap_seconds=_inter_capture_gap(previous, capture_started_utc_ns),
                state=state,
                false_complete_count=int(state is CaptureState.COMMITTED),
                post_commit=post_commit,
                process_peak_rss_bytes=self._peak_rss_bytes(),
                storage_before=storage_before,
                storage_after=storage_after,
                admission=_admission_observation(admission, recovery=recovered),
                processing_backlog_before=backlog_before,
                processing_backlog_after=backlog_after,
                errors=errors,
            )
        return self._bundle_evidence(
            definition,
            bundle,
            index=index,
            recovered=recovered,
            scheduled_active_seconds=scheduled_active_seconds,
            active_elapsed_seconds=active_elapsed,
            acquisition_elapsed_seconds=elapsed,
            previous=previous,
            admission=admission,
            storage_before=storage_before,
            storage_after=storage_after,
            backlog_before=backlog_before,
            backlog_after=backlog_after,
            post_commit=post_commit,
            result_errors=() if result is None else result.errors,
        )

    def _bundle_evidence(
        self,
        definition: SoakDefinitionV1,
        bundle: PublishedBundle,
        *,
        index: int,
        recovered: bool,
        scheduled_active_seconds: float,
        active_elapsed_seconds: float,
        acquisition_elapsed_seconds: float,
        previous: SoakTrialEvidenceV1 | None,
        admission: AdmissionEstimate,
        storage_before: StorageObservationV1,
        storage_after: StorageObservationV1,
        backlog_before: ProcessingBacklogObservationV1,
        backlog_after: ProcessingBacklogObservationV1,
        post_commit: PostCommitObservationV1,
        result_errors: tuple[str, ...],
    ) -> SoakTrialEvidenceV1:
        manifest = bundle.manifest
        verification_error = None
        try:
            self.store.verify(bundle)
            digest_valid = True
        except Exception as error:
            digest_valid = False
            verification_error = f"{type(error).__name__}: {error}"
        started_utc_ns, finished_utc_ns = _manifest_capture_bounds(manifest)
        requested_samples = sum(stream.requested_sample_count for stream in manifest.streams)
        captured_samples = sum(stream.captured_sample_count for stream in manifest.streams)
        gaps = sum(stream.continuity.gap_count for stream in manifest.streams)
        overflows = sum(stream.continuity.overflow_count for stream in manifest.streams)
        false_stream = any(
            stream.state is StreamState.COMPLETE
            and (
                not digest_valid
                or stream.captured_sample_count != stream.requested_sample_count
                or stream.timing is None
            )
            for stream in manifest.streams
        )
        false_capture = manifest.state is CaptureState.COMMITTED and (
            any(stream.state is not StreamState.COMPLETE for stream in manifest.streams)
            or gaps > 0
            or overflows > 0
        )
        sample_rate_hz = manifest.capture_plan.profile_revision.profile.sample_rate_hz
        recorded_span_seconds = max(
            (stream.captured_sample_count / sample_rate_hz for stream in manifest.streams),
            default=0,
        )
        sync = manifest.synchronization
        return SoakTrialEvidenceV1(
            soak_id=definition.soak_id,
            trial_index=index,
            session_id=manifest.session_id,
            recovered_after_interruption=recovered,
            scheduled_active_seconds=scheduled_active_seconds,
            active_elapsed_seconds=active_elapsed_seconds,
            capture_started_utc_ns=started_utc_ns,
            capture_finished_utc_ns=finished_utc_ns,
            acquisition_elapsed_seconds=acquisition_elapsed_seconds,
            inter_capture_gap_seconds=_inter_capture_gap(previous, started_utc_ns),
            recorded_span_seconds=recorded_span_seconds,
            state=manifest.state,
            bundle_uri=bundle.uri,
            manifest_sha256=bundle.manifest_sha256,
            digest_valid=digest_valid,
            verification_error=verification_error,
            requested_sample_count=requested_samples,
            captured_sample_count=captured_samples,
            gap_count=gaps,
            overflow_count=overflows,
            estimated_start_skew_ns=sync.estimated_start_skew_ns,
            start_skew_uncertainty_ns=sync.start_skew_uncertainty_ns,
            estimated_overlap_ns=sync.estimated_overlap_ns,
            guaranteed_overlap_ns=sync.guaranteed_overlap_ns,
            overlap_fraction=sync.overlap_fraction,
            false_complete_count=int(false_stream or false_capture),
            recording_tags=manifest.tags,
            post_commit=post_commit,
            process_peak_rss_bytes=self._peak_rss_bytes(),
            storage_before=storage_before,
            storage_after=storage_after,
            admission=_admission_observation(admission, recovery=recovered),
            processing_backlog_before=backlog_before,
            processing_backlog_after=backlog_after,
            errors=result_errors,
        )

    def _observe_post_commit(
        self,
        session_id: str,
        bundle: PublishedBundle | None,
    ) -> PostCommitObservationV1:
        observed = self._utc_ns()
        if bundle is None:
            return PostCommitObservationV1(
                observed_utc_ns=observed,
                target_session_id=session_id,
                attempted=False,
                succeeded=False,
                error="no published bundle was available for post-commit reconciliation",
            )
        if self._post_commit_observer is None:
            return PostCommitObservationV1(
                observed_utc_ns=observed,
                target_session_id=session_id,
                attempted=False,
                succeeded=False,
                error="post-commit observer is not configured",
            )
        try:
            result = self._post_commit_observer(bundle)
            if result.target_session_id != session_id:
                raise ValueError("post-commit observer returned evidence for another session")
            return result
        except Exception as error:
            return PostCommitObservationV1(
                observed_utc_ns=observed,
                target_session_id=session_id,
                attempted=True,
                succeeded=False,
                error=f"{type(error).__name__}: {error}",
            )

    def _observe_storage(self) -> StorageObservationV1:
        statistics = os.statvfs(self.store.root)
        block_size = statistics.f_frsize or statistics.f_bsize
        total = statistics.f_blocks * block_size
        available = statistics.f_bavail * block_size
        used = (statistics.f_blocks - statistics.f_bfree) * block_size
        return StorageObservationV1(
            observed_utc_ns=self._utc_ns(),
            total_bytes=total,
            used_bytes=used,
            available_bytes=available,
            used_fraction=0 if total == 0 else used / total,
        )

    def _observe_backlog(self) -> ProcessingBacklogObservationV1:
        observed = self._utc_ns()
        if self._backlog_observer is None:
            return ProcessingBacklogObservationV1(
                observed_utc_ns=observed,
                available=False,
                error="processing backlog observer is not configured",
            )
        try:
            return self._backlog_observer()
        except Exception as error:
            return ProcessingBacklogObservationV1(
                observed_utc_ns=observed,
                available=False,
                error=f"{type(error).__name__}: {error}",
            )


def _summarize(
    definition: SoakDefinitionV1,
    trials: list[SoakTrialEvidenceV1],
    evidence_root: Path,
    *,
    updated_utc_ns: int,
    active_elapsed_seconds: float,
    status: Literal["running", "interrupted", "failed", "complete"],
    completion_reason: Literal["duration", "trial_limit", "cancelled", "policy", "running"],
) -> SoakSummaryV1:
    completed = len(trials)
    committed = sum(trial.state is CaptureState.COMMITTED for trial in trials)
    recorded_seconds = sum(trial.recorded_span_seconds for trial in trials)
    inter_capture_gaps = tuple(
        trial.inter_capture_gap_seconds
        for trial in trials
        if trial.inter_capture_gap_seconds is not None
    )
    overlap = tuple(
        trial.overlap_fraction for trial in trials if trial.overlap_fraction is not None
    )
    skews = tuple(
        trial.estimated_start_skew_ns
        for trial in trials
        if trial.estimated_start_skew_ns is not None
    )
    rss = tuple(trial.process_peak_rss_bytes for trial in trials)
    queued = tuple(
        observation.queued
        for trial in trials
        for observation in (
            trial.processing_backlog_before,
            trial.processing_backlog_after,
        )
        if observation.available and observation.queued is not None
    )
    storage = tuple(
        observation
        for trial in trials
        for observation in (trial.storage_before, trial.storage_after)
    )
    maximum_rss = max((definition.baseline_peak_rss_bytes, *rss))
    maximum_queue = max(queued) if queued else None
    queue_growth = (
        None
        if maximum_queue is None or definition.baseline_processing_backlog_queued is None
        else maximum_queue - definition.baseline_processing_backlog_queued
    )
    violations = _policy_violations(
        definition,
        trials,
        committed=committed,
        maximum_rss=maximum_rss,
        maximum_queue=maximum_queue,
        queue_growth=queue_growth,
        maximum_storage=max((item.used_fraction for item in storage), default=0),
        inter_capture_gaps=inter_capture_gaps,
        overlap=overlap,
    )
    terminal_complete = status == "complete"
    return SoakSummaryV1(
        soak_id=definition.soak_id,
        updated_utc_ns=updated_utc_ns,
        status=status,
        completion_reason=completion_reason,
        complete=terminal_complete,
        passed=terminal_complete and not violations,
        completed_trial_count=completed,
        committed_count=committed,
        degraded_count=sum(trial.state is CaptureState.DEGRADED for trial in trials),
        failed_count=sum(trial.state is CaptureState.FAILED for trial in trials),
        committed_fraction=committed / completed if completed else 0,
        active_elapsed_seconds=active_elapsed_seconds,
        recorded_seconds=recorded_seconds,
        duty_cycle=(recorded_seconds / active_elapsed_seconds if active_elapsed_seconds else 0),
        total_requested_sample_count=sum(trial.requested_sample_count for trial in trials),
        total_captured_sample_count=sum(trial.captured_sample_count for trial in trials),
        total_gap_count=sum(trial.gap_count for trial in trials),
        total_overflow_count=sum(trial.overflow_count for trial in trials),
        false_complete_count=sum(trial.false_complete_count for trial in trials),
        digest_invalid_count=sum(trial.digest_valid is False for trial in trials),
        admission_rejection_count=sum(
            trial.admission.evidence_scope == "capture" and not trial.admission.admitted
            for trial in trials
        ),
        post_commit_success_count=sum(
            trial.bundle_uri is not None and trial.post_commit.succeeded for trial in trials
        ),
        post_commit_failure_count=sum(
            trial.bundle_uri is not None and not trial.post_commit.succeeded for trial in trials
        ),
        queued_run_count=len(
            {run_id for trial in trials for run_id in trial.post_commit.queued_run_ids}
        ),
        maximum_inter_capture_gap_seconds=(max(inter_capture_gaps) if inter_capture_gaps else None),
        minimum_overlap_fraction=min(overlap) if overlap else None,
        maximum_start_skew_ns=max(skews) if skews else None,
        maximum_peak_rss_bytes=maximum_rss,
        peak_rss_growth_bytes=maximum_rss - definition.baseline_peak_rss_bytes,
        maximum_processing_backlog_queued=maximum_queue,
        processing_backlog_growth=queue_growth,
        maximum_storage_used_fraction=max((item.used_fraction for item in storage), default=0),
        minimum_storage_available_bytes=min((item.available_bytes for item in storage), default=0),
        last_trial_index=trials[-1].trial_index if trials else None,
        last_session_id=trials[-1].session_id if trials else None,
        evidence_directory=str(evidence_root),
        policy=definition.policy,
        policy_violations=violations,
    )


def _policy_violations(
    definition: SoakDefinitionV1,
    trials: list[SoakTrialEvidenceV1],
    *,
    committed: int,
    maximum_rss: int,
    maximum_queue: int | None,
    queue_growth: int | None,
    maximum_storage: float,
    inter_capture_gaps: tuple[float, ...],
    overlap: tuple[float, ...],
) -> tuple[str, ...]:
    policy = definition.policy
    completed = len(trials)
    violations: list[str] = []
    if completed and committed / completed < policy.minimum_committed_fraction:
        violations.append("committed capture fraction is below policy")
    if policy.require_all_digests_valid and any(
        trial.bundle_uri is not None and trial.digest_valid is not True for trial in trials
    ):
        violations.append("one or more recording digests are invalid or unverified")
    if sum(trial.false_complete_count for trial in trials) > policy.maximum_false_complete_count:
        violations.append("false-complete count exceeds policy")
    if sum(trial.gap_count for trial in trials) > policy.maximum_gap_count:
        violations.append("sample gap count exceeds policy")
    if sum(trial.overflow_count for trial in trials) > policy.maximum_overflow_count:
        violations.append("radio overflow count exceeds policy")
    if (
        sum(
            trial.admission.evidence_scope == "capture" and not trial.admission.admitted
            for trial in trials
        )
        > policy.maximum_admission_rejection_count
    ):
        violations.append("storage admission rejection count exceeds policy")
    if maximum_rss - definition.baseline_peak_rss_bytes > policy.maximum_peak_rss_growth_bytes:
        violations.append("process peak RSS growth exceeds policy")
    if maximum_queue is not None and maximum_queue > policy.maximum_processing_backlog_queued:
        violations.append("processing backlog queue exceeds policy")
    if queue_growth is not None and queue_growth > policy.maximum_processing_backlog_growth:
        violations.append("processing backlog growth exceeds policy")
    if maximum_storage > policy.maximum_storage_used_fraction:
        violations.append("storage utilization exceeds policy")
    if (
        policy.maximum_inter_capture_gap_seconds is not None
        and inter_capture_gaps
        and max(inter_capture_gaps) > policy.maximum_inter_capture_gap_seconds
    ):
        violations.append("inter-capture gap exceeds policy")
    if (
        completed
        and len(definition.radio_ids) == 2
        and (not overlap or min(overlap) < policy.minimum_dual_radio_overlap_fraction)
    ):
        violations.append("dual-radio overlap is below policy")
    post_commit_failures = sum(
        trial.bundle_uri is not None and not trial.post_commit.succeeded for trial in trials
    )
    if (
        policy.maximum_post_commit_failure_count is not None
        and post_commit_failures > policy.maximum_post_commit_failure_count
    ):
        violations.append(_POST_COMMIT_POLICY_VIOLATION)
    return tuple(violations)


def _requires_early_stop(violations: tuple[str, ...]) -> bool:
    """Database registration failures are durable evidence, not capture failures.

    They reject the final full-system gate but acquisition continues so a later
    reconciliation callback can register recordings committed during an outage.
    Resource growth and scientific-integrity failures remain fail-fast.
    """

    return any(violation != _POST_COMMIT_POLICY_VIOLATION for violation in violations)


def _manifest_capture_bounds(
    manifest: RecordingManifestV1 | RecordingManifestV3,
) -> tuple[int, int]:
    starts = tuple(
        stream.timing.first_sample.estimate_utc_ns
        for stream in manifest.streams
        if stream.timing is not None
    )
    finishes = tuple(
        stream.timing.last_sample.estimate_utc_ns
        for stream in manifest.streams
        if stream.timing is not None
    )
    return (
        min(starts) if starts else manifest.created_utc_ns,
        max(finishes) if finishes else manifest.finalized_utc_ns,
    )


def _inter_capture_gap(
    previous: SoakTrialEvidenceV1 | None,
    capture_started_utc_ns: int,
) -> float | None:
    if previous is None:
        return None
    return max(0, capture_started_utc_ns - previous.capture_finished_utc_ns) / 1e9


def _admission_observation(
    admission: AdmissionEstimate,
    *,
    recovery: bool,
) -> AdmissionObservationV1:
    return AdmissionObservationV1(
        evidence_scope="recovery" if recovery else "capture",
        admitted=admission.admitted,
        required_free_bytes=admission.required_free_bytes,
        available_free_bytes=admission.available_free_bytes,
        used_fraction=admission.storage_used_fraction,
        warning=admission.storage_warning,
        reason=admission.policy_reason,
    )


def _completion_reason(
    config: SoakConfigV1,
    completed_trials: int,
    active_elapsed_seconds: float,
) -> Literal["duration", "trial_limit"] | None:
    if config.maximum_trials is not None and completed_trials >= config.maximum_trials:
        return "trial_limit"
    if completed_trials and active_elapsed_seconds >= config.duration_seconds:
        return "duration"
    return None


def _session_id(soak_id: str, index: int) -> str:
    return f"{soak_id}-trial-{index + 1:08d}"


def _load_trials(root: Path, soak_id: str) -> list[SoakTrialEvidenceV1]:
    trials: list[SoakTrialEvidenceV1] = []
    for expected, path in enumerate(sorted(root.glob("trial-*.json"))):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"soak evidence is not a regular file: {path}")
        trial = _read_model(path, SoakTrialEvidenceV1, _MAX_TRIAL_BYTES)
        if (
            trial.soak_id != soak_id
            or trial.trial_index != expected
            or trial.session_id != _session_id(soak_id, expected)
            or path.name != f"trial-{expected:08d}.json"
        ):
            raise ValueError("soak trial evidence is non-contiguous or mismatched")
        trials.append(trial)
    return trials


def _read_model[SoakModelT: SoakModel](
    path: Path,
    model_type: type[SoakModelT],
    maximum_bytes: int,
) -> SoakModelT:
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise ValueError(f"qualification evidence size is invalid: {path}")
    return model_type.model_validate_json(path.read_bytes())


def _atomic_create_model(path: Path, model: BaseModel, maximum_bytes: int) -> None:
    _reject_qnap_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump_json(indent=2).encode("utf-8")
    if len(payload) > maximum_bytes:
        raise ValueError("qualification evidence exceeded its bounded file size")
    temporary = path.with_name(f".{path.name}.{os.getpid()}-{uuid4().hex}.partial")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_replace_model(path: Path, model: BaseModel, maximum_bytes: int) -> None:
    _reject_qnap_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump_json(indent=2).encode("utf-8")
    if len(payload) > maximum_bytes:
        raise ValueError("qualification aggregate exceeded its bounded file size")
    temporary = path.with_name(f".{path.name}.{os.getpid()}-{uuid4().hex}.partial")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _event_wait(event: Event, seconds: float) -> bool:
    return event.wait(seconds)


def _process_peak_rss_bytes() -> int:
    observed = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(observed if platform.system() == "Darwin" else observed * 1024)


def _reject_qnap_path(path: Path) -> None:
    resolved = path.resolve(strict=False)
    qnap = Path("/mnt/qnap01")
    if resolved == qnap or qnap in resolved.parents:
        raise ValueError("soak outputs cannot be written beneath read-only /mnt/qnap01")
