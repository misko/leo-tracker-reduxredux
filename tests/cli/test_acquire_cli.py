from __future__ import annotations

import hashlib
import json
import stat
import tomllib
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any, cast

import pytest
from typer.testing import CliRunner

import leo.qualification.capture_modes as capture_modes_module
from leo.acquisition import (
    AcquisitionQueuePressure,
    CaptureSessionResult,
    StorageAdmissionDecision,
)
from leo.cli import (
    CliSettings,
    CompositionHooks,
    ExitCode,
    configured_backend_factory,
    create_cli,
)
from leo.cli.backend import AcquisitionCliBackend, ProcessingCliBackend
from leo.cli.composition import RadioConfigurationV1
from leo.cli.models import CaptureDataV1, JobsDataV1, ReconcileDataV1
from leo.cli.runner import ContinuousAcquisitionRunner
from leo.contracts.states import CaptureState, SynchronizationGrade
from leo.qualification import (
    CaptureModeAcceptanceHarness,
    CaptureModeExpectationV1,
    CaptureModeSessionCheckV1,
    CaptureModeStreamTimingEvidenceV1,
)
from leo.storage import RecordingStore
from tests.postgres_support import isolated_test_schema_url

runner = CliRunner()


def test_packaged_leo_entrypoint_targets_cli_main() -> None:
    pyproject = Path(__file__).parents[2] / "pyproject.toml"
    configuration = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert configuration["project"]["scripts"]["leo"] == "leo.cli:main"


def test_cli_qualification_defaults_follow_the_configured_bulk_root(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"

    settings = CliSettings.from_environ({"LEO_BULK_ROOT": str(bulk)})

    assert settings.qualification_root == bulk / "qualification"
    assert settings.capture_evidence_root == bulk / "qualification" / "capture"
    assert settings.legacy_evidence_root == bulk / "qualification" / "legacy"
    assert settings.scanner_dwell_ms == 120
    assert settings.scanner_persistent_transition_guard_us == 5_000
    assert settings.scanner_persistent_read_ahead_visits == 8
    assert settings.scanner_persistent_queue_capacity_visits == 64
    assert settings.scanner_persistent_iiod_port == 30_432


@pytest.mark.parametrize(
    "report_root",
    (Path("relative/scanner"), Path("/mnt/qnap01/scanner")),
)
def test_scanner_report_root_must_be_local_and_absolute(tmp_path: Path, report_root: Path) -> None:
    with pytest.raises(ValueError, match="scanner report"):
        CliSettings(
            profile_root=tmp_path / "profiles",
            bulk_root=tmp_path / "bulk",
            radio_backend="fake",
            radios=(),
            scanner_report_root=report_root,
        )


@pytest.fixture
def configured_cli(tmp_path: Path):
    profile_root = tmp_path / "profiles"
    profile_root.mkdir()
    (profile_root / "tiny.yaml").write_text(
        """\
schema_version: 1
name: tiny-test
center_frequency_hz: 1700000000
sample_rate_hz: 2500000
bandwidth_hz: 2500000
receivers: [0, 1]
gain_mode: manual
gains:
  - {schema_version: 1, receiver_id: 0, gain_db: 30.0}
  - {schema_version: 1, receiver_id: 1, gain_db: 30.0}
sample_count: 8
refill_samples: 4
settle_seconds: 0
prime_refills: 0
continuity_policy: require_contiguous
synchronization_mode: best_effort
peer_failure_policy: keep_survivor
storage_policy: test-zstd-v1
tags: [TEST]
""",
        encoding="utf-8",
    )
    settings = CliSettings(
        profile_root=profile_root,
        bulk_root=tmp_path / "bulk",
        radio_backend="fake",
        radios=(
            RadioConfigurationV1(radio_id="radio-a", receiver_count=2),
            RadioConfigurationV1(radio_id="radio-b", receiver_count=2),
        ),
        safety_reserve_bytes=0,
    )
    return create_cli(configured_backend_factory(settings)), settings


@pytest.fixture
def cli_database_url():
    with isolated_test_schema_url(prefix="leo_cli") as database_url:
        yield database_url


def _json(output: str) -> dict:
    return json.loads(output)


def test_radio_human_and_json_views_use_same_values(configured_cli) -> None:
    app, _settings = configured_cli

    human = runner.invoke(app, ["acquire", "radios"])
    machine = runner.invoke(app, ["acquire", "radios", "--json"])

    assert human.exit_code == ExitCode.OK
    assert "radio-a" in human.stdout
    assert "radio-b" in human.stdout
    result = _json(machine.stdout)
    assert result["schema_version"] == 1
    assert result["command"] == "acquire.radios"
    assert [item["radio_id"] for item in result["payload"]["radios"]] == [
        "radio-a",
        "radio-b",
    ]


def test_profile_list_show_and_validate_are_typed_json(configured_cli) -> None:
    app, _settings = configured_cli

    listed = runner.invoke(app, ["acquire", "profiles", "list", "--json"])
    shown = runner.invoke(
        app,
        ["acquire", "profiles", "show", "tiny-test", "--json"],
    )
    validated = runner.invoke(
        app,
        ["acquire", "profiles", "validate", "tiny-test", "--json"],
    )

    assert listed.exit_code == ExitCode.OK
    assert _json(listed.stdout)["payload"]["profiles"][0]["name"] == "tiny-test"
    assert _json(shown.stdout)["payload"]["revision"]["profile"]["sample_count"] == 8
    assert _json(validated.stdout)["payload"]["valid"] is True


def test_profile_show_preserves_continuity_v2_contract(tmp_path: Path) -> None:
    settings = CliSettings(
        profile_root=Path(__file__).parents[2] / "profiles",
        bulk_root=tmp_path / "bulk",
        radio_backend="fake",
        radios=(),
        safety_reserve_bytes=0,
    )
    app = create_cli(configured_backend_factory(settings))

    shown = runner.invoke(
        app,
        [
            "acquire",
            "profiles",
            "show",
            "starlink-ch4-lower-2p5m-60s-continuity-v2",
            "--json",
        ],
    )

    assert shown.exit_code == ExitCode.OK
    payload = _json(shown.stdout)["payload"]
    assert payload["kind"] == "profile_show_v2"
    assert payload["revision"]["schema_version"] == 2
    assert payload["revision"]["profile"]["kernel_buffers"] == 8


def test_missing_profile_has_stable_not_found_exit_and_json(configured_cli) -> None:
    app, _settings = configured_cli
    result = runner.invoke(
        app,
        ["acquire", "profiles", "show", "absent", "--json"],
    )

    assert result.exit_code == ExitCode.NOT_FOUND
    body = _json(result.stdout)
    assert body["ok"] is False
    assert body["exit_code"] == ExitCode.NOT_FOUND
    assert body["payload"] is None


def test_doctor_checks_fake_configuration_without_hardware(configured_cli) -> None:
    app, _settings = configured_cli
    result = runner.invoke(
        app,
        ["acquire", "doctor", "--probe-radios", "--json"],
    )

    assert result.exit_code == ExitCode.OK
    body = _json(result.stdout)
    assert body["payload"]["healthy"] is True
    assert {check["name"] for check in body["payload"]["checks"]} == {
        "profiles",
        "bulk_storage",
        "radios",
    }


def test_doctor_without_radios_uses_stable_unhealthy_exit(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    settings = CliSettings(
        profile_root=profiles,
        bulk_root=tmp_path / "bulk",
        radio_backend="fake",
        radios=(),
        safety_reserve_bytes=0,
    )
    app = create_cli(configured_backend_factory(settings))

    result = runner.invoke(app, ["acquire", "doctor", "--json"])

    assert result.exit_code == ExitCode.UNHEALTHY
    assert _json(result.stdout)["exit_code"] == ExitCode.UNHEALTHY


def test_once_runs_fake_capture_and_status_finds_committed_bundle(configured_cli) -> None:
    app, settings = configured_cli
    captured = runner.invoke(
        app,
        [
            "acquire",
            "once",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--session-id",
            "cli-once",
            "--json",
        ],
    )

    assert captured.exit_code == ExitCode.OK, captured.stdout
    body = _json(captured.stdout)
    assert body["payload"]["state"] == "committed"
    assert body["payload"]["radio_ids"] == ["radio-a"]
    bundle = RecordingStore(settings.bulk_root).inspect("cli-once")
    assert bundle.manifest.source_type.value == "test"
    assert "TEST" in bundle.manifest.tags
    assert bundle.manifest.producer.source_revision == settings.pipeline_release_id

    status = runner.invoke(app, ["acquire", "status", "--json"])
    assert status.exit_code == ExitCode.OK
    status_body = _json(status.stdout)["payload"]
    assert status_body["committed_recording_count"] == 1
    assert status_body["last_capture"]["session_id"] == "cli-once"


def test_durable_pause_blocks_manual_capture_until_resume(configured_cli) -> None:
    app, settings = configured_cli

    paused = runner.invoke(
        app,
        [
            "acquire",
            "pause",
            "--operator",
            "test-operator",
            "--reason",
            "integration test",
            "--json",
        ],
    )
    blocked = runner.invoke(
        app,
        [
            "acquire",
            "once",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--session-id",
            "must-not-exist",
            "--json",
        ],
    )
    status = runner.invoke(app, ["acquire", "status", "--json"])
    resumed = runner.invoke(
        app,
        ["acquire", "resume", "--operator", "test-operator", "--json"],
    )

    assert paused.exit_code == ExitCode.OK
    assert _json(paused.stdout)["payload"]["state"]["observed_state"] == "paused"
    assert blocked.exit_code == ExitCode.CONFLICT
    assert not (settings.bulk_root / "spool" / "must-not-exist.partial").exists()
    assert _json(status.stdout)["payload"]["capture_control"]["desired_state"] == "paused"
    assert resumed.exit_code == ExitCode.OK
    assert _json(resumed.stdout)["payload"]["state"]["observed_state"] == "running"

    captured = runner.invoke(
        app,
        [
            "acquire",
            "once",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--session-id",
            "after-resume",
            "--json",
        ],
    )
    assert captured.exit_code == ExitCode.OK, captured.stdout


@pytest.mark.postgres
def test_run_is_foreground_bounded_for_qualification(configured_cli, cli_database_url) -> None:
    _app, settings = configured_cli
    settings = replace(settings, database_url=cli_database_url)

    class AvailableCatalog:
        def jobs(self) -> JobsDataV1:
            return JobsDataV1(
                queued=0,
                running=0,
                failed=0,
                oldest_queued_seconds=None,
            )

        def storage_admission(self) -> StorageAdmissionDecision:
            return StorageAdmissionDecision(allowed=True, used_fraction=0.2)

        def reconcile_session(self, session_id: str) -> ReconcileDataV1:
            return ReconcileDataV1(
                restored_purges=(),
                discarded_purges=(),
                registered_sessions=(session_id,),
                existing_sessions=(),
                queued_run_ids=(),
                issues=(),
            )

    hooks = CompositionHooks(
        processing_backend_factory=lambda _settings: cast(ProcessingCliBackend, AvailableCatalog())
    )
    app = create_cli(configured_backend_factory(settings, hooks))
    result = runner.invoke(
        app,
        [
            "acquire",
            "run",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--max-captures",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.OK, result.stdout
    payload = _json(result.stdout)["payload"]
    assert payload["kind"] == "run"
    assert payload["profile_name"] == "tiny-test"
    assert payload["stopped_reason"] == "maximum_captures"
    assert payload["capture_count"] == 2
    assert payload["committed_count"] == 2
    assert len(RecordingStore(settings.bulk_root).reconcile().committed) == 2


def test_run_accepts_an_exact_repeated_profile_pool_and_emits_v2_json() -> None:
    profile_names = (
        "starlink-ch4-lower-2p5m-60s-continuity-v2",
        "starlink-ch4-lower-3m-60s-capture-v2",
        "starlink-ch4-lower-5m-60s-segmented-v2",
    )

    class MultiProfileBackend:
        def __init__(self) -> None:
            self.validated: list[str] = []
            self.capture_requests: list[tuple[str, tuple[str, ...]]] = []

        def profile_show(self, name: str):
            assert name in profile_names
            self.validated.append(name)
            return object()

        def acquisition_queue_pressure(self) -> AcquisitionQueuePressure:
            return AcquisitionQueuePressure(queued=0, running=0)

        def capture_once(self, profile_name: str, **kwargs) -> CaptureDataV1:
            radio_ids = tuple(kwargs["radio_ids"])
            self.capture_requests.append((profile_name, radio_ids))
            return CaptureDataV1(
                session_id="multi-profile-one",
                state=CaptureState.COMMITTED,
                radio_ids=radio_ids,
                profile_name=profile_name,
                raw_iq_bytes=32,
                required_free_bytes=32,
                available_free_bytes=1024,
            )

    backend = MultiProfileBackend()
    arguments = ["acquire", "run"]
    for profile_name in profile_names:
        arguments.extend(("--profile", profile_name))
    arguments.extend(("--radio", "radio-a", "--radio", "radio-b", "--max-captures", "1"))
    arguments.append("--json")

    result = runner.invoke(
        create_cli(lambda: backend),  # type: ignore[arg-type,return-value]
        arguments,
    )

    assert result.exit_code == ExitCode.OK, result.stdout
    payload = _json(result.stdout)["payload"]
    assert payload["kind"] == "run_v2"
    assert payload["profile_names"] == list(profile_names)
    assert payload["selection_policy"] == "uniform_per_dwell"
    assert payload["last_capture"]["profile_name"] in profile_names
    assert backend.validated == list(profile_names)
    assert backend.capture_requests == [
        (payload["last_capture"]["profile_name"], ("radio-a", "radio-b"))
    ]


def test_run_help_exposes_bounded_scanner_only_controls() -> None:
    result = runner.invoke(create_cli(lambda: cast(Any, None)), ["acquire", "run", "--help"])

    assert result.exit_code == ExitCode.OK, result.stdout
    assert "--scanner-only" in result.stdout
    assert "--max-scanner-runs" in result.stdout
    assert "after N scanner starts" in result.stdout


def test_admission_rejection_has_distinct_automation_exit(configured_cli) -> None:
    _app, settings = configured_cli
    constrained = CliSettings(
        profile_root=settings.profile_root,
        bulk_root=settings.bulk_root,
        radio_backend=settings.radio_backend,
        radios=settings.radios,
        safety_reserve_bytes=10**30,
    )
    app = create_cli(configured_backend_factory(constrained))

    result = runner.invoke(
        app,
        ["acquire", "once", "--profile", "tiny-test", "--json"],
    )

    assert result.exit_code == ExitCode.ADMISSION_REJECTED
    assert _json(result.stdout)["payload"]["state"] == "failed"


def test_production_composition_observer_receives_capture_result(configured_cli) -> None:
    _app, settings = configured_cli
    observed: list[CaptureSessionResult] = []
    stores: list[Path] = []

    def make_store(root: Path) -> RecordingStore:
        stores.append(root)
        return RecordingStore(root)

    hooks = CompositionHooks(
        recording_store_factory=make_store,
        capture_observer=observed.append,
    )
    app = create_cli(configured_backend_factory(settings, hooks))

    result = runner.invoke(
        app,
        [
            "acquire",
            "once",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--session-id",
            "hooked-capture",
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.OK
    assert stores == [settings.bulk_root]
    assert len(observed) == 1
    assert observed[0].session_id == "hooked-capture"


def test_committed_capture_automatically_reconciles_when_catalog_is_available(
    configured_cli,
) -> None:
    _app, settings = configured_cli

    class AvailableCatalog:
        def __init__(self) -> None:
            self.reconciled = 0
            self.targeted_sessions: list[str] = []

        def storage_admission(self) -> StorageAdmissionDecision:
            return StorageAdmissionDecision(allowed=True, used_fraction=0.2)

        def reconcile(self) -> ReconcileDataV1:
            raise AssertionError("new capture must not rescan historical inventory")

        def reconcile_session(self, _session_id: str) -> ReconcileDataV1:
            self.targeted_sessions.append(_session_id)
            self.reconciled += 1
            return ReconcileDataV1(
                restored_purges=(),
                discarded_purges=(),
                registered_sessions=("auto-visible",),
                existing_sessions=(),
                queued_run_ids=("capture-run",),
                issues=(),
            )

    catalog = AvailableCatalog()
    hooks = CompositionHooks(
        processing_backend_factory=lambda _settings: cast(ProcessingCliBackend, catalog)
    )
    app = create_cli(configured_backend_factory(settings, hooks))

    result = runner.invoke(
        app,
        [
            "acquire",
            "once",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--session-id",
            "auto-visible",
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.OK, result.stdout
    assert catalog.reconciled == 1
    assert catalog.targeted_sessions == ["auto-visible"]
    assert _json(result.stdout)["payload"]["errors"] == []


def test_catalog_outage_never_invalidates_committed_capture_and_is_durable(
    configured_cli,
) -> None:
    _app, settings = configured_cli

    class UnavailableCatalog:
        def storage_admission(self) -> StorageAdmissionDecision:
            return StorageAdmissionDecision(allowed=True, warning=True)

        def reconcile(self) -> ReconcileDataV1:
            raise RuntimeError("database unavailable")

        def reconcile_session(self, session_id: str) -> ReconcileDataV1:
            del session_id
            raise RuntimeError("database unavailable")

    hooks = CompositionHooks(
        processing_backend_factory=lambda _settings: cast(
            ProcessingCliBackend, UnavailableCatalog()
        )
    )
    app = create_cli(configured_backend_factory(settings, hooks))
    captured = runner.invoke(
        app,
        [
            "acquire",
            "once",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--session-id",
            "catalog-outage",
            "--json",
        ],
    )

    assert captured.exit_code == ExitCode.OK, captured.stdout
    payload = _json(captured.stdout)["payload"]
    assert payload["state"] == "committed"
    assert "registration is pending" in payload["errors"][0]
    RecordingStore(settings.bulk_root).verify("catalog-outage")

    status = runner.invoke(app, ["acquire", "status", "--json"])
    assert status.exit_code == ExitCode.UNHEALTHY
    warning = _json(status.stdout)["payload"]["catalog_registration_warning"]
    assert warning is not None and "database unavailable" in warning


def test_continuous_acquisition_pressure_adapter_reports_queued_and_running_separately(
    configured_cli,
) -> None:
    _app, settings = configured_cli

    class QueueCatalog:
        def jobs(self) -> JobsDataV1:
            return JobsDataV1(
                queued=31,
                running=777,
                failed=12,
                oldest_queued_seconds=4.0,
            )

    hooks = CompositionHooks(
        processing_backend_factory=lambda _settings: cast(ProcessingCliBackend, QueueCatalog())
    )
    backend = configured_backend_factory(settings, hooks)()

    pressure = backend.acquisition_queue_pressure()

    assert pressure == AcquisitionQueuePressure(queued=31, running=777)


def test_continuous_runner_propagates_one_cancellation_event() -> None:
    cancel = Event()

    class CancellingBackend:
        def acquisition_queue_pressure(self):
            return AcquisitionQueuePressure(queued=0, running=0)

        def capture_once(self, profile_name, **kwargs):
            kwargs["cancel"].set()
            return CaptureDataV1(
                session_id="cancelled-after-one",
                state=CaptureState.COMMITTED,
                radio_ids=("radio-a",),
                profile_name=profile_name,
                raw_iq_bytes=32,
                required_free_bytes=32,
                available_free_bytes=1024,
            )

    backend = cast(AcquisitionCliBackend, CancellingBackend())
    summary = ContinuousAcquisitionRunner(backend).run(
        "tiny-test",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=0,
        maximum_captures=None,
        cancel=cancel,
    )

    assert summary.stopped_reason == "cancelled"
    assert summary.capture_count == 1
    assert summary.committed_count == 1


def test_continuous_runner_holds_exact_start_to_start_period() -> None:
    class RecordingCancel:
        def __init__(self) -> None:
            self.waits: list[float] = []

        def is_set(self) -> bool:
            return False

        def wait(self, timeout: float) -> bool:
            self.waits.append(timeout)
            return True

        def set(self) -> None:
            pass

    class CommittedBackend:
        def acquisition_queue_pressure(self):
            return AcquisitionQueuePressure(queued=0, running=0)

        def capture_once(self, profile_name, **kwargs):
            return CaptureDataV1(
                session_id="periodic-one",
                state=CaptureState.COMMITTED,
                radio_ids=("radio-a",),
                profile_name=profile_name,
                raw_iq_bytes=32,
                required_free_bytes=32,
                available_free_bytes=1024,
            )

    times = iter((10.0, 78.5))
    cancel = RecordingCancel()
    summary = ContinuousAcquisitionRunner(
        cast(AcquisitionCliBackend, CommittedBackend()),
        clock=lambda: next(times),
    ).run(
        "tiny-test",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=180.0,
        maximum_captures=None,
        cancel=cast(Event, cancel),
    )

    assert cancel.waits == [111.5]
    assert summary.stopped_reason == "cancelled"
    assert summary.capture_count == 1


def test_process_group_reports_the_production_command_inventory(configured_cli) -> None:
    app, _settings = configured_cli
    result = runner.invoke(app, ["process", "--json"])

    assert result.exit_code == ExitCode.OK
    payload = _json(result.stdout)["payload"]
    assert payload["kind"] == "process_help"
    assert payload["available_commands"] == [
        "search",
        "show",
        "paths",
        "reprocess",
        "cancel-run",
        "stop-and-fence",
        "jobs",
        "pin",
        "unpin",
        "import-qnap",
        "retention-status",
        "retention-run",
        "reconcile",
        "worker",
        "calibration",
        "wp11",
    ]


def test_qualify_command_runs_and_resumes_typed_dual_trials(configured_cli) -> None:
    app, settings = configured_cli
    receipt = settings.bulk_root / "qualification" / "cli-qual.json"
    arguments = [
        "acquire",
        "qualify",
        "--profile",
        "tiny-test",
        "--trials",
        "2",
        "--qualification-id",
        "cli-qual",
        "--receipt",
        str(receipt),
        "--json",
    ]

    first = runner.invoke(app, arguments)
    resumed = runner.invoke(app, arguments)

    assert first.exit_code == ExitCode.OK, first.stdout
    payload = _json(first.stdout)["payload"]
    assert payload["kind"] == "acquisition_qualification"
    assert payload["passed"] is True
    assert payload["aggregate"]["completed_trial_count"] == 2
    assert resumed.exit_code == ExitCode.OK
    assert len(RecordingStore(settings.bulk_root).reconcile().committed) == 2


def test_capture_mode_campaign_audit_is_read_only_and_can_seal_receipt(
    configured_cli,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _original_app, settings = configured_cli
    settings = CliSettings(
        profile_root=settings.profile_root,
        bulk_root=settings.bulk_root,
        radio_backend="pluto",
        radios=(
            RadioConfigurationV1(
                radio_id="radio_pluto_5d4d",
                serial="1040005e0b100007100010000bf33a5d4d",
                host="192.168.1.20",
                receiver_count=2,
            ),
            RadioConfigurationV1(
                radio_id="radio_pluto_19f2",
                serial="10400056f695001322002d0010ad1719f2",
                host="192.168.1.21",
                receiver_count=2,
            ),
        ),
        safety_reserve_bytes=0,
    )
    production_profile = (
        Path(__file__).parents[2] / "profiles" / "starlink-ch4-lower-2p5m-60s-rx1-centered-v1.yaml"
    )
    (settings.profile_root / production_profile.name).write_text(
        production_profile.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    RecordingStore(settings.bulk_root)
    app = create_cli(configured_backend_factory(settings))
    independent_a = [f"cli-independent-a-{index:02d}" for index in range(10)]
    independent_b = [f"cli-independent-b-{index:02d}" for index in range(10)]
    synchronized = [f"cli-synchronized-{index:02d}" for index in range(10)]

    def check_without_iq(
        _self: CaptureModeAcceptanceHarness,
        _expectation: CaptureModeExpectationV1,
        role: capture_modes_module.CaptureModeRole,
        session_id: str,
        expected_radios: tuple[str, ...],
    ) -> CaptureModeSessionCheckV1:
        expected_label = {
            "independent_radio_a": "independent-a",
            "independent_radio_b": "independent-b",
            "synchronized_pair": "synchronized",
        }[role]
        passed = expected_label in session_id
        if not passed:
            return CaptureModeSessionCheckV1(
                role=role,
                session_id=session_id,
                expected_radio_ids=expected_radios,
                digest_valid=True,
                errors=("injected wrong-role evidence",),
            )
        identities = {
            "radio_pluto_5d4d": (
                "1040005e0b100007100010000bf33a5d4d",
                "ip:192.168.1.20",
                "rx_lnb_b",
            ),
            "radio_pluto_19f2": (
                "10400056f695001322002d0010ad1719f2",
                "ip:192.168.1.21",
                "rx_lnb_d",
            ),
        }
        timing = tuple(
            CaptureModeStreamTimingEvidenceV1(
                stream_id=f"stream-{index}",
                radio_id=radio_id,
                sample_count=_expectation.sample_count,
                sample_rate_hz=_expectation.sample_rate_hz,
                first_estimate_utc_ns=1_800_000_000_000_000_000 + index * 100,
                first_earliest_utc_ns=1_799_999_999_999_999_990 + index * 100,
                first_latest_utc_ns=1_800_000_000_000_000_010 + index * 100,
                first_uncertainty_ns=20,
                last_estimate_utc_ns=1_800_000_059_999_999_600 + index * 100,
                last_earliest_utc_ns=1_800_000_059_999_999_590 + index * 100,
                last_latest_utc_ns=1_800_000_059_999_999_610 + index * 100,
                last_uncertainty_ns=20,
                sample_interval_end_estimate_utc_ns=(1_800_000_060_000_000_000 + index * 100),
            )
            for index, radio_id in enumerate(expected_radios)
        )
        pair = role == "synchronized_pair"
        recomputed = (
            capture_modes_module._recompute_pair_timing((timing[0], timing[1]))
            if pair
            else (None, None, None, None, None, None)
        )
        return CaptureModeSessionCheckV1(
            role=role,
            session_id=session_id,
            expected_radio_ids=expected_radios,
            bundle_uri=f"bulk://recordings/2026/08/19/{session_id}",
            manifest_session_id=session_id,
            manifest_sha256="sha256:" + hashlib.sha256(session_id.encode()).hexdigest(),
            digest_valid=True,
            observed_radio_ids=expected_radios,
            observed_radio_serials=tuple(identities[item][0] for item in expected_radios),
            observed_radio_uris=tuple(identities[item][1] for item in expected_radios),
            declared_receiver_chain_ids=tuple(identities[item][2] for item in expected_radios),
            declared_hardware_epoch_ids=tuple(
                {
                    "radio_pluto_5d4d": "hw_gauss_r20_science_postreboot_20260816_v1",
                    "radio_pluto_19f2": "hw_gauss_r21_science_postreboot_20260816_v1",
                }[item]
                for item in expected_radios
            ),
            declared_station_topology_evidence_digests=tuple(
                {
                    "radio_pluto_5d4d": (
                        "sha256:eff9673575738b3bd72246d02252e41b5d1d548ae775e9eb453e1ee3a8290bfa"
                    ),
                    "radio_pluto_19f2": (
                        "sha256:eb69aef0b2211b3073d125da66f29ec2154e06a4a52916c2d0a036e8f17efef7"
                    ),
                }[item]
                for item in expected_radios
            ),
            observed_receiver_ids=tuple((1,) for _ in expected_radios),
            observed_sample_counts=tuple(_expectation.sample_count for _ in expected_radios),
            observed_gain_db=tuple(40.0 for _ in expected_radios),
            observed_gap_counts=tuple(0 for _ in expected_radios),
            observed_missing_sample_counts=tuple(0 for _ in expected_radios),
            observed_overflow_counts=tuple(0 for _ in expected_radios),
            observed_clipped_sample_counts=tuple(0 for _ in expected_radios),
            observed_clipped_sample_fractions=tuple(0.0 for _ in expected_radios),
            observed_constant_iq=tuple(False for _ in expected_radios),
            stream_timing=timing,
            synchronization_grade=(
                SynchronizationGrade.BEST_EFFORT_OBSERVED
                if pair
                else SynchronizationGrade.NOT_REQUESTED
            ),
            manifest_overlap_fraction=recomputed[1],
            estimated_overlap_ns=recomputed[0],
            overlap_fraction=recomputed[1],
            guaranteed_overlap_ns=recomputed[2],
            guaranteed_overlap_fraction=recomputed[3],
            estimated_start_skew_ns=recomputed[4],
            start_skew_uncertainty_ns=recomputed[5],
            overlap_rounding_tolerance_ns=1 if pair else None,
            passed=True,
        )

    monkeypatch.setattr(CaptureModeAcceptanceHarness, "_check", check_without_iq)

    arguments = [
        "acquire",
        "audit-capture-modes",
        "--profile",
        "starlink-ch4-lower-2p5m-60s-rx1-centered-v1",
        "--radio-a",
        "radio_pluto_5d4d",
        "--radio-b",
        "radio_pluto_19f2",
        "--acceptance-id",
        "cli-capture-mode-campaign",
    ]
    for session_id in independent_a:
        arguments.extend(("--independent-a-session", session_id))
    for session_id in independent_b:
        arguments.extend(("--independent-b-session", session_id))
    for session_id in synchronized:
        arguments.extend(("--synchronized-session", session_id))

    def reject_create_on_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("capture-mode audit used the mutating RecordingStore constructor")

    monkeypatch.setattr(RecordingStore, "__init__", reject_create_on_open)

    dry = runner.invoke(app, [*arguments, "--json"])

    assert dry.exit_code == ExitCode.OK, dry.stdout
    payload = _json(dry.stdout)["payload"]
    assert payload["kind"] == "single_rx_capture_mode_campaign_acceptance"
    assert payload["schema_version"] == 2
    assert payload["accepted"] is True
    assert len(payload["trial_receipts"]) == 10
    assert not (tmp_path / "campaign-receipt.json").exists()
    help_result = runner.invoke(app, ["acquire", "audit-capture-modes", "--help"])
    assert help_result.exit_code == ExitCode.OK
    assert "--minimum-overlap" not in help_result.stdout

    tiny_arguments = list(arguments)
    tiny_arguments[tiny_arguments.index("starlink-ch4-lower-2p5m-60s-rx1-centered-v1")] = (
        "tiny-test"
    )
    tiny = runner.invoke(app, [*tiny_arguments, "--json"])
    assert tiny.exit_code == ExitCode.INVALID_CONFIGURATION
    assert _json(tiny.stdout)["payload"] is None

    arbitrary_radio_arguments = list(arguments)
    arbitrary_radio_arguments[arbitrary_radio_arguments.index("radio_pluto_5d4d")] = (
        "arbitrary-radio"
    )
    arbitrary_radio = runner.invoke(app, [*arbitrary_radio_arguments, "--json"])
    assert arbitrary_radio.exit_code == ExitCode.INVALID_CONFIGURATION

    wrong_serial_settings = replace(
        settings,
        radios=(
            settings.radios[0].model_copy(update={"serial": "wrong-serial"}),
            settings.radios[1],
        ),
    )
    wrong_serial_app = create_cli(configured_backend_factory(wrong_serial_settings))
    wrong_serial = runner.invoke(wrong_serial_app, [*arguments, "--json"])
    assert wrong_serial.exit_code == ExitCode.INVALID_CONFIGURATION
    assert "does not attest radio_pluto_5d4d" in _json(wrong_serial.stdout)["message"]

    receipt_path = tmp_path / "campaign-receipt.json"
    sealed = runner.invoke(app, [*arguments, "--receipt", str(receipt_path)])

    assert sealed.exit_code == ExitCode.OK, sealed.stdout
    assert "sessions=30" in sealed.stdout
    assert receipt_path.is_file()
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o440

    wrong_roles = list(arguments)
    independent_a_index = wrong_roles.index(independent_a[0])
    independent_b_index = wrong_roles.index(independent_b[0])
    wrong_roles[independent_a_index], wrong_roles[independent_b_index] = (
        wrong_roles[independent_b_index],
        wrong_roles[independent_a_index],
    )
    rejected = runner.invoke(app, [*wrong_roles, "--json"])
    assert rejected.exit_code == ExitCode.UNHEALTHY
    assert _json(rejected.stdout)["payload"]["accepted"] is False

    wrong_count = runner.invoke(
        app,
        [
            *arguments[:],
            "--independent-a-session",
            independent_a[0],
            "--json",
        ],
    )
    assert wrong_count.exit_code == ExitCode.INVALID_CONFIGURATION


def test_writer_benchmark_command_emits_versioned_receipt(configured_cli) -> None:
    app, settings = configured_cli
    receipt = settings.bulk_root / "qualification" / "writer-cli.json"
    result = runner.invoke(
        app,
        [
            "acquire",
            "benchmark-writer",
            "--duration-seconds",
            "0.005",
            "--minimum-mb-s",
            "0.001",
            "--block-bytes",
            "65536",
            "--benchmark-id",
            "writer-cli",
            "--receipt",
            str(receipt),
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.OK, result.stdout
    payload = _json(result.stdout)["payload"]
    assert payload["kind"] == "writer_benchmark"
    assert payload["schema_version"] == 1
    assert payload["passed"] is True
    assert payload["digest_valid"] is True
    assert receipt.is_file()
    RecordingStore(settings.bulk_root).verify("writer-cli")


def test_soak_command_is_thin_resumable_and_writes_bounded_evidence(
    configured_cli,
    tmp_path: Path,
) -> None:
    app, _settings = configured_cli
    output = tmp_path / "soak-evidence"
    arguments = [
        "acquire",
        "soak",
        "--profile",
        "tiny-test",
        "--radio",
        "radio-a",
        "--duration-seconds",
        "0.001",
        "--cadence-seconds",
        "0",
        "--soak-id",
        "cli-soak",
        "--output-dir",
        str(output),
        "--json",
    ]

    first = runner.invoke(app, arguments)
    resumed = runner.invoke(app, arguments)

    assert first.exit_code == ExitCode.OK, first.stdout
    payload = _json(first.stdout)["payload"]
    assert payload["kind"] == "acquisition_soak_summary"
    assert payload["status"] == "complete"
    assert payload["completed_trial_count"] >= 1
    assert resumed.exit_code == ExitCode.OK, resumed.stdout
    assert (output / "cli-soak" / "definition.json").is_file()
    assert (output / "cli-soak" / "summary.json").is_file()


def test_soak_reconciles_and_queues_each_trial_before_backlog_after(
    configured_cli,
    tmp_path: Path,
) -> None:
    _app, settings = configured_cli
    session_id = "integrated-soak-trial-00000001"

    class PerTrialCatalog:
        def __init__(self) -> None:
            self.queue = 0
            self.reconciled = 0

        def storage_admission(self) -> StorageAdmissionDecision:
            return StorageAdmissionDecision(allowed=True, used_fraction=0.2)

        def jobs(self) -> JobsDataV1:
            return JobsDataV1(
                queued=self.queue,
                running=0,
                failed=0,
                oldest_queued_seconds=0 if self.queue else None,
            )

        def reconcile(self) -> ReconcileDataV1:
            self.reconciled += 1
            first = self.reconciled == 1
            if first:
                self.queue += 1
            return ReconcileDataV1(
                restored_purges=(),
                discarded_purges=(),
                registered_sessions=(session_id,) if first else (),
                existing_sessions=() if first else (session_id,),
                queued_run_ids=("integrated-run",) if first else (),
                issues=(),
            )

        def reconcile_session(self, _session_id: str) -> ReconcileDataV1:
            return self.reconcile()

    catalog = PerTrialCatalog()
    hooks = CompositionHooks(
        processing_backend_factory=lambda _settings: cast(ProcessingCliBackend, catalog)
    )
    app = create_cli(configured_backend_factory(settings, hooks))
    output = tmp_path / "integrated-evidence"
    result = runner.invoke(
        app,
        [
            "acquire",
            "soak",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--duration-seconds",
            "0.001",
            "--soak-id",
            "integrated-soak",
            "--output-dir",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.OK, result.stdout
    evidence = json.loads((output / "integrated-soak/trials/trial-00000000.json").read_text())
    definition = json.loads((output / "integrated-soak/definition.json").read_text())
    assert catalog.reconciled >= 1
    assert evidence["state"] == "committed"
    assert evidence["recording_tags"] == ["TEST"]
    assert evidence["post_commit"]["succeeded"] is True
    assert evidence["post_commit"]["queued_run_ids"] == ["integrated-run"]
    assert evidence["processing_backlog_before"]["queued"] == 0
    assert evidence["processing_backlog_after"]["queued"] == 1
    assert definition["recording_tag_policy"] == "preserve_profile_tags_and_queue"


def test_soak_database_outage_preserves_iq_and_final_reconcile_recovers(
    configured_cli,
    tmp_path: Path,
) -> None:
    _app, settings = configured_cli
    session_id = "outage-soak-trial-00000001"

    class RecoveringCatalog:
        def __init__(self) -> None:
            self.reconciled = 0

        def storage_admission(self) -> StorageAdmissionDecision:
            return StorageAdmissionDecision(allowed=True, used_fraction=0.2)

        def jobs(self) -> JobsDataV1:
            return JobsDataV1(
                queued=0,
                running=0,
                failed=0,
                oldest_queued_seconds=None,
            )

        def reconcile(self) -> ReconcileDataV1:
            self.reconciled += 1
            if self.reconciled == 1:
                raise RuntimeError("database temporarily unavailable")
            return ReconcileDataV1(
                restored_purges=(),
                discarded_purges=(),
                registered_sessions=(session_id,),
                existing_sessions=(),
                queued_run_ids=("recovered-analysis",),
                issues=(),
            )

        def reconcile_session(self, _session_id: str) -> ReconcileDataV1:
            return self.reconcile()

    catalog = RecoveringCatalog()
    hooks = CompositionHooks(
        processing_backend_factory=lambda _settings: cast(ProcessingCliBackend, catalog)
    )
    app = create_cli(configured_backend_factory(settings, hooks))
    output = tmp_path / "outage-evidence"
    result = runner.invoke(
        app,
        [
            "acquire",
            "soak",
            "--profile",
            "tiny-test",
            "--radio",
            "radio-a",
            "--duration-seconds",
            "0.001",
            "--soak-id",
            "outage-soak",
            "--output-dir",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.UNHEALTHY, result.stdout
    payload = _json(result.stdout)["payload"]
    assert payload["committed_count"] == 1
    assert payload["post_commit_failure_count"] == 1
    assert payload["passed"] is False
    evidence = json.loads((output / "outage-soak/trials/trial-00000000.json").read_text())
    assert evidence["state"] == "committed"
    assert evidence["digest_valid"] is True
    assert evidence["errors"] == []
    assert evidence["post_commit"]["succeeded"] is False
    assert "database temporarily unavailable" in evidence["post_commit"]["error"]
    assert catalog.reconciled == 2
    RecordingStore(settings.bulk_root).verify(session_id)
