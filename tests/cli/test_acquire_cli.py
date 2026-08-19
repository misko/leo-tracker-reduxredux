from __future__ import annotations

import json
import tomllib
from pathlib import Path
from threading import Event
from typing import cast

import pytest
from typer.testing import CliRunner

from leo.acquisition import CaptureSessionResult, StorageAdmissionDecision
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
from leo.contracts.states import CaptureState
from leo.storage import RecordingStore

runner = CliRunner()


def test_packaged_leo_entrypoint_targets_cli_main() -> None:
    pyproject = Path(__file__).parents[2] / "pyproject.toml"
    configuration = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert configuration["project"]["scripts"]["leo"] == "leo.cli:main"


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

    status = runner.invoke(app, ["acquire", "status", "--json"])
    assert status.exit_code == ExitCode.OK
    status_body = _json(status.stdout)["payload"]
    assert status_body["committed_recording_count"] == 1
    assert status_body["last_capture"]["session_id"] == "cli-once"


def test_run_is_foreground_bounded_for_qualification(configured_cli) -> None:
    app, settings = configured_cli
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
    assert payload["stopped_reason"] == "maximum_captures"
    assert payload["capture_count"] == 2
    assert payload["committed_count"] == 2
    assert len(RecordingStore(settings.bulk_root).reconcile().committed) == 2


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

        def storage_admission(self) -> StorageAdmissionDecision:
            return StorageAdmissionDecision(allowed=True, used_fraction=0.2)

        def reconcile(self) -> ReconcileDataV1:
            self.reconciled += 1
            return ReconcileDataV1(
                restored_purges=(),
                discarded_purges=(),
                registered_sessions=("auto-visible",),
                existing_sessions=(),
                queued_run_ids=("capture-run",),
                issues=(),
            )

        def reconcile_session(self, _session_id: str) -> ReconcileDataV1:
            return self.reconcile()

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


def test_continuous_runner_propagates_one_cancellation_event() -> None:
    cancel = Event()

    class CancellingBackend:
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
        "jobs",
        "pin",
        "unpin",
        "import-qnap",
        "retention-status",
        "retention-run",
        "reconcile",
        "worker",
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
