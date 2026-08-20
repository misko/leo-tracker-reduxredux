from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from leo.application.calibration_operations import CalibrationQueueResultV1
from leo.application.calibration_runtime import CalibrationOperationalEvidenceError
from leo.application.frequency_calibration import CalibrationPromotionError, ImmutableDocumentRefV1
from leo.catalog import ProductConflictError
from leo.cli.app import create_cli
from leo.cli.calibration import CalibrationCliBackend
from leo.cli.models import CalibrationQueueDataV1, ExitCode
from leo.qualification.frequency_calibration_documents import CalibrationPlanConflict

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


def test_calibration_predeclare_has_no_caller_controlled_evidence_uri() -> None:
    result = runner.invoke(
        create_cli(lambda: _CalibrationBackend()),
        ["process", "calibration", "predeclare", "--help"],
    )

    assert result.exit_code == ExitCode.OK
    assert "--evidence-uri" not in result.stdout
    assert "--starlink-channel" in result.stdout
    assert "--starlink-edge" in result.stdout


@pytest.mark.parametrize(
    "selection_args",
    (
        (),
        ("--starlink-channel", "ch1", "--starlink-edge", "lower"),
        ("--starlink-channel", "ch4", "--starlink-edge", "upper"),
    ),
)
def test_calibration_predeclare_requires_explicit_supported_channel_and_edge(
    selection_args: tuple[str, ...],
) -> None:
    result = runner.invoke(
        create_cli(lambda: _CalibrationBackend()),
        [
            "process",
            "calibration",
            "predeclare",
            "--plan-id",
            "plan-a",
            "--radio-id",
            "radio-a",
            "--session",
            "session-a",
            *selection_args,
        ],
    )

    assert result.exit_code == 2


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


def test_calibration_queue_missing_uses_stable_not_found_exit() -> None:
    class MissingOperations:
        def queue(self, _ref):
            raise KeyError("missing-session")

    backend = CalibrationCliBackend(MissingOperations())  # type: ignore[arg-type]
    result = runner.invoke(
        create_cli(lambda: backend),  # type: ignore[arg-type,return-value]
        [
            "process",
            "calibration",
            "queue",
            "--plan-uri",
            PLAN_URI,
            "--plan-digest",
            PLAN_DIGEST,
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.NOT_FOUND
    assert json.loads(result.stdout)["exit_code"] == ExitCode.NOT_FOUND


def test_calibration_promote_catalog_conflict_uses_stable_conflict_exit() -> None:
    class ConflictingOperations:
        def promote(self, **_values):
            raise ProductConflictError("immutable calibration conflicts")

    backend = CalibrationCliBackend(ConflictingOperations())  # type: ignore[arg-type]
    arguments = [
        "process",
        "calibration",
        "promote",
        "--plan-uri",
        PLAN_URI,
        "--plan-digest",
        PLAN_DIGEST,
        "--promotion-id",
        "promotion-a",
        "--calibration-id",
        "calibration-a",
        "--calibration-set-id",
        "set-a",
    ]
    human = runner.invoke(create_cli(lambda: backend), arguments)  # type: ignore[arg-type,return-value]
    machine = runner.invoke(create_cli(lambda: backend), [*arguments, "--json"])  # type: ignore[arg-type,return-value]

    assert human.exit_code == ExitCode.CONFLICT
    assert machine.exit_code == ExitCode.CONFLICT
    assert json.loads(machine.stdout)["exit_code"] == ExitCode.CONFLICT


def test_calibration_promote_insufficient_uses_stable_unhealthy_exit() -> None:
    class InsufficientOperations:
        def promote(self, **_values):
            raise CalibrationPromotionError("calibration evidence is insufficient")

    backend = CalibrationCliBackend(InsufficientOperations())  # type: ignore[arg-type]
    arguments = [
        "process",
        "calibration",
        "promote",
        "--plan-uri",
        PLAN_URI,
        "--plan-digest",
        PLAN_DIGEST,
        "--promotion-id",
        "promotion-a",
        "--calibration-id",
        "calibration-a",
        "--calibration-set-id",
        "set-a",
    ]
    human = runner.invoke(create_cli(lambda: backend), arguments)  # type: ignore[arg-type,return-value]
    machine = runner.invoke(create_cli(lambda: backend), [*arguments, "--json"])  # type: ignore[arg-type,return-value]

    assert human.exit_code == ExitCode.UNHEALTHY
    assert machine.exit_code == ExitCode.UNHEALTHY
    assert json.loads(machine.stdout)["exit_code"] == ExitCode.UNHEALTHY


def test_calibration_promote_missing_plan_uses_not_found_human_and_json() -> None:
    class MissingPlanOperations:
        def promote(self, **_values):
            raise FileNotFoundError("immutable plan is absent")

    backend = CalibrationCliBackend(MissingPlanOperations())  # type: ignore[arg-type]
    arguments = [
        "process",
        "calibration",
        "promote",
        "--plan-uri",
        PLAN_URI,
        "--plan-digest",
        PLAN_DIGEST,
        "--promotion-id",
        "promotion-a",
        "--calibration-id",
        "calibration-a",
        "--calibration-set-id",
        "set-a",
    ]
    human = runner.invoke(create_cli(lambda: backend), arguments)  # type: ignore[arg-type,return-value]
    machine = runner.invoke(create_cli(lambda: backend), [*arguments, "--json"])  # type: ignore[arg-type,return-value]

    assert human.exit_code == ExitCode.NOT_FOUND
    assert machine.exit_code == ExitCode.NOT_FOUND
    assert json.loads(machine.stdout)["exit_code"] == ExitCode.NOT_FOUND


def test_calibration_predeclare_identity_conflict_uses_conflict_human_and_json() -> None:
    class ConflictingPlanOperations:
        def predeclare(self, **_values):
            raise CalibrationPlanConflict("plan ID contains different immutable content")

    backend = CalibrationCliBackend(ConflictingPlanOperations())  # type: ignore[arg-type]
    arguments = [
        "process",
        "calibration",
        "predeclare",
        "--plan-id",
        "plan-a",
        "--radio-id",
        "radio_pluto_19f2",
        "--starlink-channel",
        "ch4",
        "--starlink-edge",
        "lower",
        "--session",
        "session-a",
        "--session",
        "session-b",
        "--session",
        "session-c",
    ]
    human = runner.invoke(create_cli(lambda: backend), arguments)  # type: ignore[arg-type,return-value]
    machine = runner.invoke(create_cli(lambda: backend), [*arguments, "--json"])  # type: ignore[arg-type,return-value]

    assert human.exit_code == ExitCode.CONFLICT
    assert machine.exit_code == ExitCode.CONFLICT
    assert json.loads(machine.stdout)["exit_code"] == ExitCode.CONFLICT


def test_calibration_promote_unsealed_evidence_uses_unhealthy_human_and_json() -> None:
    class UnsealedOperations:
        def promote(self, **_values):
            raise CalibrationOperationalEvidenceError(
                "calibration extractor run is not sealed and successful"
            )

    backend = CalibrationCliBackend(UnsealedOperations())  # type: ignore[arg-type]
    arguments = [
        "process",
        "calibration",
        "promote",
        "--plan-uri",
        PLAN_URI,
        "--plan-digest",
        PLAN_DIGEST,
        "--promotion-id",
        "promotion-unsealed",
        "--calibration-id",
        "calibration-unsealed",
        "--calibration-set-id",
        "set-unsealed",
    ]
    human = runner.invoke(create_cli(lambda: backend), arguments)  # type: ignore[arg-type,return-value]
    machine = runner.invoke(create_cli(lambda: backend), [*arguments, "--json"])  # type: ignore[arg-type,return-value]

    assert human.exit_code == ExitCode.UNHEALTHY
    assert machine.exit_code == ExitCode.UNHEALTHY
    assert json.loads(machine.stdout)["exit_code"] == ExitCode.UNHEALTHY
