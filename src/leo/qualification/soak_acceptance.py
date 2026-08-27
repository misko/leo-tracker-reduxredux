"""Read-only, reproducible final acceptance audit for acquisition soaks."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import bindparam, text

from leo.analysis.graphs import ComputeTier, long_dwell_stage_specs
from leo.catalog import create_catalog_engine
from leo.contracts.recording import RecordingManifestV4
from leo.contracts.states import CaptureState
from leo.qualification.soak import (
    SoakDefinitionV1,
    SoakSummaryV1,
    SoakTrialEvidenceV1,
    _summarize,
)
from leo.storage import RecordingStore

_TRIAL_NAME = re.compile(r"^trial-(\d{8})\.json$")
_MAX_DEFINITION_BYTES = 64 * 1024
_MAX_SUMMARY_BYTES = 64 * 1024
_MAX_TRIAL_BYTES = 256 * 1024
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_STANDARD_STAGE_KEYS = tuple(spec.key for spec in long_dwell_stage_specs(ComputeTier.STANDARD))


class AcceptanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SoakExternalThresholdsV1(AcceptanceModel):
    """Predeclared WP10 thresholds not present in the soak v1 policy."""

    schema_version: Literal[1] = 1
    required_active_seconds: Annotated[float, Field(gt=0)] = 86_400
    minimum_sample_derived_duty_cycle: Annotated[float, Field(ge=0, le=1)] = 0.50
    maximum_inter_capture_gap_seconds: Annotated[float, Field(ge=0)] = 30
    maximum_soak_origin_pending_or_leased: Annotated[int, Field(gt=0)] = 1_000
    final_active_window_seconds: Annotated[float, Field(gt=0)] = 6 * 60 * 60
    maximum_active_wall_delta_seconds: Annotated[float, Field(ge=0)] = 10
    expected_jobs_per_run: Annotated[int, Field(gt=0)] = 30
    expected_pipeline_release_id: str = "standard-v1"
    expected_stage_keys: tuple[str, ...] = _STANDARD_STAGE_KEYS


class SoakAcceptanceCheckV1(AcceptanceModel):
    name: str
    passed: bool
    detail: str


class RuntimeContinuityEvidenceV1(AcceptanceModel):
    kind: Literal["systemd_runtime_continuity"] = "systemd_runtime_continuity"
    schema_version: Literal[1] = 1
    soak_id: Annotated[str, Field(min_length=1)]
    unit_name: Annotated[str, Field(min_length=1)]
    invocation_id: Annotated[str, Field(min_length=1)]
    exec_main_pid: Annotated[int, Field(gt=0)]
    main_pid_at_observation: Annotated[int, Field(ge=0)]
    n_restarts: Annotated[int, Field(ge=0)]
    unit_invocation_start_utc_ns: Annotated[int, Field(ge=0)]
    exec_main_start_utc_ns: Annotated[int, Field(ge=0)]
    observed_utc_ns: Annotated[int, Field(ge=0)]


def capture_systemd_runtime_continuity(
    soak_id: str,
    output_path: Path,
    *,
    command_runner: Callable[[tuple[str, ...]], str] | None = None,
    observed_utc_ns: int | None = None,
) -> RuntimeContinuityEvidenceV1:
    """Capture one terminal systemd invocation without changing service state.

    The output is create-only evidence.  A still-running or unsuccessful unit is
    refused because its terminal continuity facts are not yet available.
    ``command_runner`` and ``observed_utc_ns`` exist solely to make the parser and
    publication behavior deterministic in component tests.
    """

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", soak_id):
        raise ValueError("soak ID must be one safe identifier")
    unit_name = f"leo-soak-{soak_id}.service"
    command = (
        "systemctl",
        "--user",
        "show",
        unit_name,
        "--no-pager",
        "--property=ActiveState,SubState,Result,InvocationID,ExecMainPID,MainPID,"
        "NRestarts,InactiveExitTimestamp,ExecMainStartTimestamp",
    )
    payload = command_runner(command) if command_runner is not None else _run_systemctl(command)
    properties = _parse_systemd_properties(payload)
    if properties["ActiveState"] != "inactive" or properties["SubState"] != "dead":
        raise ValueError("soak systemd unit is not terminal inactive/dead")
    if properties["Result"] != "success":
        raise ValueError("soak systemd unit did not terminate successfully")
    evidence = RuntimeContinuityEvidenceV1(
        soak_id=soak_id,
        unit_name=unit_name,
        invocation_id=properties["InvocationID"],
        exec_main_pid=_systemd_integer(properties, "ExecMainPID", positive=True),
        main_pid_at_observation=_systemd_integer(properties, "MainPID", positive=False),
        n_restarts=_systemd_integer(properties, "NRestarts", positive=False),
        unit_invocation_start_utc_ns=_parse_systemd_utc_ns(properties["InactiveExitTimestamp"]),
        exec_main_start_utc_ns=_parse_systemd_utc_ns(properties["ExecMainStartTimestamp"]),
        observed_utc_ns=time.time_ns() if observed_utc_ns is None else observed_utc_ns,
    )
    _write_immutable_model(output_path, evidence, maximum_bytes=64 * 1024)
    return evidence


def _run_systemctl(command: tuple[str, ...]) -> str:
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return completed.stdout


def _parse_systemd_properties(payload: str) -> dict[str, str]:
    expected = {
        "ActiveState",
        "SubState",
        "Result",
        "InvocationID",
        "ExecMainPID",
        "MainPID",
        "NRestarts",
        "InactiveExitTimestamp",
        "ExecMainStartTimestamp",
    }
    parsed: dict[str, str] = {}
    for line in payload.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in expected or key in parsed:
            raise ValueError("systemd output contains an unexpected or duplicate property")
        parsed[key] = value
    if set(parsed) != expected or any(not parsed[key] for key in expected):
        raise ValueError("systemd output is missing a required property")
    return parsed


def _systemd_integer(properties: dict[str, str], key: str, *, positive: bool) -> int:
    try:
        value = int(properties[key])
    except ValueError as error:
        raise ValueError(f"systemd {key} is not an integer") from error
    if value < (1 if positive else 0):
        raise ValueError(f"systemd {key} is outside its valid range")
    return value


def _parse_systemd_utc_ns(value: str) -> int:
    match = re.fullmatch(
        r"[A-Z][a-z]{2} (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))? UTC",
        value,
    )
    if match is None:
        raise ValueError("systemd timestamp is not an exact C-locale UTC timestamp")
    parsed = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    fraction = (match.group(2) or "").ljust(6, "0")
    return _ns_from_datetime(parsed.replace(microsecond=int(fraction or "0")))


class VerifiedBundleV1(AcceptanceModel):
    session_id: str
    bundle_uri: str
    manifest_sha256: str
    chunk_count: Annotated[int, Field(ge=0)]
    compressed_bytes: Annotated[int, Field(ge=0)]
    uncompressed_bytes: Annotated[int, Field(ge=0)]
    stream_count: Annotated[int, Field(gt=0)]
    stream_ids: tuple[str, ...]
    sample_loss_observable_stream_count: Annotated[int, Field(ge=0)]
    sample_loss_unobservable_stream_count: Annotated[int, Field(ge=0)]
    reported_gap_count: Annotated[int, Field(ge=0)]
    reported_overflow_count: Annotated[int, Field(ge=0)]
    guaranteed_overlap_ns: Annotated[int | None, Field(ge=0)] = None


class ContinuityHonestyV1(AcceptanceModel):
    stream_count: Annotated[int, Field(ge=0)]
    sample_loss_observable_stream_count: Annotated[int, Field(ge=0)]
    sample_loss_unobservable_stream_count: Annotated[int, Field(ge=0)]
    reported_gap_count: Annotated[int, Field(ge=0)]
    reported_overflow_count: Annotated[int, Field(ge=0)]
    minimum_guaranteed_overlap_ns: Annotated[int | None, Field(ge=0)] = None
    device_sample_loss_conclusion: Literal[
        "observable_for_all_streams",
        "not_observable_for_all_streams",
        "partially_observable",
        "no_stream_evidence",
    ]
    zero_reported_host_gaps_proves_zero_device_loss: Literal[False] = False


class ActiveUtcSegmentV1(AcceptanceModel):
    start_active_seconds: Annotated[float, Field(ge=0)]
    end_active_seconds: Annotated[float, Field(ge=0)]
    active_seconds: Annotated[float, Field(gt=0)]
    start_utc_ns: Annotated[int, Field(ge=0)]
    end_utc_ns: Annotated[int, Field(ge=0)]


class FinalActiveWindowV1(AcceptanceModel):
    requested_seconds: Annotated[float, Field(gt=0)]
    represented_seconds: Annotated[float, Field(ge=0)]
    start_active_seconds: Annotated[float, Field(ge=0)]
    end_active_seconds: Annotated[float, Field(ge=0)]
    start_utc_ns: Annotated[int, Field(ge=0)]
    end_utc_ns: Annotated[int, Field(ge=0)]
    active_utc_segments: tuple[ActiveUtcSegmentV1, ...]
    mapping_accepted_within_tolerance: bool
    ambiguous_discontinuity_count: Annotated[int, Field(ge=0)]
    restart_absence_proven_by_timing: Literal[False] = False
    job_arrival_count: Annotated[int, Field(ge=0)]
    successful_job_completion_count: Annotated[int, Field(ge=0)]
    failed_job_completion_count: Annotated[int, Field(ge=0)]
    cancelled_job_completion_count: Annotated[int, Field(ge=0)]
    arrival_rate_jobs_per_active_hour: Annotated[float, Field(ge=0)]
    successful_completion_rate_jobs_per_active_hour: Annotated[float, Field(ge=0)]


class SoakCohortSnapshotV1(AcceptanceModel):
    database_available: bool
    error: str | None = None
    expected_run_count: Annotated[int, Field(ge=0)]
    found_run_count: Annotated[int, Field(ge=0)]
    missing_run_ids: tuple[str, ...] = ()
    mismatched_run_ids: tuple[str, ...] = ()
    non_succeeded_run_ids: tuple[str, ...] = ()
    unsealed_run_ids: tuple[str, ...] = ()
    zero_job_run_ids: tuple[str, ...] = ()
    unexpected_job_count_run_ids: tuple[str, ...] = ()
    wrong_pipeline_release_run_ids: tuple[str, ...] = ()
    wrong_job_inventory_run_ids: tuple[str, ...] = ()
    job_inventory_digests: tuple[tuple[str, str], ...] = ()
    job_count: Annotated[int, Field(ge=0)]
    pending_job_count: Annotated[int, Field(ge=0)]
    leased_job_count: Annotated[int, Field(ge=0)]
    succeeded_job_count: Annotated[int, Field(ge=0)]
    failed_job_count: Annotated[int, Field(ge=0)]
    cancelled_job_count: Annotated[int, Field(ge=0)]
    inherited_pending_or_leased_job_count: Annotated[int, Field(ge=0)]
    final_active_window: FinalActiveWindowV1

    @model_validator(mode="after")
    def _availability_is_coherent(self) -> Self:
        if self.database_available == (self.error is not None):
            raise ValueError("database availability and error must agree")
        return self


class SoakAcceptanceAuditReceiptV1(AcceptanceModel):
    kind: Literal["soak_acceptance_audit"] = "soak_acceptance_audit"
    schema_version: Literal[1] = 1
    soak_id: str
    evidence_directory: str
    bulk_root: str
    definition_sha256: str
    summary_sha256: str
    trial_evidence_sha256: str
    runtime_evidence_sha256: str | None = None
    runtime_continuity: RuntimeContinuityEvidenceV1 | None = None
    thresholds: SoakExternalThresholdsV1
    completed_trial_count: Annotated[int, Field(ge=0)]
    verified_bundles: tuple[VerifiedBundleV1, ...]
    continuity: ContinuityHonestyV1
    sample_derived_duty_cycle: Annotated[float, Field(ge=0)]
    maximum_inter_capture_gap_seconds: Annotated[float | None, Field(ge=0)] = None
    cohort: SoakCohortSnapshotV1
    checks: tuple[SoakAcceptanceCheckV1, ...]
    accepted: bool

    @model_validator(mode="after")
    def _accepted_matches_checks(self) -> Self:
        if self.accepted != bool(self.checks and all(check.passed for check in self.checks)):
            raise ValueError("acceptance result must equal the conjunction of all checks")
        if (self.runtime_continuity is None) != (self.runtime_evidence_sha256 is None):
            raise ValueError(
                "runtime evidence and digest must either both be present or both absent"
            )
        if (
            self.runtime_continuity is not None
            and self.runtime_evidence_sha256 != _runtime_evidence_digest(self.runtime_continuity)
        ):
            raise ValueError("runtime evidence digest does not identify the embedded evidence")
        return self


@dataclass(frozen=True, slots=True)
class CohortJob:
    run_id: str
    session_id: str
    state: str
    stage_key: str
    scope_key: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CohortRun:
    run_id: str
    session_id: str
    state: str
    pipeline_release_id: str
    sealed_at: datetime | None


@dataclass(frozen=True, slots=True)
class CohortReadResult:
    found_runs: tuple[CohortRun, ...]
    jobs: tuple[CohortJob, ...]
    inherited_pending_or_leased: int
    transaction_read_only: bool
    transaction_isolation: str


class SoakCohortReader(Protocol):
    def read(
        self,
        *,
        expected_runs: tuple[tuple[str, str], ...],
        soak_created_utc_ns: int,
    ) -> CohortReadResult: ...


class PostgresSoakCohortReader:
    """One repeatable-read, explicitly read-only PostgreSQL snapshot."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def read(
        self,
        *,
        expected_runs: tuple[tuple[str, str], ...],
        soak_created_utc_ns: int,
    ) -> CohortReadResult:
        engine = create_catalog_engine(self.database_url)
        run_ids = tuple(run_id for run_id, _session_id in expected_runs)
        try:
            with (
                engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection,
                connection.begin(),
            ):
                connection.execute(text("SET TRANSACTION READ ONLY"))
                transaction_settings = connection.execute(
                    text(
                        """
                        SELECT current_setting('transaction_read_only') AS read_only,
                               current_setting('transaction_isolation') AS isolation
                        """
                    )
                ).one()
                transaction_read_only = str(transaction_settings.read_only) == "on"
                transaction_isolation = str(transaction_settings.isolation)
                if not transaction_read_only or transaction_isolation != "repeatable read":
                    raise RuntimeError(
                        "soak cohort snapshot requires a read-only repeatable-read transaction"
                    )
                if run_ids:
                    run_statement = text(
                        """
                        SELECT id, session_id, state, pipeline_release_id, sealed_at
                        FROM analysis_run
                        WHERE id IN :run_ids
                        """
                    ).bindparams(bindparam("run_ids", expanding=True))
                    found_runs = tuple(
                        CohortRun(
                            run_id=str(row.id),
                            session_id=str(row.session_id),
                            state=str(row.state),
                            pipeline_release_id=str(row.pipeline_release_id),
                            sealed_at=(None if row.sealed_at is None else _aware(row.sealed_at)),
                        )
                        for row in connection.execute(run_statement, {"run_ids": run_ids}).all()
                    )
                    job_statement = text(
                        """
                            SELECT pj.run_id, ar.session_id, pj.state,
                                   pj.stage_key, pj.scope_key,
                                   pj.created_at, pj.updated_at
                            FROM processing_job AS pj
                            JOIN analysis_run AS ar ON ar.id = pj.run_id
                            WHERE pj.run_id IN :run_ids
                            ORDER BY pj.id
                            """
                    ).bindparams(bindparam("run_ids", expanding=True))
                    jobs = tuple(
                        CohortJob(
                            run_id=str(row.run_id),
                            session_id=str(row.session_id),
                            state=str(row.state),
                            stage_key=str(row.stage_key),
                            scope_key=str(row.scope_key),
                            created_at=_aware(row.created_at),
                            updated_at=_aware(row.updated_at),
                        )
                        for row in connection.execute(job_statement, {"run_ids": run_ids}).all()
                    )
                else:
                    found_runs = ()
                    jobs = ()
                inherited = int(
                    connection.execute(
                        text(
                            """
                                SELECT count(*)
                                FROM processing_job
                                WHERE created_at < :created_at
                                  AND state IN ('pending', 'leased')
                                """
                        ),
                        {"created_at": _datetime_from_ns(soak_created_utc_ns)},
                    ).scalar_one()
                )
            return CohortReadResult(
                found_runs=found_runs,
                jobs=jobs,
                inherited_pending_or_leased=inherited,
                transaction_read_only=transaction_read_only,
                transaction_isolation=transaction_isolation,
            )
        finally:
            engine.dispose()


class FinalSoakAcceptanceAuditor:
    """Audit existing evidence and catalog state without changing either."""

    def __init__(
        self,
        store: RecordingStore,
        cohort_reader: SoakCohortReader,
        *,
        thresholds: SoakExternalThresholdsV1 | None = None,
        runtime_continuity: RuntimeContinuityEvidenceV1 | None = None,
    ) -> None:
        _reject_qnap_path(store.root, operation="open a recording store")
        self.store = store
        self.cohort_reader = cohort_reader
        self.thresholds = thresholds or SoakExternalThresholdsV1()
        self.runtime_continuity = runtime_continuity
        self.runtime_evidence_sha256 = (
            None if runtime_continuity is None else _runtime_evidence_digest(runtime_continuity)
        )

    @classmethod
    def from_paths(
        cls,
        *,
        bulk_root: Path,
        database_url: str,
        runtime_evidence_path: Path | None = None,
        thresholds: SoakExternalThresholdsV1 | None = None,
    ) -> FinalSoakAcceptanceAuditor:
        _reject_qnap_path(bulk_root, operation="open a recording store")
        _reject_symlinked_path(bulk_root)
        runtime = (
            None
            if runtime_evidence_path is None
            else load_runtime_continuity_evidence(runtime_evidence_path)
        )
        return cls(
            RecordingStore.open_read_only(bulk_root),
            PostgresSoakCohortReader(database_url),
            thresholds=thresholds,
            runtime_continuity=runtime,
        )

    def audit(
        self,
        evidence_directory: Path,
        *,
        receipt_path: Path | None = None,
    ) -> SoakAcceptanceAuditReceiptV1:
        _reject_qnap_path(evidence_directory, operation="read soak evidence")
        _reject_symlinked_path(evidence_directory)
        run_root = evidence_directory.resolve(strict=True)
        if not run_root.is_dir():
            raise ValueError("soak evidence path is not a directory")
        definition_path = run_root / "definition.json"
        summary_path = run_root / "summary.json"
        trials_root = run_root / "trials"
        definition_payload = _bounded_read(definition_path, _MAX_DEFINITION_BYTES)
        summary_payload = _bounded_read(summary_path, _MAX_SUMMARY_BYTES)
        definition = SoakDefinitionV1.model_validate_json(definition_payload)
        summary = SoakSummaryV1.model_validate_json(summary_payload)
        trials, trial_payloads, contiguous = _read_trials(trials_root, definition.soak_id)

        checks: list[SoakAcceptanceCheckV1] = []
        _check(
            checks,
            "identity",
            summary.soak_id == definition.soak_id,
            f"definition={definition.soak_id} summary={summary.soak_id}",
        )
        _check(
            checks,
            "terminal_summary",
            summary.status == "complete"
            and summary.complete
            and summary.passed
            and summary.completion_reason == "duration",
            (
                f"status={summary.status} complete={summary.complete} passed={summary.passed} "
                f"reason={summary.completion_reason}"
            ),
        )
        production_duration = (
            definition.configuration.duration_seconds == self.thresholds.required_active_seconds
            and definition.configuration.maximum_trials is None
            and summary.active_elapsed_seconds >= self.thresholds.required_active_seconds
        )
        _check(
            checks,
            "production_duration",
            production_duration,
            (
                f"configured={definition.configuration.duration_seconds:.6f}s "
                f"active={summary.active_elapsed_seconds:.6f}s "
                f"trial_limit={definition.configuration.maximum_trials!r}"
            ),
        )
        runtime = self.runtime_continuity
        runtime_ok = (
            runtime is not None
            and self.runtime_evidence_sha256 is not None
            and runtime.soak_id == definition.soak_id
            and runtime.unit_name == f"leo-soak-{definition.soak_id}.service"
            and runtime.n_restarts == 0
            and runtime.main_pid_at_observation in (0, runtime.exec_main_pid)
            and runtime.unit_invocation_start_utc_ns <= runtime.exec_main_start_utc_ns
            and runtime.exec_main_start_utc_ns <= definition.created_utc_ns
            and runtime.observed_utc_ns >= summary.updated_utc_ns
        )
        _check(
            checks,
            "runtime_invocation_continuity",
            runtime_ok,
            (
                "missing required immutable systemd runtime evidence"
                if runtime is None
                else (
                    f"unit={runtime.unit_name} invocation={runtime.invocation_id} "
                    f"exec_main_pid={runtime.exec_main_pid} "
                    f"main_pid_at_observation={runtime.main_pid_at_observation} "
                    f"n_restarts={runtime.n_restarts}"
                )
            ),
        )
        _check(
            checks,
            "trial_contiguity",
            contiguous and len(trials) == summary.completed_trial_count,
            f"files={len(trials)} expected_summary_count={summary.completed_trial_count}",
        )
        timeline_ok = _active_timeline_is_consistent(summary, trials)
        _check(
            checks,
            "active_timeline",
            timeline_ok,
            "trial active time and UTC bounds are monotonic and bounded by the summary",
        )

        expected_summary = _summarize(
            definition,
            list(trials),
            trials_root,
            updated_utc_ns=summary.updated_utc_ns,
            active_elapsed_seconds=summary.active_elapsed_seconds,
            status=summary.status,
            completion_reason=summary.completion_reason,
        )
        summary_fields = summary.model_dump()
        expected_fields = expected_summary.model_dump()
        _check(
            checks,
            "summary_recalculation",
            summary_fields == expected_fields,
            "persisted aggregate matches authoritative immutable trial evidence",
        )

        verified, bundle_errors = self._verify_bundles(definition, trials)
        _check(
            checks,
            "recording_bundle_digests",
            not bundle_errors and len(verified) == len(trials),
            "; ".join(bundle_errors) if bundle_errors else f"verified={len(verified)}",
        )
        post_commit_ok = bool(trials) and all(
            trial.state is CaptureState.COMMITTED
            and trial.post_commit.succeeded
            and trial.post_commit.target_session_id == trial.session_id
            for trial in trials
        )
        _check(
            checks,
            "post_commit_integration",
            post_commit_ok,
            f"successful={sum(trial.post_commit.succeeded for trial in trials)}/{len(trials)}",
        )

        maximum_gap = max(
            (
                trial.inter_capture_gap_seconds
                for trial in trials
                if trial.inter_capture_gap_seconds is not None
            ),
            default=None,
        )
        _check(
            checks,
            "external_minimum_duty_cycle",
            summary.duty_cycle >= self.thresholds.minimum_sample_derived_duty_cycle,
            (
                f"sample-derived={summary.duty_cycle:.9f} "
                f"minimum={self.thresholds.minimum_sample_derived_duty_cycle:.9f}"
            ),
        )
        _check(
            checks,
            "external_maximum_inter_capture_gap",
            maximum_gap is None or maximum_gap <= self.thresholds.maximum_inter_capture_gap_seconds,
            (
                f"observed={maximum_gap!r}s "
                f"maximum={self.thresholds.maximum_inter_capture_gap_seconds:.9f}s"
            ),
        )

        expected_runs = tuple(
            sorted(
                {
                    (run_id, trial.session_id)
                    for trial in trials
                    for run_id in trial.post_commit.queued_run_ids
                }
            )
        )
        stream_ids_by_session = {item.session_id: item.stream_ids for item in verified}
        expected_job_inventories = {
            run_id: frozenset(
                (stage_key, scope_key)
                for stage_key in self.thresholds.expected_stage_keys
                for scope_key in stream_ids_by_session.get(session_id, ())
            )
            for run_id, session_id in expected_runs
        }
        sessions_with_runs = {session_id for _run_id, session_id in expected_runs}
        expected_sessions = {trial.session_id for trial in trials}
        unique_run_ids = {run_id for run_id, _session_id in expected_runs}
        _check(
            checks,
            "recorded_run_inventory",
            bool(expected_sessions)
            and sessions_with_runs == expected_sessions
            and len(unique_run_ids) == len(expected_runs),
            (
                f"sessions={len(expected_sessions)} "
                f"sessions_with_recorded_runs={len(sessions_with_runs)} "
                f"run_ids={len(unique_run_ids)} run_ownership_pairs={len(expected_runs)}"
            ),
        )
        window = _active_window(
            summary,
            trials,
            self.thresholds.final_active_window_seconds,
            maximum_delta_seconds=self.thresholds.maximum_active_wall_delta_seconds,
        )
        cohort = self._cohort_snapshot(
            definition,
            expected_runs,
            expected_job_inventories,
            window,
        )
        _check(
            checks,
            "database_snapshot",
            cohort.database_available,
            cohort.error or "repeatable-read transaction was read-only",
        )
        _check(
            checks,
            "recorded_run_ownership",
            bool(expected_runs) and not cohort.missing_run_ids and not cohort.mismatched_run_ids,
            (
                f"expected={cohort.expected_run_count} found={cohort.found_run_count} "
                f"missing={len(cohort.missing_run_ids)} mismatched={len(cohort.mismatched_run_ids)}"
            ),
        )
        _check(
            checks,
            "terminal_succeeded_runs",
            cohort.database_available
            and not cohort.non_succeeded_run_ids
            and not cohort.unsealed_run_ids
            and not cohort.zero_job_run_ids
            and not cohort.unexpected_job_count_run_ids
            and not cohort.wrong_pipeline_release_run_ids
            and not cohort.wrong_job_inventory_run_ids,
            (
                f"non_succeeded={len(cohort.non_succeeded_run_ids)} "
                f"unsealed={len(cohort.unsealed_run_ids)} "
                f"zero_job={len(cohort.zero_job_run_ids)} "
                f"wrong_job_count={len(cohort.unexpected_job_count_run_ids)} "
                f"wrong_release={len(cohort.wrong_pipeline_release_run_ids)} "
                f"wrong_inventory={len(cohort.wrong_job_inventory_run_ids)} "
                f"expected_jobs_per_run={self.thresholds.expected_jobs_per_run}"
            ),
        )
        _check(
            checks,
            "inherited_queue_drained",
            cohort.database_available and cohort.inherited_pending_or_leased_job_count == 0,
            f"inherited_pending_or_leased={cohort.inherited_pending_or_leased_job_count}",
        )
        outstanding = cohort.pending_job_count + cohort.leased_job_count
        _check(
            checks,
            "soak_origin_outstanding_below_limit",
            cohort.database_available
            and outstanding < self.thresholds.maximum_soak_origin_pending_or_leased,
            (
                f"pending_plus_leased={outstanding} "
                f"strict_limit={self.thresholds.maximum_soak_origin_pending_or_leased}"
            ),
        )
        _check(
            checks,
            "soak_origin_queue_drained",
            cohort.database_available and outstanding == 0,
            f"pending_plus_leased={outstanding}",
        )
        final_rate_ok = (
            cohort.database_available
            and window.mapping_accepted_within_tolerance
            and window.represented_seconds >= self.thresholds.final_active_window_seconds
            and cohort.final_active_window.job_arrival_count > 0
            and cohort.final_active_window.successful_job_completion_count
            >= cohort.final_active_window.job_arrival_count
        )
        _check(
            checks,
            "final_six_active_hour_service_rate",
            final_rate_ok,
            (
                f"window={cohort.final_active_window.represented_seconds:.6f}s "
                "mapping_accepted_within_tolerance="
                f"{cohort.final_active_window.mapping_accepted_within_tolerance} "
                f"ambiguous={cohort.final_active_window.ambiguous_discontinuity_count} "
                f"arrivals={cohort.final_active_window.job_arrival_count} "
                f"successful_completions="
                f"{cohort.final_active_window.successful_job_completion_count}"
            ),
        )
        _check(
            checks,
            "no_terminal_processing_failures",
            cohort.database_available
            and cohort.failed_job_count == 0
            and cohort.cancelled_job_count == 0,
            f"failed={cohort.failed_job_count} cancelled={cohort.cancelled_job_count}",
        )

        continuity = _continuity(verified)
        receipt = SoakAcceptanceAuditReceiptV1(
            soak_id=definition.soak_id,
            evidence_directory=str(run_root),
            bulk_root=str(self.store.root),
            definition_sha256=_sha256(definition_payload),
            summary_sha256=_sha256(summary_payload),
            trial_evidence_sha256=_sequence_digest(trial_payloads),
            runtime_evidence_sha256=self.runtime_evidence_sha256,
            runtime_continuity=runtime,
            thresholds=self.thresholds,
            completed_trial_count=len(trials),
            verified_bundles=tuple(verified),
            continuity=continuity,
            sample_derived_duty_cycle=summary.duty_cycle,
            maximum_inter_capture_gap_seconds=maximum_gap,
            cohort=cohort,
            checks=tuple(checks),
            accepted=bool(checks and all(check.passed for check in checks)),
        )
        if receipt_path is not None:
            _write_immutable_receipt(receipt_path, receipt)
        return receipt

    def _verify_bundles(
        self,
        definition: SoakDefinitionV1,
        trials: Sequence[SoakTrialEvidenceV1],
    ) -> tuple[list[VerifiedBundleV1], list[str]]:
        verified: list[VerifiedBundleV1] = []
        errors: list[str] = []
        for trial in trials:
            try:
                if trial.state is not CaptureState.COMMITTED:
                    raise ValueError(f"trial state is {trial.state.value}, not committed")
                if trial.bundle_uri is None or trial.manifest_sha256 is None:
                    raise ValueError("committed trial has no bundle reference")
                if trial.digest_valid is not True or trial.verification_error is not None:
                    raise ValueError("trial did not originally record successful verification")
                bundle = self.store.inspect_uri(trial.bundle_uri)
                if bundle.session_id != trial.session_id:
                    raise ValueError("bundle session does not match trial")
                if bundle.manifest_sha256 != trial.manifest_sha256:
                    raise ValueError("manifest digest does not match trial")
                manifest = bundle.manifest
                if isinstance(manifest, RecordingManifestV4):
                    raise ValueError("legacy soak acceptance does not accept mixed-rate manifests")
                if manifest.state is not trial.state:
                    raise ValueError("manifest capture state does not match trial")
                plan = manifest.capture_plan
                if (
                    plan.plan_digest != definition.capture_plan_digest
                    or plan.profile_revision.revision_digest != definition.profile_revision_digest
                    or plan.profile_revision.profile.name != definition.profile_name
                    or plan.radio_ids != definition.radio_ids
                ):
                    raise ValueError("recording plan does not match the immutable soak definition")
                requested = sum(stream.requested_sample_count for stream in manifest.streams)
                captured = sum(stream.captured_sample_count for stream in manifest.streams)
                gaps = sum(stream.continuity.gap_count for stream in manifest.streams)
                overflows = sum(stream.continuity.overflow_count for stream in manifest.streams)
                sync = manifest.synchronization
                evidence = (
                    requested,
                    captured,
                    gaps,
                    overflows,
                    sync.estimated_start_skew_ns,
                    sync.start_skew_uncertainty_ns,
                    sync.estimated_overlap_ns,
                    sync.guaranteed_overlap_ns,
                    sync.overlap_fraction,
                    manifest.tags,
                )
                recorded = (
                    trial.requested_sample_count,
                    trial.captured_sample_count,
                    trial.gap_count,
                    trial.overflow_count,
                    trial.estimated_start_skew_ns,
                    trial.start_skew_uncertainty_ns,
                    trial.estimated_overlap_ns,
                    trial.guaranteed_overlap_ns,
                    trial.overlap_fraction,
                    trial.recording_tags,
                )
                if evidence != recorded:
                    raise ValueError("trial metrics do not match the immutable manifest")
                sample_rate_hz = manifest.capture_plan.profile_revision.profile.sample_rate_hz
                recorded_span = max(
                    (stream.captured_sample_count / sample_rate_hz for stream in manifest.streams),
                    default=0,
                )
                capture_starts = tuple(
                    stream.timing.first_sample.estimate_utc_ns
                    for stream in manifest.streams
                    if stream.timing is not None
                )
                capture_finishes = tuple(
                    stream.timing.last_sample.estimate_utc_ns
                    for stream in manifest.streams
                    if stream.timing is not None
                )
                if recorded_span != trial.recorded_span_seconds:
                    raise ValueError("sample-derived recording span does not match trial")
                if (
                    min(capture_starts) if capture_starts else manifest.created_utc_ns
                ) != trial.capture_started_utc_ns or (
                    max(capture_finishes) if capture_finishes else manifest.finalized_utc_ns
                ) != trial.capture_finished_utc_ns:
                    raise ValueError("manifest capture bounds do not match trial")
                report = self.store.verify(bundle)
                observable = sum(
                    stream.continuity.sample_loss_observable for stream in manifest.streams
                )
                verified.append(
                    VerifiedBundleV1(
                        session_id=trial.session_id,
                        bundle_uri=trial.bundle_uri,
                        manifest_sha256=bundle.manifest_sha256,
                        chunk_count=report.chunk_count,
                        compressed_bytes=report.compressed_bytes,
                        uncompressed_bytes=report.uncompressed_bytes,
                        stream_count=len(manifest.streams),
                        stream_ids=tuple(stream.stream_id for stream in manifest.streams),
                        sample_loss_observable_stream_count=observable,
                        sample_loss_unobservable_stream_count=len(manifest.streams) - observable,
                        reported_gap_count=gaps,
                        reported_overflow_count=overflows,
                        guaranteed_overlap_ns=sync.guaranteed_overlap_ns,
                    )
                )
            except Exception as error:
                errors.append(f"{trial.session_id}: {type(error).__name__}: {error}")
        return verified, errors

    def _cohort_snapshot(
        self,
        definition: SoakDefinitionV1,
        expected_runs: tuple[tuple[str, str], ...],
        expected_job_inventories: dict[str, frozenset[tuple[str, str]]],
        window: FinalActiveWindowV1,
    ) -> SoakCohortSnapshotV1:
        empty = FinalActiveWindowV1(
            **window.model_dump(
                exclude={
                    "job_arrival_count",
                    "successful_job_completion_count",
                    "failed_job_completion_count",
                    "cancelled_job_completion_count",
                    "arrival_rate_jobs_per_active_hour",
                    "successful_completion_rate_jobs_per_active_hour",
                }
            ),
            job_arrival_count=0,
            successful_job_completion_count=0,
            failed_job_completion_count=0,
            cancelled_job_completion_count=0,
            arrival_rate_jobs_per_active_hour=0,
            successful_completion_rate_jobs_per_active_hour=0,
        )
        try:
            result = self.cohort_reader.read(
                expected_runs=expected_runs,
                soak_created_utc_ns=definition.created_utc_ns,
            )
        except Exception as error:
            return SoakCohortSnapshotV1(
                database_available=False,
                error=f"{type(error).__name__}: {error}",
                expected_run_count=len(expected_runs),
                found_run_count=0,
                missing_run_ids=tuple(run_id for run_id, _ in expected_runs),
                job_count=0,
                pending_job_count=0,
                leased_job_count=0,
                succeeded_job_count=0,
                failed_job_count=0,
                cancelled_job_count=0,
                inherited_pending_or_leased_job_count=0,
                final_active_window=empty,
            )
        expected = dict(expected_runs)
        found = {run.run_id: run.session_id for run in result.found_runs}
        missing = tuple(sorted(set(expected) - set(found)))
        mismatched = tuple(
            sorted(
                run_id for run_id in set(expected) & set(found) if expected[run_id] != found[run_id]
            )
        )
        non_succeeded = tuple(
            sorted(run.run_id for run in result.found_runs if run.state != "succeeded")
        )
        unsealed = tuple(sorted(run.run_id for run in result.found_runs if run.sealed_at is None))
        job_counts = Counter(job.run_id for job in result.jobs)
        zero_job = tuple(
            sorted(run.run_id for run in result.found_runs if job_counts[run.run_id] == 0)
        )
        wrong_job_count = tuple(
            sorted(
                run.run_id
                for run in result.found_runs
                if job_counts[run.run_id] != self.thresholds.expected_jobs_per_run
            )
        )
        wrong_release = tuple(
            sorted(
                run.run_id
                for run in result.found_runs
                if run.pipeline_release_id != self.thresholds.expected_pipeline_release_id
            )
        )
        identities_by_run: dict[str, set[tuple[str, str]]] = {
            run.run_id: set() for run in result.found_runs
        }
        for job in result.jobs:
            identities_by_run.setdefault(job.run_id, set()).add((job.stage_key, job.scope_key))
        wrong_inventory = tuple(
            sorted(
                run_id
                for run_id, expected_inventory in expected_job_inventories.items()
                if identities_by_run.get(run_id, set()) != expected_inventory
            )
        )
        inventory_digests = tuple(
            (run_id, _job_inventory_digest(identities))
            for run_id, identities in sorted(identities_by_run.items())
        )
        states = Counter(job.state for job in result.jobs)
        arrivals = sum(_timestamp_in_active_window(job.created_at, window) for job in result.jobs)
        successful = sum(
            job.state == "succeeded" and _timestamp_in_active_window(job.updated_at, window)
            for job in result.jobs
        )
        failed = sum(
            job.state == "failed" and _timestamp_in_active_window(job.updated_at, window)
            for job in result.jobs
        )
        cancelled = sum(
            job.state == "cancelled" and _timestamp_in_active_window(job.updated_at, window)
            for job in result.jobs
        )
        hours = window.represented_seconds / 3600
        measured_window = empty.model_copy(
            update={
                "job_arrival_count": arrivals,
                "successful_job_completion_count": successful,
                "failed_job_completion_count": failed,
                "cancelled_job_completion_count": cancelled,
                "arrival_rate_jobs_per_active_hour": arrivals / hours if hours else 0,
                "successful_completion_rate_jobs_per_active_hour": (
                    successful / hours if hours else 0
                ),
            }
        )
        return SoakCohortSnapshotV1(
            database_available=True,
            expected_run_count=len(expected_runs),
            found_run_count=len(found),
            missing_run_ids=missing,
            mismatched_run_ids=mismatched,
            non_succeeded_run_ids=non_succeeded,
            unsealed_run_ids=unsealed,
            zero_job_run_ids=zero_job,
            unexpected_job_count_run_ids=wrong_job_count,
            wrong_pipeline_release_run_ids=wrong_release,
            wrong_job_inventory_run_ids=wrong_inventory,
            job_inventory_digests=inventory_digests,
            job_count=len(result.jobs),
            pending_job_count=states["pending"],
            leased_job_count=states["leased"],
            succeeded_job_count=states["succeeded"],
            failed_job_count=states["failed"],
            cancelled_job_count=states["cancelled"],
            inherited_pending_or_leased_job_count=result.inherited_pending_or_leased,
            final_active_window=measured_window,
        )


def resolve_soak_evidence(value: str, *, bulk_root: Path) -> Path:
    """Resolve either an explicit directory or one safe soak ID."""

    _reject_qnap_path(bulk_root, operation="resolve soak evidence")
    _reject_symlinked_path(bulk_root)
    supplied = Path(value)
    _reject_qnap_path(supplied, operation="read soak evidence")
    _reject_symlinked_path(supplied)
    if supplied.exists():
        return supplied.resolve(strict=True)
    if (
        "/" in value
        or "\\" in value
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", value)
    ):
        raise ValueError("soak evidence must be an existing directory or one safe soak ID")
    candidate = bulk_root / "qualification" / "soak" / value
    _reject_symlinked_path(candidate)
    return candidate.resolve(strict=True)


def load_runtime_continuity_evidence(
    path: Path,
) -> RuntimeContinuityEvidenceV1:
    _reject_qnap_path(path, operation="read runtime continuity evidence")
    _reject_symlinked_path(path)
    payload = _bounded_read(path, 64 * 1024)
    return RuntimeContinuityEvidenceV1.model_validate_json(payload)


def _read_trials(
    root: Path, soak_id: str
) -> tuple[tuple[SoakTrialEvidenceV1, ...], tuple[bytes, ...], bool]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("soak trials path is not a regular directory")
    entries = tuple(sorted(root.iterdir()))
    paths = tuple(path for path in entries if _TRIAL_NAME.fullmatch(path.name))
    trials: list[SoakTrialEvidenceV1] = []
    payloads: list[bytes] = []
    contiguous = len(paths) == len(entries)
    for expected, path in enumerate(paths):
        match = _TRIAL_NAME.fullmatch(path.name)
        if path.is_symlink() or not path.is_file() or match is None:
            contiguous = False
        payload = _bounded_read(path, _MAX_TRIAL_BYTES)
        trial = SoakTrialEvidenceV1.model_validate_json(payload)
        expected_session = f"{soak_id}-trial-{expected + 1:08d}"
        if (
            match is None
            or int(match.group(1)) != expected
            or trial.trial_index != expected
            or trial.soak_id != soak_id
            or trial.session_id != expected_session
        ):
            contiguous = False
        trials.append(trial)
        payloads.append(payload)
    return tuple(trials), tuple(payloads), contiguous


def _active_window(
    summary: SoakSummaryV1,
    trials: Sequence[SoakTrialEvidenceV1],
    requested_seconds: float,
    *,
    maximum_delta_seconds: float,
) -> FinalActiveWindowV1:
    requested_representation = min(summary.active_elapsed_seconds, requested_seconds)
    start_active = summary.active_elapsed_seconds - requested_representation
    end_active = summary.active_elapsed_seconds
    end_utc = summary.updated_utc_ns
    start_utc = max(0, end_utc - round(requested_representation * 1_000_000_000))
    ambiguous = _ambiguous_discontinuities(
        summary,
        trials,
        window_start_active=start_active,
        window_end_active=end_active,
        maximum_delta_seconds=maximum_delta_seconds,
    )
    mapping_accepted = ambiguous == 0 and requested_representation > 0
    clipped = (
        (
            ActiveUtcSegmentV1(
                start_active_seconds=start_active,
                end_active_seconds=end_active,
                active_seconds=requested_representation,
                start_utc_ns=start_utc,
                end_utc_ns=end_utc,
            ),
        )
        if mapping_accepted
        else ()
    )
    represented = requested_representation if mapping_accepted else 0
    return FinalActiveWindowV1(
        requested_seconds=requested_seconds,
        represented_seconds=represented,
        start_active_seconds=start_active,
        end_active_seconds=end_active,
        start_utc_ns=start_utc,
        end_utc_ns=end_utc,
        active_utc_segments=tuple(clipped),
        mapping_accepted_within_tolerance=mapping_accepted,
        ambiguous_discontinuity_count=ambiguous,
        job_arrival_count=0,
        successful_job_completion_count=0,
        failed_job_completion_count=0,
        cancelled_job_completion_count=0,
        arrival_rate_jobs_per_active_hour=0,
        successful_completion_rate_jobs_per_active_hour=0,
    )


def _active_timeline_is_consistent(
    summary: SoakSummaryV1,
    trials: Sequence[SoakTrialEvidenceV1],
) -> bool:
    previous_active = 0.0
    previous_finish_utc = 0
    for trial in trials:
        capture_start_active = trial.active_elapsed_seconds - trial.acquisition_elapsed_seconds
        if (
            capture_start_active < previous_active
            or trial.active_elapsed_seconds < capture_start_active
            or trial.capture_started_utc_ns < previous_finish_utc
            or trial.capture_finished_utc_ns < trial.capture_started_utc_ns
        ):
            return False
        previous_active = trial.active_elapsed_seconds
        previous_finish_utc = trial.capture_finished_utc_ns
    return (
        previous_active <= summary.active_elapsed_seconds
        and previous_finish_utc <= summary.updated_utc_ns
    )


def _ambiguous_discontinuities(
    summary: SoakSummaryV1,
    trials: Sequence[SoakTrialEvidenceV1],
    *,
    window_start_active: float,
    window_end_active: float,
    maximum_delta_seconds: float,
) -> int:
    """Count wall/active discontinuities that make the final window ambiguous."""

    ambiguous = 0
    previous: SoakTrialEvidenceV1 | None = None
    for trial in trials:
        if previous is not None:
            active_delta = trial.active_elapsed_seconds - previous.active_elapsed_seconds
            wall_delta = (
                trial.capture_finished_utc_ns - previous.capture_finished_utc_ns
            ) / 1_000_000_000
            overlaps = (
                trial.active_elapsed_seconds >= window_start_active
                and previous.active_elapsed_seconds <= window_end_active
            )
            if overlaps and abs(wall_delta - active_delta) > maximum_delta_seconds:
                ambiguous += 1
        previous = trial
    if previous is not None:
        active_gap = summary.active_elapsed_seconds - previous.active_elapsed_seconds
        wall_gap = (summary.updated_utc_ns - previous.capture_finished_utc_ns) / 1_000_000_000
        overlaps = (
            summary.active_elapsed_seconds >= window_start_active
            and previous.active_elapsed_seconds <= window_end_active
        )
        if overlaps and abs(wall_gap - active_gap) > maximum_delta_seconds:
            ambiguous += 1
    return ambiguous


def _timestamp_in_active_window(value: datetime, window: FinalActiveWindowV1) -> bool:
    timestamp_ns = _ns_from_datetime(value)
    return any(
        segment.start_utc_ns <= timestamp_ns <= segment.end_utc_ns
        for segment in window.active_utc_segments
    )


def _continuity(verified: Sequence[VerifiedBundleV1]) -> ContinuityHonestyV1:
    stream_count = sum(item.stream_count for item in verified)
    observable = sum(item.sample_loss_observable_stream_count for item in verified)
    unobservable = sum(item.sample_loss_unobservable_stream_count for item in verified)
    guaranteed = tuple(
        item.guaranteed_overlap_ns for item in verified if item.guaranteed_overlap_ns is not None
    )
    conclusion: Literal[
        "observable_for_all_streams",
        "not_observable_for_all_streams",
        "partially_observable",
        "no_stream_evidence",
    ]
    if not stream_count:
        conclusion = "no_stream_evidence"
    elif observable == stream_count:
        conclusion = "observable_for_all_streams"
    elif unobservable == stream_count:
        conclusion = "not_observable_for_all_streams"
    else:
        conclusion = "partially_observable"
    return ContinuityHonestyV1(
        stream_count=stream_count,
        sample_loss_observable_stream_count=observable,
        sample_loss_unobservable_stream_count=unobservable,
        reported_gap_count=sum(item.reported_gap_count for item in verified),
        reported_overflow_count=sum(item.reported_overflow_count for item in verified),
        minimum_guaranteed_overlap_ns=min(guaranteed) if guaranteed else None,
        device_sample_loss_conclusion=conclusion,
    )


def _bounded_read(path: Path, maximum_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"qualification evidence is not a regular file: {path}")
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise ValueError(f"qualification evidence size is invalid: {path}")
    return path.read_bytes()


def _check(checks: list[SoakAcceptanceCheckV1], name: str, passed: bool, detail: str) -> None:
    checks.append(SoakAcceptanceCheckV1(name=name, passed=passed, detail=detail))


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _runtime_evidence_digest(evidence: RuntimeContinuityEvidenceV1) -> str:
    return _sha256(evidence.model_dump_json().encode("utf-8"))


def _sequence_digest(payloads: Sequence[bytes]) -> str:
    digest = hashlib.sha256()
    for payload in payloads:
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return f"sha256:{digest.hexdigest()}"


def _job_inventory_digest(identities: set[tuple[str, str]] | frozenset[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for stage_key, scope_key in sorted(identities):
        for value in (stage_key, scope_key):
            payload = value.encode("utf-8")
            digest.update(len(payload).to_bytes(4, "big"))
            digest.update(payload)
    return f"sha256:{digest.hexdigest()}"


def _datetime_from_ns(value: int) -> datetime:
    seconds, remainder = divmod(value, 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC).replace(microsecond=remainder // 1_000)


def _ns_from_datetime(value: datetime) -> int:
    aware = _aware(value)
    delta = aware - datetime(1970, 1, 1, tzinfo=UTC)
    return (
        delta.days * 86_400_000_000_000 + delta.seconds * 1_000_000_000 + delta.microseconds * 1_000
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _write_immutable_receipt(path: Path, receipt: SoakAcceptanceAuditReceiptV1) -> None:
    _write_immutable_model(path, receipt, maximum_bytes=_MAX_RECEIPT_BYTES)


def _write_immutable_model(
    path: Path,
    value: BaseModel,
    *,
    maximum_bytes: int,
) -> None:
    _reject_qnap_output(path)
    _reject_symlinked_path(path.parent)
    if not path.name or path.name in {".", ".."}:
        raise ValueError("receipt path must name one file")
    parent = path.parent.resolve(strict=True)
    _reject_qnap_output(parent)
    if not parent.is_dir():
        raise ValueError("receipt parent is not a directory")
    destination = parent / path.name
    try:
        os.lstat(destination)
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"immutable audit receipt already exists: {destination}")
    payload = value.model_dump_json(indent=2).encode("utf-8") + b"\n"
    if len(payload) > maximum_bytes:
        raise ValueError("immutable evidence exceeded its bounded file size")
    temporary = parent / f".{path.name}.{os.getpid()}-{uuid4().hex}.partial"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fchmod(stream.fileno(), 0o440)
            os.fsync(stream.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        _fsync_directory(parent)
    finally:
        temporary.unlink(missing_ok=True)
        _fsync_directory(parent)


def _reject_qnap_output(path: Path) -> None:
    _reject_qnap_path(path, operation="write audit receipts")


def _reject_qnap_path(path: Path, *, operation: str) -> None:
    absolute = Path(os.path.abspath(path))
    qnap = Path("/mnt/qnap01")
    if absolute == qnap or qnap in absolute.parents:
        raise ValueError(f"final soak auditor must never {operation} beneath /mnt/qnap01")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reject_symlinked_path(path: Path) -> None:
    """Reject indirection before resolving an auditor path.

    The lexical QNAP guard runs first, so this walker never touches QNAP for a
    directly forbidden input. Refusing all parent symlinks also closes indirect
    escapes without following a link to discover its target.
    """

    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"final soak auditor path is symlinked: {current}")
