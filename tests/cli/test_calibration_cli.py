from __future__ import annotations

import json

from typer.testing import CliRunner

from leo.application.calibration_operations import CalibrationQueueResultV1
from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.cli.app import create_cli
from leo.cli.calibration import CalibrationCliBackend
from leo.cli.models import CalibrationQueueDataV1, ExitCode

runner = CliRunner()
PLAN_DIGEST = "sha256:" + "a" * 64
PLAN_URI = "qualification://frequency-calibration-predeclarations/cli-plan"


class _CalibrationBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def calibration_queue(self, *, plan_uri: str, plan_digest: str) -> CalibrationQueueDataV1:
        self.calls.append((plan_uri, plan_digest))
        return CalibrationQueueDataV1(
            result=CalibrationQueueResultV1(
                plan_ref=ImmutableDocumentRefV1(
                    logical_uri=plan_uri,
                    digest=plan_digest,
                ),
                stage_key="wp11-frequency-calibration-extractor",
                session_run_ids=(("future-1", "run-future-1"),),
            )
        )


def test_calibration_queue_human_and_json_share_typed_backend_model() -> None:
    backend = _CalibrationBackend()
    app = create_cli(lambda: backend)  # type: ignore[arg-type,return-value]
    arguments = [
        "process",
        "calibration",
        "queue",
        "--plan-uri",
        PLAN_URI,
        "--plan-digest",
        PLAN_DIGEST,
    ]

    machine = runner.invoke(app, [*arguments, "--json"])
    human = runner.invoke(app, arguments)

    assert machine.exit_code == ExitCode.OK
    assert human.exit_code == ExitCode.OK
    result = json.loads(machine.stdout)
    assert result["payload"]["kind"] == "calibration_queue"
    assert result["payload"]["result"]["promotion_policy"] == "evidence_only"
    assert "stage=wp11-frequency-calibration-extractor policy=evidence_only" in human.stdout
    assert backend.calls == [(PLAN_URI, PLAN_DIGEST), (PLAN_URI, PLAN_DIGEST)]


def test_calibration_command_inventory_is_exact() -> None:
    result = runner.invoke(create_cli(lambda: _CalibrationBackend()), ["process", "calibration"])

    assert result.exit_code == 2
    for command in ("predeclare", "queue", "promote", "show"):
        assert command in result.stdout


def test_calibration_show_missing_uses_stable_not_found_exit() -> None:
    class MissingOperations:
        def show(self, promotion_id: str):
            raise KeyError(promotion_id)

    backend = CalibrationCliBackend(MissingOperations())  # type: ignore[arg-type]
    result = runner.invoke(
        create_cli(lambda: backend),  # type: ignore[arg-type,return-value]
        ["process", "calibration", "show", "missing", "--json"],
    )

    assert result.exit_code == ExitCode.NOT_FOUND
    assert json.loads(result.stdout)["exit_code"] == ExitCode.NOT_FOUND
