from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.application.wp11_legacy import WP11ConfigPublication, WP11LegacyRunResult
from leo.application.wp11_operations import (
    WP11CampaignSummary,
    WP11CreateResult,
    WP11Operations,
    WP11QueueResult,
)
from leo.application.wp11_production import WP11RunConflict
from leo.cli.app import create_cli
from leo.cli.backend import CliBackendError
from leo.cli.models import (
    ExitCode,
    WP11ConfigDataV1,
    WP11CreateDataV1,
    WP11LegacyDataV1,
    WP11QueueDataV1,
    WP11ShowDataV1,
)
from leo.cli.wp11 import WP11CliBackend

_REF = ImmutableDocumentRefV1(
    logical_uri="qualification://wp11-plans/campaign-a.json",
    digest="sha256:" + "1" * 64,
)
_CAPTURE = ImmutableDocumentRefV1(
    logical_uri="qualification://capture/accepted.json",
    digest="sha256:" + "2" * 64,
)


class _Backend:
    def wp11_config(self, *, output_path: Path) -> WP11ConfigDataV1:
        return WP11ConfigDataV1(
            result=WP11ConfigPublication(
                output_path=str(output_path),
                config_digest="sha256:" + "3" * 64,
                state="created",
            )
        )

    def wp11_create(self, **_kwargs) -> WP11CreateDataV1:
        return WP11CreateDataV1(
            result=WP11CreateResult(
                campaign_id="campaign-a",
                plan=_REF,
                capture=_CAPTURE,
                session_count=30,
                stream_count=40,
                pipeline_release_id="release-a",
            )
        )

    def wp11_queue(self, campaign_id: str) -> WP11QueueDataV1:
        return WP11QueueDataV1(
            result=WP11QueueResult(
                campaign_id=campaign_id,
                run_ids=tuple(f"wp11-{index:02d}" for index in range(30)),
                session_count=30,
                stream_count=40,
                already_queued_count=0,
            )
        )

    def wp11_legacy(self, campaign_id: str, *, ordinals: tuple[int, ...]) -> WP11LegacyDataV1:
        return WP11LegacyDataV1(
            result=WP11LegacyRunResult(
                campaign_id=campaign_id,
                requested_count=len(ordinals),
                created_count=len(ordinals),
                existing_count=0,
                receipts=(),
            )
        )

    def wp11_finalize(self, _campaign_id: str):
        raise CliBackendError("campaign has unfinished runs", ExitCode.UNHEALTHY)

    def wp11_show(self, campaign_id: str) -> WP11ShowDataV1:
        return WP11ShowDataV1(
            summary=WP11CampaignSummary(
                campaign_id=campaign_id,
                state="processing",
                result_status=None,
                mathematical_eligible=None,
                production_accepted=None,
                session_count=30,
                stream_count=40,
            )
        )


def test_wp11_command_inventory_and_typed_human_json(tmp_path: Path) -> None:
    runner = CliRunner()
    app = create_cli(lambda: _Backend())  # type: ignore[arg-type]
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    help_result = runner.invoke(app, ["process", "wp11", "--help"])
    assert help_result.exit_code == ExitCode.OK
    for command in ("config", "create", "legacy", "queue", "finalize", "show"):
        assert command in help_result.stdout

    config_result = runner.invoke(
        app,
        ["process", "wp11", "config", "--output", str(config), "--json"],
    )
    assert config_result.exit_code == ExitCode.OK
    assert json.loads(config_result.stdout)["payload"]["result"]["state"] == "created"

    create_args = [
        "process",
        "wp11",
        "create",
        "--campaign-id",
        "campaign-a",
        "--capture-uri",
        _CAPTURE.logical_uri,
        "--capture-digest",
        _CAPTURE.digest,
        "--config",
        str(config),
    ]
    human = runner.invoke(app, create_args)
    machine = runner.invoke(app, [*create_args, "--json"])
    assert human.exit_code == machine.exit_code == ExitCode.OK
    assert json.loads(machine.stdout)["payload"]["result"]["stream_count"] == 40

    legacy = runner.invoke(
        app,
        ["process", "wp11", "legacy", "campaign-a", "--ordinal", "0", "--json"],
    )
    assert legacy.exit_code == ExitCode.OK
    assert json.loads(legacy.stdout)["payload"]["result"]["requested_count"] == 1

    queued = runner.invoke(app, ["process", "wp11", "queue", "campaign-a", "--json"])
    assert queued.exit_code == ExitCode.OK
    assert len(json.loads(queued.stdout)["payload"]["result"]["run_ids"]) == 30
    shown = runner.invoke(app, ["process", "wp11", "show", "campaign-a", "--json"])
    assert json.loads(shown.stdout)["payload"]["summary"]["state"] == "processing"
    final = runner.invoke(app, ["process", "wp11", "finalize", "campaign-a", "--json"])
    assert final.exit_code == ExitCode.UNHEALTHY
    assert json.loads(final.stdout)["exit_code"] == ExitCode.UNHEALTHY


def test_wp11_queue_conflict_is_stable_for_human_and_json() -> None:
    class ConflictingWorkflow:
        def queue(self, _campaign_id: str):
            raise WP11RunConflict("deterministic run differs from immutable plan")

    class CompleteLegacy:
        def require_complete(self, _campaign_id: str) -> None:
            return None

    backend = WP11CliBackend(
        WP11Operations(ConflictingWorkflow()),  # type: ignore[arg-type]
        CompleteLegacy(),  # type: ignore[arg-type]
    )
    app = create_cli(lambda: backend)  # type: ignore[arg-type]
    arguments = ["process", "wp11", "queue", "campaign-a"]
    human = CliRunner().invoke(app, arguments)
    machine = CliRunner().invoke(app, [*arguments, "--json"])
    assert human.exit_code == ExitCode.CONFLICT
    assert machine.exit_code == ExitCode.CONFLICT
    assert json.loads(machine.stdout)["exit_code"] == ExitCode.CONFLICT


def test_wp11_queue_refuses_to_create_jobs_before_all_legacy_receipts() -> None:
    class Workflow:
        def queue(self, _campaign_id: str):
            raise AssertionError("queue must not be reached")

    class IncompleteLegacy:
        def require_complete(self, _campaign_id: str) -> None:
            raise FileNotFoundError("legacy receipt 07 is absent")

    backend = WP11CliBackend(
        WP11Operations(Workflow()),  # type: ignore[arg-type]
        IncompleteLegacy(),  # type: ignore[arg-type]
    )
    app = create_cli(lambda: backend)  # type: ignore[arg-type]
    for suffix in ([], ["--json"]):
        result = CliRunner().invoke(
            app,
            ["process", "wp11", "queue", "campaign-a", *suffix],
        )
        assert result.exit_code == ExitCode.NOT_FOUND
        assert "legacy" in result.stdout.lower()
