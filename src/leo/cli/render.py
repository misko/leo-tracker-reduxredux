"""Human and machine renderers over the same typed result object."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import cast

from rich.console import Console
from rich.table import Table

from leo.cli.models import (
    AcquisitionStatusDataV1,
    CalibrationPredeclareDataV1,
    CalibrationPromoteDataV1,
    CalibrationQueueDataV1,
    CalibrationShowDataV1,
    CancelRunDataV1,
    CaptureControlDataV1,
    CaptureDataV1,
    CommandResultV1,
    DoctorDataV1,
    HoldDataV1,
    ImportDataV1,
    JobsDataV1,
    ProcessHelpDataV1,
    ProfileListDataV1,
    ProfileShowDataV1,
    ProfileValidationDataV1,
    RadioListDataV1,
    ReconcileDataV1,
    ReprocessDataV1,
    RetentionDataV1,
    RunDataV1,
    SessionDetailDataV1,
    SessionPathsDataV1,
    SessionSearchDataV1,
    WorkerDataV1,
)
from leo.qualification import (
    AcquisitionQualificationReceiptV1,
    CaptureModeCampaignAcceptanceReceiptV2,
    RuntimeContinuityEvidenceV1,
    SoakAcceptanceAuditReceiptV1,
    SoakSummaryV1,
    WriterBenchmarkReceiptV1,
)
from leo.scanner import (
    ScannerBurstReportV1,
    ScannerBurstReportV2,
    ScannerReport,
    ScannerReportLike,
    ScannerReportV2,
)


def _emit_scanner_burst(
    console: Console,
    reports: Sequence[ScannerReportLike],
) -> None:
    table = Table("Scan", "Active edges", "Inconclusive", "Capture", "Analysis")
    for index, report in enumerate(reports, start=1):
        table.add_row(
            str(index),
            str(len(report.active_edges)),
            str(sum(item.decision.value == "inconclusive" for item in report.results)),
            f"{report.capture_elapsed_ms:.1f} ms",
            f"{report.analysis_elapsed_ms:.1f} ms",
        )
    console.print(table)


def emit_result(result: CommandResultV1, *, json_output: bool) -> None:
    if json_output:
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return
    console = Console(file=sys.stdout, force_terminal=False, color_system=None, highlight=False)
    payload = result.payload
    console.print(result.message, style="green" if result.ok else "red")
    if isinstance(payload, (ScannerBurstReportV1, ScannerBurstReportV2)):
        _emit_scanner_burst(console, cast(Sequence[ScannerReportLike], payload.reports))
    elif isinstance(payload, (ScannerReport, ScannerReportV2)):
        table = Table("Channel", "Edge", "IF MHz", "Capture", "First hit", "Margin", "Result")
        for scan_result in payload.results:
            hit = scan_result.first_detection
            table.add_row(
                f"CH{scan_result.target.channel}",
                scan_result.target.edge.value,
                f"{scan_result.target.if_center_hz / 1e6:.4f}",
                (
                    f"{scan_result.listen_ms:.1f} ms"
                    if scan_result.listen_ms is not None
                    else "failed"
                ),
                f"{hit.probe_start_ms} ms RX{hit.receiver_id}" if hit is not None else "—",
                (f"{scan_result.best_margin:.4f}" if scan_result.best_margin is not None else "—"),
                scan_result.decision.value.upper(),
            )
        console.print(table)
        console.print(
            f"capture={payload.capture_elapsed_ms:.1f} ms "
            f"analysis={payload.analysis_elapsed_ms:.1f} ms "
            "candidate-only; no payload decoded"
        )
    elif isinstance(payload, RadioListDataV1):
        table = Table("Radio", "Backend", "Serial", "RX", "State", "Detail")
        for radio in payload.radios:
            table.add_row(
                radio.radio_id,
                radio.backend,
                radio.serial,
                str(radio.receiver_count),
                radio.state,
                radio.detail or "",
            )
        console.print(table)
    elif isinstance(payload, DoctorDataV1):
        table = Table("Check", "State", "Detail")
        for check in payload.checks:
            table.add_row(check.name, check.state.value, check.detail)
        console.print(table)
    elif isinstance(payload, ProfileListDataV1):
        table = Table("Profile", "Sample rate", "Dwell/samples", "RX", "Tags")
        for profile in payload.profiles:
            dwell = profile.duration_seconds or str(profile.sample_count)
            table.add_row(
                profile.name,
                str(profile.sample_rate_hz),
                dwell,
                ",".join(str(receiver) for receiver in profile.receivers),
                ",".join(profile.tags),
            )
        console.print(table)
    elif isinstance(payload, ProfileShowDataV1):
        console.print(f"path: {payload.path}")
        console.print_json(data=payload.revision.model_dump(mode="json"))
    elif isinstance(payload, ProfileValidationDataV1):
        table = Table("Path", "Name", "Valid", "Revision / error")
        for item in payload.items:
            table.add_row(
                item.path,
                item.name or "",
                "yes" if item.valid else "no",
                item.revision_digest or item.error or "",
            )
        console.print(table)
    elif isinstance(payload, CaptureDataV1):
        _render_capture(console, payload)
    elif isinstance(payload, CaptureControlDataV1):
        console.print(
            f"desired={payload.state.desired_state.value} "
            f"observed={payload.state.observed_state.value} "
            f"generation={payload.state.generation}"
        )
        console.print(f"radios={','.join(payload.radio_ids)} reason={payload.state.reason}")
    elif isinstance(payload, RunDataV1):
        console.print(
            f"captures={payload.capture_count} committed={payload.committed_count} "
            f"degraded={payload.degraded_count} failed={payload.failed_count} "
            f"stop={payload.stopped_reason}"
        )
        if payload.last_capture is not None:
            _render_capture(console, payload.last_capture)
    elif isinstance(payload, AcquisitionStatusDataV1):
        console.print(f"backend: {payload.backend}")
        console.print(f"bulk root: {payload.bulk_root}")
        console.print(f"configured radios: {payload.configured_radio_count}")
        console.print(f"valid profiles: {payload.valid_profile_count}")
        console.print(f"committed recordings: {payload.committed_recording_count}")
        console.print(f"incomplete spools: {payload.incomplete_spool_count}")
        console.print(f"reconcile issues: {payload.reconcile_issue_count}")
        if payload.catalog_registration_warning is not None:
            console.print(f"catalog warning: {payload.catalog_registration_warning}")
        if payload.last_capture is not None:
            console.print("last capture:")
            _render_capture(console, payload.last_capture)
    elif isinstance(payload, AcquisitionQualificationReceiptV1):
        aggregate = payload.aggregate
        console.print(f"qualification: {payload.qualification_id}")
        console.print(f"complete: {payload.complete} passed: {payload.passed}")
        console.print(
            f"trials={aggregate.completed_trial_count}/{aggregate.requested_trial_count} "
            f"committed={aggregate.committed_count} degraded={aggregate.degraded_count} "
            f"failed={aggregate.failed_count}"
        )
        console.print(
            f"success={aggregate.successful_trial_fraction:.3f} "
            f"overlap-pass={aggregate.overlap_passing_trial_fraction:.3f} "
            f"digests-valid={aggregate.all_digests_valid}"
        )
        if aggregate.mean_overlap_fraction is not None:
            console.print(
                f"overlap mean={aggregate.mean_overlap_fraction:.6f} "
                f"minimum={aggregate.minimum_overlap_fraction:.6f}"
            )
    elif isinstance(payload, CaptureModeCampaignAcceptanceReceiptV2):
        console.print(f"capture-mode campaign: {payload.acceptance_id}")
        console.print(
            f"accepted={payload.accepted} trials={len(payload.trial_receipts)} "
            f"sessions={sum(len(trial.checks) for trial in payload.trial_receipts)}"
        )
        table = Table("Trial", "Independent A", "Independent B", "Synchronized")
        for index, trial in enumerate(payload.trial_receipts, start=1):
            table.add_row(
                str(index),
                "PASS" if trial.checks[0].passed else "FAIL",
                "PASS" if trial.checks[1].passed else "FAIL",
                "PASS" if trial.checks[2].passed else "FAIL",
            )
        console.print(table)
        console.print(
            "scope=capture-only; Standard processing and detection evidence remains required"
        )
    elif isinstance(payload, WriterBenchmarkReceiptV1):
        console.print(f"benchmark: {payload.benchmark_id}")
        console.print(f"passed: {payload.passed} digest-valid: {payload.digest_valid}")
        console.print(
            f"throughput: {payload.throughput_mb_s:.2f} MB/s "
            f"target: {payload.configuration.minimum_throughput_mb_s:.2f} MB/s"
        )
        console.print(
            f"wrote {payload.uncompressed_bytes} raw bytes in {payload.elapsed_seconds:.3f}s"
        )
    elif isinstance(payload, SoakSummaryV1):
        console.print(f"soak: {payload.soak_id}")
        console.print(
            f"status={payload.status} passed={payload.passed} "
            f"trials={payload.completed_trial_count} duty={payload.duty_cycle:.3f}"
        )
        console.print(
            f"committed={payload.committed_count} degraded={payload.degraded_count} "
            f"failed={payload.failed_count} gaps={payload.total_gap_count} "
            f"overflows={payload.total_overflow_count}"
        )
        for violation in payload.policy_violations:
            console.print(f"policy violation: {violation}")
    elif isinstance(payload, SoakAcceptanceAuditReceiptV1):
        console.print(f"soak: {payload.soak_id}")
        console.print(
            f"accepted={payload.accepted} trials={payload.completed_trial_count} "
            f"verified={len(payload.verified_bundles)}"
        )
        console.print(
            f"duty={payload.sample_derived_duty_cycle:.6f} "
            f"maximum-gap={payload.maximum_inter_capture_gap_seconds!r}s"
        )
        window = payload.cohort.final_active_window
        console.print(
            f"final-window arrivals={window.job_arrival_count} "
            f"successful-completions={window.successful_job_completion_count} "
            f"pending={payload.cohort.pending_job_count} leased={payload.cohort.leased_job_count}"
        )
        console.print("continuity: " + payload.continuity.device_sample_loss_conclusion)
        for audit_check in payload.checks:
            console.print(
                f"{'PASS' if audit_check.passed else 'FAIL'} "
                f"{audit_check.name}: {audit_check.detail}"
            )
    elif isinstance(payload, RuntimeContinuityEvidenceV1):
        console.print(f"soak: {payload.soak_id}")
        console.print(
            f"unit={payload.unit_name} invocation={payload.invocation_id} "
            f"restarts={payload.n_restarts}"
        )
    elif isinstance(payload, ProcessHelpDataV1):
        console.print("commands: " + ", ".join(payload.available_commands))
    elif isinstance(payload, SessionSearchDataV1):
        table = Table("Session", "Created", "Source", "State", "Held", "Tags", "Current run")
        for session_item in payload.sessions:
            table.add_row(
                session_item.session_id,
                session_item.created_at.isoformat(),
                session_item.source_type,
                session_item.state,
                "yes" if session_item.held else "no",
                ",".join(session_item.tags),
                session_item.current_run_id or "",
            )
        console.print(table)
    elif isinstance(payload, SessionDetailDataV1):
        console.print(f"session: {payload.session_id}")
        console.print(f"source/state: {payload.source_type}/{payload.state}")
        console.print(f"created: {payload.created_at.isoformat()}")
        console.print(f"held: {payload.held} ({payload.hold_reason or ''})")
        console.print(f"tags: {', '.join(payload.tags)}")
        console.print(f"bundle: {payload.bundle_uri or ''}")
        if payload.analysis is not None:
            console.print(
                f"current analysis: {payload.analysis.run_id} "
                f"release={payload.analysis.pipeline_release_id} state={payload.analysis.state}"
            )
            console.print(
                f"jobs={len(payload.analysis.jobs)} products={len(payload.analysis.products)}"
            )
    elif isinstance(payload, SessionPathsDataV1):
        table = Table("Role", "Logical URI", "Physical path", "Exists", "Digest")
        for path_item in payload.paths:
            table.add_row(
                path_item.role,
                path_item.logical_uri,
                path_item.physical_path or "",
                "yes" if path_item.exists else "no",
                path_item.digest or "",
            )
        console.print(table)
    elif isinstance(payload, ReprocessDataV1):
        console.print(f"session: {payload.session_id}")
        console.print(f"state: {payload.state}")
        console.print(f"planned run: {payload.run_id}")
        console.print(f"previous current: {payload.previous_current_run_id or 'none'}")
        console.print(f"pipeline release: {payload.pipeline_release_id}")
        console.print(f"scopes: {', '.join(payload.queued_scope_keys)}")
    elif isinstance(payload, CancelRunDataV1):
        console.print(
            f"run={payload.run_id} state={payload.state} changed={payload.changed} "
            f"cancelled-jobs={payload.cancelled_job_count} "
            f"succeeded-jobs={payload.succeeded_job_count} products={payload.product_count}"
        )
        console.print(f"reason: {payload.reason}")
    elif isinstance(payload, JobsDataV1):
        console.print(
            f"queued={payload.queued} running={payload.running} failed={payload.failed} "
            f"oldest-queued={payload.oldest_queued_seconds}"
        )
        if payload.ready_to_finalize_run_ids:
            console.print("ready to finalize: " + ", ".join(payload.ready_to_finalize_run_ids))
    elif isinstance(payload, HoldDataV1):
        console.print(
            f"session={payload.session_id} held={payload.held} changed={payload.changed} "
            f"reason={payload.reason or ''}"
        )
    elif isinstance(payload, ImportDataV1):
        console.print(f"corpus: {payload.corpus_id}")
        console.print(f"local root: {payload.local_root}")
        table = Table("Fixture", "Session", "Status", "Bundle", "Directory")
        for fixture_item in payload.fixtures:
            table.add_row(
                fixture_item.fixture_id,
                fixture_item.session_id,
                fixture_item.status,
                fixture_item.bundle_uri,
                fixture_item.directory,
            )
        console.print(table)
    elif isinstance(payload, RetentionDataV1):
        console.print(
            f"usage={payload.used_fraction:.3%} warning={payload.warning} "
            f"admission={payload.admission_allowed_after_plan} blocked={payload.blocked}"
        )
        console.print(
            f"selected={len(payload.selected_ids)} bytes={payload.selected_bytes} "
            f"committed={len(payload.committed_ids)} dry-run={payload.dry_run}"
        )
        for failure in payload.failures:
            console.print(f"failure: {failure}")
    elif isinstance(payload, WorkerDataV1):
        console.print(
            f"worker={payload.worker_id} claimed={payload.claimed_count} "
            f"succeeded={payload.succeeded_count} failed={payload.failed_count}"
        )
        console.print(
            f"finalized={payload.finalized_count} rejected={payload.rejected_count} "
            f"errors={payload.error_count} stop={payload.stopped_reason}"
        )
        omitted = (
            payload.execution_evidence_omitted_count
            + payload.finalized_id_evidence_omitted_count
            + payload.rejected_id_evidence_omitted_count
            + payload.error_evidence_omitted_count
        )
        if omitted:
            console.print(
                f"recent evidence capped at {payload.evidence_limit}; "
                f"{omitted} item(s) omitted across evidence categories"
            )
        for error in payload.errors:
            console.print(f"error: {error}")
    elif isinstance(payload, ReconcileDataV1):
        console.print(
            f"purges restored={len(payload.restored_purges)} "
            f"discarded={len(payload.discarded_purges)}"
        )
        console.print(
            f"sessions registered={len(payload.registered_sessions)} "
            f"existing={len(payload.existing_sessions)} runs queued={len(payload.queued_run_ids)}"
        )
        for issue in payload.issues:
            console.print(f"issue: {issue}")
        for incompatibility in payload.historical_incompatibilities:
            console.print(f"historical incompatibility: {incompatibility}")
    elif isinstance(payload, CalibrationPredeclareDataV1):
        console.print(f"plan: {payload.result.plan.plan_id}")
        console.print(f"uri: {payload.result.plan_ref.logical_uri}")
        console.print(f"digest: {payload.result.plan_ref.digest}")
        console.print("sessions: " + ", ".join(payload.result.plan.scheduled_session_ids))
    elif isinstance(payload, CalibrationQueueDataV1):
        console.print(f"stage={payload.result.stage_key} policy={payload.result.promotion_policy}")
        for session_id, run_id in payload.result.session_run_ids:
            console.print(f"{session_id}: {run_id}")
    elif isinstance(payload, (CalibrationPromoteDataV1, CalibrationShowDataV1)):
        console.print(f"promotion: {payload.result.publication.promotion_id}")
        console.print(f"bundle: {payload.result.publication.bundle_uri}")
        console.print(f"manifest: {payload.result.publication.manifest_digest}")
        console.print(f"calibration set: {payload.result.calibration_set.calibration_set_id}")
        for calibration in payload.result.calibration_set.calibrations:
            console.print(
                f"{calibration.calibration_id}: center={calibration.center_hz}Hz "
                f"bounds=[{calibration.uncertainty_lower_hz},"
                f"{calibration.uncertainty_upper_hz}]Hz"
            )


def _render_capture(console: Console, capture: CaptureDataV1) -> None:
    console.print(f"session: {capture.session_id}")
    console.print(f"state: {capture.state.value}")
    console.print(f"profile: {capture.profile_name}")
    console.print(f"radios: {', '.join(capture.radio_ids)}")
    if capture.bundle_uri is not None:
        console.print(f"bundle: {capture.bundle_uri}")
    for error in capture.errors:
        console.print(f"error: {error}")
