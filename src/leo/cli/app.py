"""Typer command tree for local acquisition operations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Annotated, Literal, cast

import typer

from leo.cli.backend import CliBackendError
from leo.cli.composition import BackendFactory, default_backend_factory
from leo.cli.models import (
    AcquisitionStatusDataV1,
    CancelRunDataV1,
    CaptureDataV1,
    CliPayload,
    CommandResultV1,
    DoctorDataV1,
    ExitCode,
    HoldDataV1,
    ImportDataV1,
    JobsDataV1,
    ProcessHelpDataV1,
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
from leo.cli.render import emit_result
from leo.cli.runner import ContinuousAcquisitionRunner, cancellation_signals
from leo.contracts.states import CaptureState
from leo.qualification import (
    AcquisitionAcceptancePolicyV1,
    AcquisitionQualificationReceiptV1,
    CaptureModeCampaignAcceptanceReceiptV2,
    SoakAcceptanceAuditReceiptV1,
    SoakConfigV1,
    SoakSummaryV1,
    WriterBenchmarkConfigV1,
    WriterBenchmarkReceiptV1,
)

PayloadOperation = Callable[[], CliPayload]


def create_cli(backend_factory: BackendFactory = default_backend_factory) -> typer.Typer:
    app = typer.Typer(name="leo", no_args_is_help=True, pretty_exceptions_enable=False)
    acquire = typer.Typer(name="acquire", no_args_is_help=True)
    profiles = typer.Typer(name="profiles", no_args_is_help=True)
    process = typer.Typer(name="process", invoke_without_command=True)
    calibration = typer.Typer(name="calibration", no_args_is_help=True)
    app.add_typer(acquire, name="acquire", help="Acquire and inspect Pluto+ IQ recordings.")
    app.add_typer(process, name="process", help="Processing commands registered separately.")
    process.add_typer(
        calibration,
        name="calibration",
        help="Predeclare, queue, promote and inspect WP11 frequency calibration.",
    )
    acquire.add_typer(profiles, name="profiles", help="Inspect revisioned capture profiles.")

    @acquire.command("radios")
    def radios(
        probe: Annotated[
            bool,
            typer.Option("--probe/--no-probe", help="Open and serial-attest configured radios."),
        ] = False,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "acquire.radios",
            lambda: backend_factory().radios(probe=probe),
            json_output=json_output,
        )

    @acquire.command("doctor")
    def doctor(
        probe_radios: Annotated[
            bool,
            typer.Option("--probe-radios/--no-probe-radios"),
        ] = False,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "acquire.doctor",
            lambda: backend_factory().doctor(probe_radios=probe_radios),
            json_output=json_output,
        )

    @profiles.command("list")
    def profiles_list(
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "acquire.profiles.list",
            lambda: backend_factory().profiles_list(),
            json_output=json_output,
        )

    @profiles.command("show")
    def profile_show(
        name: Annotated[str, typer.Argument(help="Exact profile name.")],
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "acquire.profiles.show",
            lambda: backend_factory().profile_show(name),
            json_output=json_output,
        )

    @profiles.command("validate")
    def profiles_validate(
        target: Annotated[
            str | None,
            typer.Argument(help="Optional profile name or file stem; omit to validate all."),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "acquire.profiles.validate",
            lambda: backend_factory().profiles_validate(target),
            json_output=json_output,
        )

    @acquire.command("once")
    def once(
        profile_name: Annotated[str, typer.Option("--profile", help="Capture profile name.")],
        radio_ids: Annotated[
            list[str] | None,
            typer.Option("--radio", help="Configured radio ID; repeat for a pair."),
        ] = None,
        session_id: Annotated[
            str | None,
            typer.Option("--session-id", help="Explicit safe session ID."),
        ] = None,
        tags: Annotated[
            list[str] | None,
            typer.Option("--tag", help="Additional manifest tag; repeat as needed."),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        cancel = Event()
        _execute(
            "acquire.once",
            lambda: backend_factory().capture_once(
                profile_name,
                radio_ids=tuple(radio_ids or ()),
                session_id=session_id,
                extra_tags=tuple(tags or ()),
                cancel=cancel,
            ),
            json_output=json_output,
        )

    @acquire.command("run")
    def run(
        profile_name: Annotated[str, typer.Option("--profile", help="Capture profile name.")],
        radio_ids: Annotated[
            list[str] | None,
            typer.Option("--radio", help="Configured radio ID; repeat for a pair."),
        ] = None,
        tags: Annotated[
            list[str] | None,
            typer.Option("--tag", help="Additional manifest tag; repeat as needed."),
        ] = None,
        interval_seconds: Annotated[
            float,
            typer.Option("--interval-seconds", min=0, help="Idle time between captures."),
        ] = 0.0,
        maximum_captures: Annotated[
            int | None,
            typer.Option("--max-captures", min=1, help="Stop after N captures."),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        cancel = Event()

        def run_foreground() -> RunDataV1:
            runner = ContinuousAcquisitionRunner(backend_factory())
            return runner.run(
                profile_name,
                radio_ids=tuple(radio_ids or ()),
                extra_tags=tuple(tags or ()),
                interval_seconds=interval_seconds,
                maximum_captures=maximum_captures,
                cancel=cancel,
            )

        _execute(
            "acquire.run",
            run_foreground,
            json_output=json_output,
        )

    @acquire.command("status")
    def status(
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "acquire.status",
            lambda: backend_factory().status(),
            json_output=json_output,
        )

    @acquire.command("qualify")
    def qualify(
        profile_name: Annotated[str, typer.Option("--profile", help="Capture profile name.")],
        radio_ids: Annotated[
            list[str] | None,
            typer.Option("--radio", help="Configured radio ID; repeat for a pair."),
        ] = None,
        trial_count: Annotated[
            int,
            typer.Option("--trials", min=1, help="Bounded number of capture trials."),
        ] = 20,
        qualification_id: Annotated[
            str | None,
            typer.Option("--qualification-id", help="Stable ID used to resume trials."),
        ] = None,
        receipt_path: Annotated[
            Path | None,
            typer.Option("--receipt", help="Qualification JSON receipt path."),
        ] = None,
        resume: Annotated[
            bool,
            typer.Option("--resume/--no-resume", help="Resume an existing matching receipt."),
        ] = True,
        minimum_successful_fraction: Annotated[
            float,
            typer.Option("--minimum-successful-fraction", min=0, max=1),
        ] = 0.95,
        minimum_overlap: Annotated[
            float,
            typer.Option("--minimum-overlap", min=0, max=1),
        ] = 0.99,
        minimum_overlap_trial_fraction: Annotated[
            float,
            typer.Option("--minimum-overlap-trial-fraction", min=0, max=1),
        ] = 0.95,
        maximum_false_complete: Annotated[
            int,
            typer.Option("--maximum-false-complete", min=0),
        ] = 0,
        maximum_false_coherent: Annotated[
            int,
            typer.Option("--maximum-false-coherent", min=0),
        ] = 0,
        require_valid_digests: Annotated[
            bool,
            typer.Option("--require-valid-digests/--allow-invalid-digests"),
        ] = True,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        cancel = Event()
        policy = AcquisitionAcceptancePolicyV1(
            minimum_successful_trial_fraction=minimum_successful_fraction,
            minimum_estimated_overlap_fraction=minimum_overlap,
            minimum_overlap_passing_trial_fraction=minimum_overlap_trial_fraction,
            maximum_false_complete_count=maximum_false_complete,
            maximum_false_coherent_count=maximum_false_coherent,
            require_all_digests_valid=require_valid_digests,
        )

        def run_qualification() -> AcquisitionQualificationReceiptV1:
            with cancellation_signals(cancel):
                return backend_factory().qualify(
                    profile_name,
                    radio_ids=tuple(radio_ids or ()),
                    qualification_id=qualification_id,
                    trial_count=trial_count,
                    receipt_path=receipt_path,
                    policy=policy,
                    resume=resume,
                    cancel=cancel,
                )

        _execute(
            "acquire.qualify",
            run_qualification,
            json_output=json_output,
        )

    @acquire.command("audit-capture-modes")
    def audit_capture_modes(
        profile_name: Annotated[str, typer.Option("--profile", help="Exact capture profile.")],
        radio_a: Annotated[str, typer.Option("--radio-a", help="First configured radio ID.")],
        radio_b: Annotated[str, typer.Option("--radio-b", help="Second configured radio ID.")],
        acceptance_id: Annotated[
            str,
            typer.Option("--acceptance-id", help="Stable campaign receipt ID."),
        ],
        independent_a_sessions: Annotated[
            list[str],
            typer.Option(
                "--independent-a-session",
                help="Radio A independent session ID; repeat exactly 10 times.",
            ),
        ],
        independent_b_sessions: Annotated[
            list[str],
            typer.Option(
                "--independent-b-session",
                help="Radio B independent session ID; repeat exactly 10 times.",
            ),
        ],
        synchronized_sessions: Annotated[
            list[str],
            typer.Option(
                "--synchronized-session",
                help="Two-radio synchronized session ID; repeat exactly 10 times.",
            ),
        ],
        receipt_path: Annotated[
            Path | None,
            typer.Option(
                "--receipt",
                help="Optional immutable local receipt; omit for a read-only dry audit.",
            ),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        def run_audit() -> CaptureModeCampaignAcceptanceReceiptV2:
            return backend_factory().accept_capture_modes(
                profile_name,
                radio_ids=(radio_a, radio_b),
                acceptance_id=acceptance_id,
                independent_radio_a_session_ids=tuple(independent_a_sessions),
                independent_radio_b_session_ids=tuple(independent_b_sessions),
                synchronized_pair_session_ids=tuple(synchronized_sessions),
                receipt_path=receipt_path,
            )

        _execute(
            "acquire.audit-capture-modes",
            run_audit,
            json_output=json_output,
        )

    @acquire.command("benchmark-writer")
    def benchmark_writer(
        duration_seconds: Annotated[
            float,
            typer.Option("--duration-seconds", min=0.001, max=3600),
        ] = 1.0,
        minimum_throughput_mb_s: Annotated[
            float,
            typer.Option("--minimum-mb-s", min=0.001),
        ] = 60.0,
        block_bytes: Annotated[
            int,
            typer.Option("--block-bytes", min=16_384, max=128 * 1024 * 1024),
        ] = 128 * 1024 * 1024,
        receiver_count: Annotated[
            int,
            typer.Option("--receivers", min=1, max=2),
        ] = 2,
        zstd_level: Annotated[
            int,
            typer.Option("--zstd-level", min=-10, max=22),
        ] = 3,
        random_seed: Annotated[int, typer.Option("--seed", min=0)] = 20260819,
        benchmark_id: Annotated[
            str | None,
            typer.Option("--benchmark-id", help="Stable ID used to resume."),
        ] = None,
        receipt_path: Annotated[
            Path | None,
            typer.Option("--receipt", help="Benchmark JSON receipt path."),
        ] = None,
        resume: Annotated[bool, typer.Option("--resume/--no-resume")] = True,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        cancel = Event()
        configuration = WriterBenchmarkConfigV1(
            duration_seconds=duration_seconds,
            minimum_throughput_mb_s=minimum_throughput_mb_s,
            block_uncompressed_bytes=block_bytes,
            receiver_count=cast(Literal[1, 2], receiver_count),
            zstd_level=zstd_level,
            random_seed=random_seed,
        )

        def run_benchmark() -> WriterBenchmarkReceiptV1:
            with cancellation_signals(cancel):
                return backend_factory().benchmark_writer(
                    benchmark_id=benchmark_id,
                    receipt_path=receipt_path,
                    configuration=configuration,
                    resume=resume,
                    cancel=cancel,
                )

        _execute(
            "acquire.benchmark-writer",
            run_benchmark,
            json_output=json_output,
        )

    @acquire.command("soak")
    def soak(
        profile_name: Annotated[str, typer.Option("--profile")],
        radio_ids: Annotated[
            list[str] | None,
            typer.Option("--radio", help="Configured radio ID; repeat for a pair."),
        ] = None,
        duration_seconds: Annotated[
            float,
            typer.Option("--duration-seconds", min=0.001, max=7 * 24 * 60 * 60),
        ] = 86_400,
        cadence_seconds: Annotated[
            float,
            typer.Option("--cadence-seconds", min=0, max=24 * 60 * 60),
        ] = 0,
        soak_id: Annotated[
            str | None,
            typer.Option("--soak-id", help="Stable ID used to resume."),
        ] = None,
        output_root: Annotated[
            Path | None,
            typer.Option("--output-dir", help="Root for soak evidence."),
        ] = None,
        resume: Annotated[bool, typer.Option("--resume/--no-resume")] = True,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        cancel = Event()
        configuration = SoakConfigV1(
            duration_seconds=duration_seconds,
            cadence_seconds=cadence_seconds,
        )

        def run_soak() -> SoakSummaryV1:
            with cancellation_signals(cancel):
                return backend_factory().soak(
                    profile_name,
                    radio_ids=tuple(radio_ids or ()),
                    soak_id=soak_id,
                    output_root=output_root,
                    configuration=configuration,
                    resume=resume,
                    cancel=cancel,
                )

        _execute("acquire.soak", run_soak, json_output=json_output)

    @acquire.command("audit-soak")
    def audit_soak(
        evidence: Annotated[
            str,
            typer.Argument(help="Existing soak evidence directory or soak ID."),
        ],
        database_url: Annotated[
            str | None,
            typer.Option(
                "--database-url",
                help="PostgreSQL catalog URL; defaults to LEO_DATABASE_URL.",
            ),
        ] = None,
        receipt_path: Annotated[
            Path | None,
            typer.Option(
                "--receipt",
                help="Explicit new path for an immutable 0440 JSON receipt.",
            ),
        ] = None,
        runtime_evidence_path: Annotated[
            Path | None,
            typer.Option(
                "--runtime-evidence",
                help="Immutable systemd invocation/NRestarts evidence JSON.",
            ),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        def run_audit() -> SoakAcceptanceAuditReceiptV1:
            return backend_factory().audit_soak(
                evidence,
                database_url=database_url,
                receipt_path=receipt_path,
                runtime_evidence_path=runtime_evidence_path,
            )

        _execute("acquire.audit-soak", run_audit, json_output=json_output)

    @process.callback()
    def process_root(
        context: typer.Context,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        if context.invoked_subcommand is not None:
            return
        result = CommandResultV1(
            command="process",
            ok=True,
            exit_code=ExitCode.OK,
            message="No processing command was selected.",
            payload=ProcessHelpDataV1(),
        )
        emit_result(result, json_output=json_output)

    @process.command("search")
    def process_search(
        source_type: Annotated[str | None, typer.Option("--source-type")] = None,
        state: Annotated[str | None, typer.Option("--state")] = None,
        tag: Annotated[str | None, typer.Option("--tag")] = None,
        held: Annotated[
            bool | None,
            typer.Option("--held/--unheld", help="Filter by active retention hold."),
        ] = None,
        test_only: Annotated[
            bool,
            typer.Option("--test", help="Require TEST source type and tag."),
        ] = False,
        created_after: Annotated[
            datetime | None,
            typer.Option("--after", help="ISO-8601 inclusive creation lower bound."),
        ] = None,
        created_before: Annotated[
            datetime | None,
            typer.Option("--before", help="ISO-8601 exclusive creation upper bound."),
        ] = None,
        limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 100,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        if test_only and source_type not in {None, "test"}:
            raise typer.BadParameter("--test conflicts with a non-test --source-type")
        if test_only and tag not in {None, "TEST"}:
            raise typer.BadParameter("--test conflicts with a non-TEST --tag")
        _execute(
            "process.search",
            lambda: backend_factory().search_sessions(
                source_type="test" if test_only else source_type,
                state=state,
                tag="TEST" if test_only else tag,
                held=held,
                created_after=created_after,
                created_before=created_before,
                limit=limit,
            ),
            json_output=json_output,
        )

    @process.command("show")
    def process_show(
        session_id: Annotated[str, typer.Argument(help="Capture session ID.")],
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "process.show",
            lambda: backend_factory().show_session(session_id),
            json_output=json_output,
        )

    @process.command("paths")
    def process_paths(
        session_id: Annotated[str, typer.Argument(help="Capture session ID.")],
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "process.paths",
            lambda: backend_factory().session_paths(session_id),
            json_output=json_output,
        )

    @process.command("reprocess")
    def process_reprocess(
        session_id: Annotated[str, typer.Argument(help="Capture session ID.")],
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "process.reprocess",
            lambda: backend_factory().reprocess(session_id),
            json_output=json_output,
        )

    @process.command("cancel-run")
    def process_cancel_run(
        run_id: Annotated[str, typer.Argument(help="Analysis run ID.")],
        reason: Annotated[
            str,
            typer.Option("--reason", help="Auditable reason for cancellation."),
        ],
        confirmed: Annotated[
            bool,
            typer.Option("--yes", help="Confirm cancellation of queued jobs."),
        ] = False,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        def cancel_operation() -> CancelRunDataV1:
            if not confirmed:
                raise CliBackendError(
                    "cancel-run requires --yes confirmation",
                    ExitCode.CONFIRMATION_REQUIRED,
                )
            return backend_factory().cancel_run(run_id, reason=reason)

        _execute(
            "process.cancel-run",
            cancel_operation,
            json_output=json_output,
        )

    @process.command("jobs")
    def process_jobs(
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute("process.jobs", lambda: backend_factory().jobs(), json_output=json_output)

    @process.command("pin")
    def process_pin(
        session_id: Annotated[str, typer.Argument(help="Capture session ID.")],
        reason: Annotated[str, typer.Option("--reason", help="Why this data must be kept.")],
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "process.pin",
            lambda: backend_factory().pin(session_id, reason=reason),
            json_output=json_output,
        )

    @process.command("unpin")
    def process_unpin(
        session_id: Annotated[str, typer.Argument(help="Capture session ID.")],
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "process.unpin",
            lambda: backend_factory().unpin(session_id),
            json_output=json_output,
        )

    @process.command("import-qnap")
    def process_import_qnap(
        manifest: Annotated[Path, typer.Argument(help="Read-only corpus manifest.")],
        copy: Annotated[
            bool,
            typer.Option("--copy", help="Explicitly copy and verify into local storage."),
        ] = False,
        tags: Annotated[
            list[str] | None,
            typer.Option("--tag", help="Required TEST tag; repeat only if needed."),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "process.import-qnap",
            lambda: backend_factory().import_qnap(
                manifest,
                copy=copy,
                tags=tuple(tags or ()),
            ),
            json_output=json_output,
        )

    @process.command("retention-status")
    def process_retention_status(
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "process.retention-status",
            lambda: backend_factory().retention_status(),
            json_output=json_output,
        )

    @process.command("retention-run")
    def process_retention_run(
        dry_run: Annotated[
            bool,
            typer.Option("--dry-run/--execute", help="Plan only, or perform selected purges."),
        ] = True,
        yes: Annotated[
            bool,
            typer.Option("--yes", help="Confirm a manually requested destructive pass."),
        ] = False,
        automatic: Annotated[
            bool,
            typer.Option(
                "--automatic",
                help="Use only from the configured unattended retention timer.",
                hidden=True,
            ),
        ] = False,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        def retention_operation() -> RetentionDataV1:
            if not dry_run and not (yes or automatic):
                raise CliBackendError(
                    "destructive retention requires --yes (or the systemd-only --automatic mode)",
                    ExitCode.CONFIRMATION_REQUIRED,
                )
            return backend_factory().retention_run(dry_run=dry_run)

        _execute(
            "process.retention-run",
            retention_operation,
            json_output=json_output,
        )

    @process.command("reconcile")
    def process_reconcile(
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        _execute(
            "process.reconcile",
            lambda: backend_factory().reconcile(),
            json_output=json_output,
        )

    @process.command("worker")
    def process_worker(
        worker_id: Annotated[str, typer.Option("--worker-id", help="Stable worker identity.")],
        poll_seconds: Annotated[
            float,
            typer.Option("--poll-seconds", min=0.01, help="Idle queue poll interval."),
        ] = 1.0,
        once: Annotated[
            bool,
            typer.Option("--once", help="Claim at most one job and return."),
        ] = False,
        maximum_jobs: Annotated[
            int | None,
            typer.Option("--max-jobs", min=1, help="Bound work for qualification/tests."),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Emit typed JSON.")] = False,
    ) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        cancel = Event()

        def run_worker() -> WorkerDataV1:
            with cancellation_signals(cancel):
                return backend_factory().worker(
                    worker_id=worker_id,
                    poll_seconds=poll_seconds,
                    maximum_jobs=maximum_jobs,
                    once=once,
                    cancel=cancel,
                )

        _execute("process.worker", run_worker, json_output=json_output)

    @calibration.command("predeclare")
    def calibration_predeclare(
        plan_id: Annotated[str, typer.Option("--plan-id")],
        radio_id: Annotated[str, typer.Option("--radio-id")],
        session_ids: Annotated[
            list[str],
            typer.Option("--session", help="Preassigned capture session ID; repeat."),
        ],
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        _execute(
            "process.calibration.predeclare",
            lambda: backend_factory().calibration_predeclare(
                plan_id=plan_id,
                radio_id=radio_id,
                scheduled_session_ids=tuple(session_ids),
            ),
            json_output=json_output,
        )

    @calibration.command("queue")
    def calibration_queue(
        plan_uri: Annotated[str, typer.Option("--plan-uri")],
        plan_digest: Annotated[str, typer.Option("--plan-digest")],
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        _execute(
            "process.calibration.queue",
            lambda: backend_factory().calibration_queue(
                plan_uri=plan_uri,
                plan_digest=plan_digest,
            ),
            json_output=json_output,
        )

    @calibration.command("promote")
    def calibration_promote(
        plan_uri: Annotated[str, typer.Option("--plan-uri")],
        plan_digest: Annotated[str, typer.Option("--plan-digest")],
        promotion_id: Annotated[str, typer.Option("--promotion-id")],
        calibration_id: Annotated[str, typer.Option("--calibration-id")],
        calibration_set_id: Annotated[str, typer.Option("--calibration-set-id")],
        valid_until_utc_ns: Annotated[int | None, typer.Option("--valid-until-utc-ns")] = None,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        _execute(
            "process.calibration.promote",
            lambda: backend_factory().calibration_promote(
                plan_uri=plan_uri,
                plan_digest=plan_digest,
                promotion_id=promotion_id,
                calibration_id=calibration_id,
                calibration_set_id=calibration_set_id,
                valid_until_utc_ns=valid_until_utc_ns,
            ),
            json_output=json_output,
        )

    @calibration.command("show")
    def calibration_show(
        promotion_id: Annotated[str, typer.Argument()],
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        _execute(
            "process.calibration.show",
            lambda: backend_factory().calibration_show(promotion_id),
            json_output=json_output,
        )

    return app


def _execute(command: str, operation: PayloadOperation, *, json_output: bool) -> None:
    try:
        payload = operation()
        exit_code = _exit_code(payload)
        message = _message(payload)
    except CliBackendError as error:
        payload = None
        exit_code = error.exit_code
        message = str(error)
    except (OSError, ValueError) as error:
        payload = None
        exit_code = ExitCode.INVALID_CONFIGURATION
        message = f"{type(error).__name__}: {error}"
    except Exception as error:
        payload = None
        exit_code = ExitCode.UNEXPECTED
        message = f"{type(error).__name__}: {error}"
    result = CommandResultV1(
        command=command,
        ok=exit_code is ExitCode.OK,
        exit_code=exit_code,
        message=message,
        payload=payload,
    )
    emit_result(result, json_output=json_output)
    if exit_code is not ExitCode.OK:
        raise typer.Exit(code=int(exit_code))


def _exit_code(payload: CliPayload) -> ExitCode:
    if isinstance(payload, RadioListDataV1) and any(
        radio.state == "error" for radio in payload.radios
    ):
        return ExitCode.UNHEALTHY
    if isinstance(payload, DoctorDataV1) and not payload.healthy:
        return ExitCode.UNHEALTHY
    if isinstance(payload, AcquisitionStatusDataV1) and payload.reconcile_issue_count:
        return ExitCode.UNHEALTHY
    if isinstance(payload, AcquisitionStatusDataV1) and payload.catalog_registration_warning:
        return ExitCode.UNHEALTHY
    if isinstance(payload, SoakSummaryV1):
        if payload.status == "complete" and payload.passed:
            return ExitCode.OK
        if payload.status == "interrupted":
            return ExitCode.INTERRUPTED
        return ExitCode.UNHEALTHY
    if isinstance(payload, SoakAcceptanceAuditReceiptV1):
        return ExitCode.OK if payload.accepted else ExitCode.UNHEALTHY
    if isinstance(payload, CaptureModeCampaignAcceptanceReceiptV2):
        return ExitCode.OK if payload.accepted else ExitCode.UNHEALTHY
    if isinstance(payload, ProfileValidationDataV1) and not payload.valid:
        return ExitCode.INVALID_CONFIGURATION
    if isinstance(payload, CaptureDataV1):
        if payload.state is CaptureState.COMMITTED:
            return ExitCode.OK
        if payload.state is CaptureState.DEGRADED:
            return ExitCode.CAPTURE_DEGRADED
        if payload.available_free_bytes < payload.required_free_bytes:
            return ExitCode.ADMISSION_REJECTED
        return ExitCode.CAPTURE_FAILED
    if isinstance(payload, RunDataV1):
        if payload.stopped_reason == "cancelled":
            return ExitCode.INTERRUPTED
        if payload.failed_count:
            return ExitCode.CAPTURE_FAILED
        if payload.degraded_count:
            return ExitCode.CAPTURE_DEGRADED
    if isinstance(payload, AcquisitionQualificationReceiptV1):
        if payload.cancelled:
            return ExitCode.INTERRUPTED
        if not payload.passed:
            return ExitCode.UNHEALTHY
    if isinstance(payload, WriterBenchmarkReceiptV1):
        if payload.cancelled:
            return ExitCode.INTERRUPTED
        if not payload.passed:
            return ExitCode.UNHEALTHY
    if isinstance(payload, RetentionDataV1):
        if payload.failures:
            return ExitCode.PROCESSING_FAILED
        if not payload.admission_allowed_after_plan:
            return ExitCode.UNHEALTHY
    if isinstance(payload, WorkerDataV1):
        if payload.stopped_reason == "cancelled":
            return ExitCode.INTERRUPTED
        if payload.failed_count or payload.rejected_count or payload.error_count:
            return ExitCode.PROCESSING_FAILED
    if isinstance(payload, ReconcileDataV1) and payload.issues:
        return ExitCode.UNHEALTHY
    if isinstance(payload, ImportDataV1) and payload.issues:
        return ExitCode.UNHEALTHY
    return ExitCode.OK


def _message(payload: CliPayload) -> str:
    if isinstance(payload, RadioListDataV1):
        failed = sum(radio.state == "error" for radio in payload.radios)
        return (
            f"{failed} configured radio probe(s) failed."
            if failed
            else f"Found {len(payload.radios)} configured radio(s)."
        )
    if isinstance(payload, DoctorDataV1):
        return "Acquisition checks passed." if payload.healthy else "Acquisition checks failed."
    if isinstance(payload, AcquisitionStatusDataV1):
        return (
            "Acquisition storage has reconciliation issues."
            if payload.reconcile_issue_count
            else "Acquisition status is healthy."
        )
    if isinstance(payload, ProfileValidationDataV1):
        return "Capture profiles are valid." if payload.valid else "Capture profiles are invalid."
    if isinstance(payload, CaptureDataV1):
        return f"Capture {payload.session_id} finished {payload.state.value}."
    if isinstance(payload, RunDataV1):
        return f"Acquisition run stopped: {payload.stopped_reason}."
    if isinstance(payload, AcquisitionQualificationReceiptV1):
        return (
            f"Qualification {payload.qualification_id} passed."
            if payload.passed
            else f"Qualification {payload.qualification_id} did not pass."
        )
    if isinstance(payload, WriterBenchmarkReceiptV1):
        return (
            f"Writer benchmark {payload.benchmark_id} passed."
            if payload.passed
            else f"Writer benchmark {payload.benchmark_id} did not pass."
        )
    if isinstance(payload, SoakSummaryV1):
        return f"Acquisition soak {payload.soak_id} finished {payload.status}."
    if isinstance(payload, SoakAcceptanceAuditReceiptV1):
        return (
            f"Final soak audit {payload.soak_id} passed."
            if payload.accepted
            else f"Final soak audit {payload.soak_id} did not pass."
        )
    if isinstance(payload, CaptureModeCampaignAcceptanceReceiptV2):
        return (
            f"Capture-mode campaign {payload.acceptance_id} passed."
            if payload.accepted
            else f"Capture-mode campaign {payload.acceptance_id} did not pass."
        )
    if isinstance(payload, SessionSearchDataV1):
        return f"Found {len(payload.sessions)} capture session(s)."
    if isinstance(payload, SessionDetailDataV1):
        return f"Capture session {payload.session_id}."
    if isinstance(payload, SessionPathsDataV1):
        return f"Resolved {len(payload.paths)} path(s) for {payload.session_id}."
    if isinstance(payload, ReprocessDataV1):
        return f"Queued reprocessing run {payload.run_id} for {payload.session_id}."
    if isinstance(payload, CancelRunDataV1):
        return (
            f"Analysis run {payload.run_id} "
            f"{'cancelled' if payload.changed else 'was already cancelled'}."
        )
    if isinstance(payload, JobsDataV1):
        return f"Processing backlog: {payload.queued} queued, {payload.running} running."
    if isinstance(payload, HoldDataV1):
        return f"Session {payload.session_id} is {'pinned' if payload.held else 'unpinned'}."
    if isinstance(payload, ImportDataV1):
        return f"Imported {len(payload.fixtures)} verified TEST fixture(s)."
    if isinstance(payload, RetentionDataV1):
        return (
            f"Retention {'plan' if payload.dry_run else 'run'} selected "
            f"{len(payload.selected_ids)} item(s)."
        )
    if isinstance(payload, WorkerDataV1):
        return f"Worker {payload.worker_id} stopped: {payload.stopped_reason}."
    if isinstance(payload, ReconcileDataV1):
        return (
            f"Reconciliation registered {len(payload.registered_sessions)} session(s) and "
            f"queued {len(payload.queued_run_ids)} run(s)."
        )
    return "Command completed."


app = create_cli()


def main() -> None:
    app()
