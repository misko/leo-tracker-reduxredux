from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Event

import pytest
from typer.testing import CliRunner

import leo.qualification.soak_acceptance as soak_acceptance_module
from leo.acquisition import AcquisitionApplication, AcquisitionConfig, AcquisitionCoordinator
from leo.cli import ExitCode, create_cli
from leo.contracts.profile import CapturePlanV1, CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.states import GainMode, SourceType
from leo.domain.profiles import compile_capture_plan
from leo.qualification import (
    AcquisitionSoakHarness,
    PostCommitObservationV1,
    ProcessingBacklogObservationV1,
    SoakConfigV1,
    SoakSummaryV1,
    SoakTrialEvidenceV1,
)
from leo.qualification.soak_acceptance import (
    CohortJob,
    CohortReadResult,
    CohortRun,
    FinalSoakAcceptanceAuditor,
    RuntimeContinuityEvidenceV1,
    SoakExternalThresholdsV1,
    VerifiedBundleV1,
    _active_window,
    _continuity,
    capture_systemd_runtime_continuity,
    resolve_soak_evidence,
)
from leo.radio import FakeRadioSource
from leo.storage import RecordingStore

runner = CliRunner()


class AcquisitionClock:
    def __init__(self) -> None:
        self.utc = 1_900_000_000_000_000_000
        self.monotonic = 5_000_000_000

    def utc_ns(self) -> int:
        self.utc += 10_000
        return self.utc

    def monotonic_ns(self) -> int:
        self.monotonic += 10_000
        return self.monotonic

    def sleep(self, _seconds: float, _cancel: Event) -> None:
        return None

    def wait_until(self, target_monotonic_ns: int, _cancel: Event) -> int:
        self.monotonic = target_monotonic_ns
        return target_monotonic_ns


class SoakClock:
    def __init__(self) -> None:
        self.value = 0
        self.utc_origin = 1_900_000_000_000_000_000

    def monotonic_ns(self) -> int:
        self.value += 1_000_000
        return self.value

    def utc_ns(self) -> int:
        return self.utc_origin + self.value

    def wait(self, cancel: Event, seconds: float) -> bool:
        self.value += round(seconds * 1_000_000_000)
        return cancel.is_set()


class StaticCohortReader:
    def __init__(
        self,
        timestamp: datetime,
        *,
        pending: int = 0,
        inherited: int = 0,
        fail: bool = False,
        run_state: str = "succeeded",
        sealed: bool = True,
        zero_job: bool = False,
        stage_key: str = "raw-validate",
        pipeline_release_id: str = "standard-v1",
    ) -> None:
        self.timestamp = timestamp
        self.pending = pending
        self.inherited = inherited
        self.fail = fail
        self.run_state = run_state
        self.sealed = sealed
        self.zero_job = zero_job
        self.stage_key = stage_key
        self.pipeline_release_id = pipeline_release_id

    def read(
        self,
        *,
        expected_runs: tuple[tuple[str, str], ...],
        soak_created_utc_ns: int,
    ) -> CohortReadResult:
        del soak_created_utc_ns
        if self.fail:
            raise RuntimeError("database unavailable")
        jobs = []
        for run_id, session_id in expected_runs:
            if not self.zero_job:
                jobs.append(
                    CohortJob(
                        run_id=run_id,
                        session_id=session_id,
                        state="succeeded",
                        stage_key=self.stage_key,
                        scope_key="stream-0",
                        created_at=self.timestamp,
                        updated_at=self.timestamp,
                    )
                )
        for _index in range(self.pending):
            jobs.append(
                CohortJob(
                    run_id=expected_runs[0][0],
                    session_id=expected_runs[0][1],
                    state="pending",
                    stage_key="pending-extra",
                    scope_key="stream-0",
                    created_at=self.timestamp,
                    updated_at=self.timestamp,
                )
            )
        return CohortReadResult(
            found_runs=tuple(
                CohortRun(
                    run_id=run_id,
                    session_id=session_id,
                    state=self.run_state,
                    pipeline_release_id=self.pipeline_release_id,
                    sealed_at=self.timestamp if self.sealed else None,
                )
                for run_id, session_id in expected_runs
            ),
            jobs=tuple(jobs),
            inherited_pending_or_leased=self.inherited,
            transaction_read_only=True,
            transaction_isolation="repeatable read",
        )


def _plan() -> CapturePlanV1:
    profile = CaptureProfileV1(
        name="audit-soak-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30),
            ReceiverGainV1(receiver_id=1, gain_db=30),
        ),
        sample_count=8,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        storage_policy="soak-zstd-v1",
        tags=("TEST",),
    )
    return compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ("radio-a",),
        source_type=SourceType.TEST,
    )


def _make_evidence(tmp_path: Path) -> tuple[RecordingStore, Path, SoakExternalThresholdsV1]:
    store = RecordingStore(tmp_path / "bulk")
    acquisition_clock = AcquisitionClock()
    application = AcquisitionApplication(
        AcquisitionCoordinator(
            store,
            clock=acquisition_clock,
            config=AcquisitionConfig(
                release_lead_ns=0,
                safety_reserve_bytes=0,
                metadata_bytes_per_refill=64,
            ),
        )
    )
    soak_clock = SoakClock()
    queue = ProcessingBacklogObservationV1(
        observed_utc_ns=soak_clock.utc_origin,
        queued=0,
        running=0,
        failed=0,
    )

    def post_commit(bundle) -> PostCommitObservationV1:
        return PostCommitObservationV1(
            observed_utc_ns=soak_clock.utc_ns(),
            target_session_id=bundle.session_id,
            attempted=True,
            succeeded=True,
            registered_session_ids=(bundle.session_id,),
            queued_run_ids=(f"run-{bundle.session_id}",),
        )

    duration = 0.008
    harness = AcquisitionSoakHarness(
        store,
        application,
        output_root=store.root / "qualification" / "soak",
        backlog_observer=lambda: queue,
        post_commit_observer=post_commit,
        monotonic_ns=soak_clock.monotonic_ns,
        utc_ns=soak_clock.utc_ns,
        wait=soak_clock.wait,
        peak_rss_bytes=lambda: 100,
    )
    source_index = 0

    def source(radio_id: str) -> FakeRadioSource:
        nonlocal source_index
        source_index += 1
        return FakeRadioSource(
            radio_id,
            seed=42,
            utc_origin_ns=soak_clock.utc_origin + source_index * 1_000_000,
            block_latency_ns=10_000,
        )

    summary = harness.run(
        _plan(),
        source,
        soak_id="acceptance-test",
        configuration=SoakConfigV1(duration_seconds=duration),
    )
    assert summary.passed
    thresholds = SoakExternalThresholdsV1(
        required_active_seconds=duration,
        minimum_sample_derived_duty_cycle=0,
        maximum_inter_capture_gap_seconds=30,
        maximum_soak_origin_pending_or_leased=1_000,
        final_active_window_seconds=min(duration, summary.active_elapsed_seconds),
        expected_jobs_per_run=1,
        expected_stage_keys=("raw-validate",),
    )
    return store, store.root / "qualification/soak/acceptance-test", thresholds


def _window_midpoint(evidence: Path) -> datetime:
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    return datetime.fromtimestamp(summary["updated_utc_ns"] / 1e9, UTC)


def _auditor(
    store: RecordingStore,
    evidence: Path,
    thresholds: SoakExternalThresholdsV1,
    *,
    pending: int = 0,
    inherited: int = 0,
    fail: bool = False,
    run_state: str = "succeeded",
    sealed: bool = True,
    zero_job: bool = False,
    stage_key: str = "raw-validate",
    pipeline_release_id: str = "standard-v1",
    runtime_present: bool = True,
    runtime_n_restarts: int = 0,
    runtime_replaced: bool = False,
    runtime_main_pid: int = 0,
) -> FinalSoakAcceptanceAuditor:
    definition = json.loads((evidence / "definition.json").read_text(encoding="utf-8"))
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    exec_start = definition["created_utc_ns"] + (1 if runtime_replaced else -1)
    runtime = RuntimeContinuityEvidenceV1(
        soak_id="acceptance-test",
        unit_name="leo-soak-acceptance-test.service",
        invocation_id="test-invocation",
        exec_main_pid=1234,
        main_pid_at_observation=runtime_main_pid,
        n_restarts=runtime_n_restarts,
        unit_invocation_start_utc_ns=exec_start - 1,
        exec_main_start_utc_ns=exec_start,
        observed_utc_ns=summary["updated_utc_ns"],
    )
    return FinalSoakAcceptanceAuditor(
        RecordingStore.open_read_only(store.root),
        StaticCohortReader(
            _window_midpoint(evidence),
            pending=pending,
            inherited=inherited,
            fail=fail,
            run_state=run_state,
            sealed=sealed,
            zero_job=zero_job,
            stage_key=stage_key,
            pipeline_release_id=pipeline_release_id,
        ),
        thresholds=thresholds,
        runtime_continuity=runtime if runtime_present else None,
    )


def test_terminal_pass_reverifies_bundles_and_preserves_continuity_honesty(
    tmp_path: Path,
) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)

    receipt = _auditor(store, evidence, thresholds).audit(evidence)

    assert receipt.accepted, tuple(check for check in receipt.checks if not check.passed)
    assert len(receipt.verified_bundles) == receipt.completed_trial_count
    assert receipt.continuity.sample_loss_observable_stream_count > 0
    assert receipt.continuity.device_sample_loss_conclusion == "observable_for_all_streams"
    assert receipt.continuity.zero_reported_host_gaps_proves_zero_device_loss is False
    assert receipt.continuity.reported_gap_count == 0
    assert receipt.cohort.final_active_window.job_arrival_count > 0
    assert (
        receipt.cohort.final_active_window.successful_job_completion_count
        == receipt.cohort.final_active_window.job_arrival_count
    )


def test_receipt_rejects_runtime_digest_unrelated_to_embedded_evidence(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    receipt = _auditor(store, evidence, thresholds).audit(evidence)
    payload = receipt.model_dump()
    payload["runtime_evidence_sha256"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="does not identify"):
        type(receipt).model_validate(payload)


def test_audit_cli_human_and_json_render_the_same_read_only_receipt(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    receipt = _auditor(store, evidence, thresholds).audit(evidence)
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(
        receipt.runtime_continuity.model_dump_json(),  # type: ignore[union-attr]
        encoding="utf-8",
    )
    calls: list[tuple[str, str | None, Path | None, Path | None]] = []

    class AuditOnlyBackend:
        def audit_soak(self, value, *, database_url, receipt_path, runtime_evidence_path):
            calls.append((value, database_url, receipt_path, runtime_evidence_path))
            return receipt

    app = create_cli(lambda: AuditOnlyBackend())  # type: ignore[arg-type,return-value]
    human = runner.invoke(app, ["acquire", "audit-soak", str(evidence)])
    machine = runner.invoke(
        app,
        [
            "acquire",
            "audit-soak",
            str(evidence),
            "--database-url",
            "postgresql://unused",
            "--runtime-evidence",
            str(runtime_path),
            "--json",
        ],
    )

    assert human.exit_code == ExitCode.OK
    assert "accepted=True" in human.stdout
    assert "continuity:" in human.stdout
    assert machine.exit_code == ExitCode.OK
    body = json.loads(machine.stdout)
    assert body["command"] == "acquire.audit-soak"
    assert body["payload"]["kind"] == "soak_acceptance_audit"
    assert body["payload"]["accepted"] is True
    assert calls == [
        (str(evidence), None, None, None),
        (str(evidence), "postgresql://unused", None, runtime_path),
    ]


def test_audit_cli_returns_typed_unhealthy_result_for_nonacceptance(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    receipt = _auditor(store, evidence, thresholds, run_state="running").audit(evidence)

    class AuditOnlyBackend:
        def audit_soak(self, _value, *, database_url, receipt_path, runtime_evidence_path):
            del database_url, receipt_path, runtime_evidence_path
            return receipt

    app = create_cli(lambda: AuditOnlyBackend())  # type: ignore[arg-type,return-value]
    result = runner.invoke(app, ["acquire", "audit-soak", str(evidence), "--json"])

    assert result.exit_code == ExitCode.UNHEALTHY
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["payload"]["kind"] == "soak_acceptance_audit"
    assert body["payload"]["accepted"] is False


def _terminal_systemd_properties(*, active: bool = False, restarts: int = 0) -> str:
    return "\n".join(
        (
            f"ActiveState={'active' if active else 'inactive'}",
            f"SubState={'running' if active else 'dead'}",
            "Result=success",
            "InvocationID=0123456789abcdef0123456789abcdef",
            "ExecMainPID=4321",
            f"MainPID={4321 if active else 0}",
            f"NRestarts={restarts}",
            "InactiveExitTimestamp=Wed 2026-08-19 03:47:45 UTC",
            "ExecMainStartTimestamp=Wed 2026-08-19 03:47:45.123456 UTC",
        )
    )


def test_runtime_capture_is_terminal_bounded_create_only_evidence(tmp_path: Path) -> None:
    output = tmp_path / "runtime.json"
    commands: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...]) -> str:
        commands.append(command)
        return _terminal_systemd_properties(restarts=1)

    evidence = capture_systemd_runtime_continuity(
        "production-24h-test",
        output,
        command_runner=run,
        observed_utc_ns=1_787_227_202_000_000_000,
    )

    assert commands[0][:4] == (
        "systemctl",
        "--user",
        "show",
        "leo-soak-production-24h-test.service",
    )
    assert evidence.n_restarts == 1  # Record honestly; the auditor rejects it.
    assert evidence.exec_main_start_utc_ns % 1_000_000_000 == 123_456_000
    assert output.stat().st_mode & 0o777 == 0o440
    assert output.stat().st_size < 64 * 1024
    assert RuntimeContinuityEvidenceV1.model_validate_json(output.read_bytes()) == evidence
    with pytest.raises(FileExistsError, match="already exists"):
        capture_systemd_runtime_continuity(
            "production-24h-test",
            output,
            command_runner=run,
            observed_utc_ns=1_787_227_202_000_000_000,
        )


def test_runtime_capture_refuses_running_or_malformed_unit_without_output(tmp_path: Path) -> None:
    running_output = tmp_path / "running.json"
    with pytest.raises(ValueError, match="not terminal"):
        capture_systemd_runtime_continuity(
            "production-24h-test",
            running_output,
            command_runner=lambda _command: _terminal_systemd_properties(active=True),
        )
    assert not running_output.exists()

    malformed_output = tmp_path / "malformed.json"
    malformed = _terminal_systemd_properties().replace(" UTC", " local", 1)
    with pytest.raises(ValueError, match="C-locale UTC"):
        capture_systemd_runtime_continuity(
            "production-24h-test",
            malformed_output,
            command_runner=lambda _command: malformed,
        )
    assert not malformed_output.exists()


def test_runtime_capture_cli_is_a_thin_typed_command(tmp_path: Path) -> None:
    output = tmp_path / "runtime.json"
    evidence = RuntimeContinuityEvidenceV1(
        soak_id="production-24h-test",
        unit_name="leo-soak-production-24h-test.service",
        invocation_id="invocation",
        exec_main_pid=4321,
        main_pid_at_observation=0,
        n_restarts=0,
        unit_invocation_start_utc_ns=1,
        exec_main_start_utc_ns=2,
        observed_utc_ns=3,
    )
    calls: list[tuple[str, Path]] = []

    class RuntimeOnlyBackend:
        def capture_soak_runtime(self, soak_id: str, *, output_path: Path):
            calls.append((soak_id, output_path))
            return evidence

    app = create_cli(lambda: RuntimeOnlyBackend())  # type: ignore[arg-type,return-value]
    result = runner.invoke(
        app,
        [
            "acquire",
            "capture-soak-runtime",
            "production-24h-test",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.OK
    body = json.loads(result.stdout)
    assert body["command"] == "acquire.capture-soak-runtime"
    assert body["payload"] == evidence.model_dump(mode="json")
    assert calls == [("production-24h-test", output)]


def test_unobservable_streams_never_become_a_zero_device_loss_claim() -> None:
    continuity = _continuity(
        (
            VerifiedBundleV1(
                session_id="unobservable",
                bundle_uri="bulk://recordings/2030/01/01/unobservable",
                manifest_sha256="sha256:" + "a" * 64,
                chunk_count=1,
                compressed_bytes=10,
                uncompressed_bytes=20,
                stream_count=2,
                stream_ids=("radio-a", "radio-b"),
                sample_loss_observable_stream_count=0,
                sample_loss_unobservable_stream_count=2,
                reported_gap_count=0,
                reported_overflow_count=0,
                guaranteed_overlap_ns=0,
            ),
        )
    )

    assert continuity.device_sample_loss_conclusion == "not_observable_for_all_streams"
    assert continuity.zero_reported_host_gaps_proves_zero_device_loss is False
    assert continuity.minimum_guaranteed_overlap_ns == 0


def test_final_active_window_fails_closed_across_restart_sized_discontinuity(
    tmp_path: Path,
) -> None:
    _store, evidence, thresholds = _make_evidence(tmp_path)
    summary = SoakSummaryV1.model_validate_json((evidence / "summary.json").read_bytes())
    trials = tuple(
        SoakTrialEvidenceV1.model_validate_json(path.read_bytes())
        for path in sorted((evidence / "trials").glob("trial-*.json"))
    )
    shift_ns = 60 * 1_000_000_000
    shifted = (
        trials[0],
        *(
            trial.model_copy(
                update={
                    "capture_started_utc_ns": trial.capture_started_utc_ns + shift_ns,
                    "capture_finished_utc_ns": trial.capture_finished_utc_ns + shift_ns,
                }
            )
            for trial in trials[1:]
        ),
    )
    shifted_summary = summary.model_copy(
        update={"updated_utc_ns": summary.updated_utc_ns + shift_ns}
    )

    window = _active_window(
        shifted_summary,
        shifted,
        thresholds.final_active_window_seconds,
        maximum_delta_seconds=thresholds.maximum_active_wall_delta_seconds,
    )

    assert not window.mapping_accepted_within_tolerance
    assert window.ambiguous_discontinuity_count == 1
    assert window.represented_seconds == 0
    assert window.active_utc_segments == ()


def test_running_summary_is_a_reproducible_non_acceptance(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    path = evidence / "summary.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(status="running", completion_reason="running", complete=False, passed=False)
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = _auditor(store, evidence, thresholds).audit(evidence)

    assert not receipt.accepted
    assert not next(check for check in receipt.checks if check.name == "terminal_summary").passed


def test_unexpected_or_missing_trial_evidence_cannot_pass(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    unexpected = evidence / "trials/.unfinished.partial"
    unexpected.write_text("not immutable evidence", encoding="utf-8")

    receipt = _auditor(store, evidence, thresholds).audit(evidence)

    assert not receipt.accepted
    assert not next(check for check in receipt.checks if check.name == "trial_contiguity").passed


def test_external_threshold_and_database_failures_are_explicit(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    strict = thresholds.model_copy(update={"minimum_sample_derived_duty_cycle": 1.0})

    threshold_receipt = _auditor(store, evidence, strict).audit(evidence)
    database_receipt = _auditor(store, evidence, thresholds, fail=True).audit(evidence)

    assert not threshold_receipt.accepted
    assert not next(
        check for check in threshold_receipt.checks if check.name == "external_minimum_duty_cycle"
    ).passed
    assert not database_receipt.accepted
    assert not database_receipt.cohort.database_available
    assert "database unavailable" in (database_receipt.cohort.error or "")


@pytest.mark.parametrize(
    "options",
    [
        {"runtime_present": False},
        {"runtime_n_restarts": 1},
        {"runtime_replaced": True},
        {"runtime_main_pid": 9999},
    ],
)
def test_missing_restarted_or_replaced_runtime_invocation_cannot_pass(
    tmp_path: Path, options: dict[str, object]
) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)

    receipt = _auditor(store, evidence, thresholds, **options).audit(evidence)  # type: ignore[arg-type]

    assert not receipt.accepted
    check = next(check for check in receipt.checks if check.name == "runtime_invocation_continuity")
    assert not check.passed


@pytest.mark.parametrize("pending", [1, 999])
def test_less_than_limit_does_not_substitute_for_zero_cohort_drain(
    tmp_path: Path, pending: int
) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)

    receipt = _auditor(store, evidence, thresholds, pending=pending).audit(evidence)

    assert not receipt.accepted
    assert next(
        check for check in receipt.checks if check.name == "soak_origin_outstanding_below_limit"
    ).passed
    assert not next(
        check for check in receipt.checks if check.name == "soak_origin_queue_drained"
    ).passed


def test_inherited_queue_must_be_drained(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)

    receipt = _auditor(store, evidence, thresholds, inherited=1).audit(evidence)

    assert not receipt.accepted
    assert not next(
        check for check in receipt.checks if check.name == "inherited_queue_drained"
    ).passed


@pytest.mark.parametrize(
    ("options", "expected_fragment"),
    [
        ({"run_state": "running"}, "non_succeeded=3"),
        ({"sealed": False}, "unsealed=3"),
        ({"zero_job": True}, "zero_job=3"),
        ({"stage_key": "wrong-stage"}, "wrong_inventory=3"),
        ({"pipeline_release_id": "research-v1"}, "wrong_release=3"),
    ],
)
def test_every_run_must_be_sealed_succeeded_and_have_exact_standard_inventory(
    tmp_path: Path,
    options: dict[str, object],
    expected_fragment: str,
) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)

    receipt = _auditor(store, evidence, thresholds, **options).audit(evidence)  # type: ignore[arg-type]

    assert not receipt.accepted
    check = next(check for check in receipt.checks if check.name == "terminal_succeeded_runs")
    assert not check.passed
    assert expected_fragment in check.detail


def test_receipt_is_atomic_read_only_and_never_overwritten(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    auditor = _auditor(store, evidence, thresholds)
    receipt_path = tmp_path / "acceptance.json"

    first = auditor.audit(evidence, receipt_path=receipt_path)

    assert receipt_path.stat().st_mode & 0o777 == 0o440
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["accepted"] is first.accepted
    with pytest.raises(FileExistsError, match="already exists"):
        auditor.audit(evidence, receipt_path=receipt_path)


def test_symlinked_receipt_parent_is_rejected_without_following_it(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    auditor = _auditor(store, evidence, thresholds)
    target = tmp_path / "unfollowed-target"
    target.mkdir()
    linked = tmp_path / "linked-parent"
    linked.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked"):
        auditor.audit(evidence, receipt_path=linked / "forbidden.json")
    assert tuple(target.iterdir()) == ()


def test_symlinked_receipt_final_component_is_rejected_without_following_target(
    tmp_path: Path,
) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    auditor = _auditor(store, evidence, thresholds)
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("unchanged", encoding="utf-8")
    receipt_path = tmp_path / "receipt-link.json"
    receipt_path.symlink_to(sentinel)

    with pytest.raises(FileExistsError, match="already exists"):
        auditor.audit(evidence, receipt_path=receipt_path)

    assert receipt_path.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


def test_receipt_link_failure_leaves_no_destination_or_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    auditor = _auditor(store, evidence, thresholds)
    receipt_path = tmp_path / "link-failure.json"

    def fail_link(*_args, **_kwargs):
        raise OSError("injected link failure")

    monkeypatch.setattr(soak_acceptance_module.os, "link", fail_link)
    with pytest.raises(OSError, match="injected link failure"):
        auditor.audit(evidence, receipt_path=receipt_path)

    assert not os.path.lexists(receipt_path)
    assert not tuple(tmp_path.glob(".*.partial"))


def test_safe_id_symlink_is_rejected_before_candidate_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bulk = tmp_path / "bulk"
    soak_root = bulk / "qualification" / "soak"
    soak_root.mkdir(parents=True)
    sentinel = tmp_path / "sentinel-target"
    sentinel.mkdir()
    candidate = soak_root / "linked-soak"
    candidate.symlink_to(sentinel, target_is_directory=True)
    original_resolve = Path.resolve

    def guarded_resolve(path: Path, *args, **kwargs):
        if path == candidate:
            raise AssertionError("candidate symlink was resolved")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    with pytest.raises(ValueError, match="symlinked"):
        resolve_soak_evidence("linked-soak", bulk_root=bulk)


def test_qnap_evidence_is_rejected_lexically_before_any_lookup(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"
    bulk.mkdir()

    with pytest.raises(ValueError, match="never read soak evidence"):
        resolve_soak_evidence(
            "/mnt/qnap01/this-path-must-not-be-probed",
            bulk_root=bulk,
        )


def test_corrupted_bundle_is_not_accepted(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    trial = json.loads(next((evidence / "trials").glob("trial-*.json")).read_text(encoding="utf-8"))
    bundle = store.inspect_uri(trial["bundle_uri"])
    chunk = bundle.manifest.streams[0].chunks[0]
    path = bundle.path / chunk.relative_path
    path.chmod(0o640)
    path.write_bytes(path.read_bytes() + b"corruption")

    receipt = _auditor(store, evidence, thresholds).audit(evidence)

    assert not receipt.accepted
    check = next(check for check in receipt.checks if check.name == "recording_bundle_digests")
    assert not check.passed
    assert "compressed chunk" in check.detail


def test_auditor_reports_corruption_in_first_and_later_trial_bundles(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    trial_paths = sorted((evidence / "trials").glob("trial-*.json"))
    corrupted_sessions = []
    for trial_path in (trial_paths[0], trial_paths[-1]):
        trial = json.loads(trial_path.read_text(encoding="utf-8"))
        bundle = store.inspect_uri(trial["bundle_uri"])
        chunk_path = bundle.path / bundle.manifest.streams[0].chunks[0].relative_path
        chunk_path.chmod(0o640)
        chunk_path.write_bytes(chunk_path.read_bytes() + b"corruption")
        corrupted_sessions.append(trial["session_id"])

    receipt = _auditor(store, evidence, thresholds).audit(evidence)

    check = next(check for check in receipt.checks if check.name == "recording_bundle_digests")
    assert not check.passed
    assert all(session_id in check.detail for session_id in corrupted_sessions)


def test_bundle_plan_must_match_immutable_soak_definition(tmp_path: Path) -> None:
    store, evidence, thresholds = _make_evidence(tmp_path)
    definition_path = evidence / "definition.json"
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    definition["profile_name"] = "different-profile"
    definition_path.write_text(json.dumps(definition), encoding="utf-8")

    receipt = _auditor(store, evidence, thresholds).audit(evidence)

    assert not receipt.accepted
    check = next(check for check in receipt.checks if check.name == "recording_bundle_digests")
    assert not check.passed
    assert "immutable soak definition" in check.detail
