from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any, cast

from typer.testing import CliRunner

from leo.cli.app import create_cli
from leo.cli.composition import BackendFactory
from leo.cli.models import (
    AnalysisRunDataV1,
    CancelRunDataV1,
    ExitCode,
    HoldDataV1,
    ImportDataV1,
    ImportFixtureDataV1,
    JobsDataV1,
    PathItemDataV1,
    ReconcileDataV1,
    ReprocessDataV1,
    RetentionDataV1,
    SessionDetailDataV1,
    SessionPathsDataV1,
    SessionSearchDataV1,
    SessionSearchItemV1,
    WorkerDataV1,
)

runner = CliRunner()
NOW = datetime(2026, 8, 19, tzinfo=UTC)


class FakeProcessBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def search_sessions(self, **kwargs) -> SessionSearchDataV1:
        self.calls.append(("search", kwargs))
        return SessionSearchDataV1(
            sessions=(
                SessionSearchItemV1(
                    session_id="session-a",
                    source_type="test",
                    state="committed",
                    created_at=NOW,
                    bundle_uri="bulk://recordings/2026/08/19/session-a",
                    held=True,
                    tags=("TEST",),
                    current_run_id="run-old",
                ),
            )
        )

    def show_session(self, session_id: str) -> SessionDetailDataV1:
        self.calls.append(("show", {"session_id": session_id}))
        return SessionDetailDataV1(
            session_id=session_id,
            source_type="test",
            state="committed",
            created_at=NOW,
            bundle_uri="bulk://recordings/2026/08/19/session-a",
            manifest_digest="sha256:" + "a" * 64,
            attributes={},
            tags=("TEST",),
            held=True,
            hold_reason="TEST fixture",
            analysis=AnalysisRunDataV1(
                run_id="run-old",
                pipeline_release_id="baseline-v1",
                state="succeeded",
                created_at=NOW,
                started_at=NOW,
                sealed_at=NOW,
                failure=None,
                input_manifest_digest="sha256:" + "a" * 64,
                manifest_uri="bulk://analysis/session-a/run-old/manifest.json",
                manifest_digest="sha256:" + "b" * 64,
                is_current=True,
                jobs=(),
                products=(),
            ),
        )

    def session_paths(self, session_id: str) -> SessionPathsDataV1:
        self.calls.append(("paths", {"session_id": session_id}))
        return SessionPathsDataV1(
            session_id=session_id,
            paths=(
                PathItemDataV1(
                    role="recording_bundle",
                    logical_uri="bulk://recordings/2026/08/19/session-a",
                    physical_path="/srv/bulk/leo/recordings/2026/08/19/session-a",
                    exists=True,
                ),
            ),
        )

    def reprocess(self, session_id: str, *, dry_run: bool = False) -> ReprocessDataV1:
        self.calls.append(("reprocess", {"session_id": session_id, "dry_run": dry_run}))
        return ReprocessDataV1(
            session_id=session_id,
            run_id="run-new",
            pipeline_release_id="baseline-v1",
            previous_current_run_id="run-old",
            queued_scope_keys=("stream-a",),
            state="dry_run" if dry_run else "queued",
        )

    def cancel_run(self, run_id: str, *, reason: str) -> CancelRunDataV1:
        self.calls.append(("cancel_run", {"run_id": run_id, "reason": reason}))
        return CancelRunDataV1(
            run_id=run_id,
            changed=True,
            reason=reason,
            cancelled_job_count=30,
            succeeded_job_count=0,
            failed_job_count=0,
            product_count=0,
        )

    def jobs(self) -> JobsDataV1:
        self.calls.append(("jobs", {}))
        return JobsDataV1(queued=2, running=1, failed=0, oldest_queued_seconds=4.5)

    def pin(self, session_id: str, *, reason: str) -> HoldDataV1:
        self.calls.append(("pin", {"session_id": session_id, "reason": reason}))
        return HoldDataV1(session_id=session_id, held=True, changed=True, reason=reason)

    def unpin(self, session_id: str) -> HoldDataV1:
        self.calls.append(("unpin", {"session_id": session_id}))
        return HoldDataV1(session_id=session_id, held=False, changed=True)

    def import_qnap(
        self, manifest_path: Path, *, copy: bool, tags: tuple[str, ...]
    ) -> ImportDataV1:
        self.calls.append(("import", {"manifest_path": manifest_path, "copy": copy, "tags": tags}))
        return ImportDataV1(
            corpus_id="corpus-v1",
            source_manifest=str(manifest_path),
            local_root="/srv/bulk/leo/test-corpus",
            fixtures=(
                ImportFixtureDataV1(
                    fixture_id="fixture-a",
                    directory="/srv/bulk/leo/test-corpus/fixture-a",
                    status="created",
                    session_id="fixture-a",
                    bundle_uri="bulk://recordings/2026/08/19/fixture-a",
                ),
            ),
        )

    def retention_status(self) -> RetentionDataV1:
        self.calls.append(("retention_status", {}))
        return _retention(dry_run=True)

    def retention_run(self, *, dry_run: bool) -> RetentionDataV1:
        self.calls.append(("retention_run", {"dry_run": dry_run}))
        return _retention(dry_run=dry_run)

    def reconcile(self) -> ReconcileDataV1:
        self.calls.append(("reconcile", {}))
        return ReconcileDataV1(
            restored_purges=(),
            discarded_purges=(),
            registered_sessions=("session-a",),
            existing_sessions=(),
            queued_run_ids=("run-new",),
            issues=(),
        )

    def worker(self, **kwargs) -> WorkerDataV1:
        self.calls.append(("worker", kwargs))
        return WorkerDataV1(
            worker_id=kwargs["worker_id"],
            stopped_reason="idle",
            claimed_count=0,
            succeeded_count=0,
            failed_count=0,
        )


def _retention(*, dry_run: bool) -> RetentionDataV1:
    return RetentionDataV1(
        dry_run=dry_run,
        total_bytes=1000,
        used_bytes=720,
        used_fraction=0.72,
        high_watermark=0.70,
        low_watermark=0.65,
        warning_watermark=0.75,
        admission_stop_watermark=0.80,
        should_run=True,
        warning=False,
        admission_allowed_after_plan=True,
        blocked=False,
        selected_ids=("session:session-a",),
        selected_bytes=100,
        predicted_used_bytes=620,
        target_used_bytes=650,
    )


def _app(backend: FakeProcessBackend):
    return create_cli(cast(BackendFactory, lambda: backend))


def _json(output: str) -> dict[str, Any]:
    return json.loads(output)


def test_search_human_and_json_share_typed_values_and_filters() -> None:
    backend = FakeProcessBackend()
    app = _app(backend)
    human = runner.invoke(app, ["process", "search", "--test", "--held"])
    machine = runner.invoke(app, ["process", "search", "--test", "--held", "--json"])

    assert human.exit_code == ExitCode.OK
    assert "session-a" in human.stdout
    payload = _json(machine.stdout)["payload"]
    assert payload["kind"] == "session_search"
    assert payload["sessions"][0]["session_id"] == "session-a"
    assert backend.calls[-1][1]["source_type"] == "test"
    assert backend.calls[-1][1]["tag"] == "TEST"
    assert backend.calls[-1][1]["held"] is True


def test_all_processing_data_commands_route_to_one_typed_backend() -> None:
    backend = FakeProcessBackend()
    app = _app(backend)
    commands = (
        (["process", "show", "session-a", "--json"], "session_detail"),
        (["process", "paths", "session-a", "--json"], "session_paths"),
        (["process", "reprocess", "session-a", "--json"], "reprocess"),
        (
            [
                "process",
                "cancel-run",
                "run-new",
                "--reason",
                "operator request",
                "--yes",
                "--json",
            ],
            "cancel_analysis_run",
        ),
        (["process", "jobs", "--json"], "jobs"),
        (["process", "pin", "session-a", "--reason", "keep", "--json"], "hold"),
        (["process", "unpin", "session-a", "--json"], "hold"),
        (["process", "retention-status", "--json"], "retention"),
        (["process", "retention-run", "--dry-run", "--json"], "retention"),
        (["process", "reconcile", "--json"], "reconcile"),
        (
            [
                "process",
                "import-qnap",
                "/mnt/qnap01/corpus.json",
                "--copy",
                "--tag",
                "TEST",
                "--json",
            ],
            "qnap_import",
        ),
        (
            ["process", "worker", "--worker-id", "worker-a", "--once", "--json"],
            "worker",
        ),
    )

    for arguments, expected_kind in commands:
        result = runner.invoke(app, arguments)
        assert result.exit_code == ExitCode.OK, result.stdout
        assert _json(result.stdout)["payload"]["kind"] == expected_kind


def test_unversioned_reprocess_dry_run_is_rejected_before_backend_mutation() -> None:
    backend = FakeProcessBackend()
    result = runner.invoke(
        _app(backend), ["process", "reprocess", "session-a", "--dry-run", "--json"]
    )

    assert result.exit_code == ExitCode.INVALID_CONFIGURATION
    payload = _json(result.stdout)
    assert payload["message"] == (
        "--dry-run and --wait require an exact --release; no run was created"
    )
    assert payload["payload"] is None
    assert backend.calls == []


def test_destructive_retention_requires_confirmation_before_backend_call() -> None:
    backend = FakeProcessBackend()
    app = _app(backend)

    refused = runner.invoke(app, ["process", "retention-run", "--execute", "--json"])
    accepted = runner.invoke(
        app,
        ["process", "retention-run", "--execute", "--yes", "--json"],
    )

    assert refused.exit_code == ExitCode.CONFIRMATION_REQUIRED
    assert _json(refused.stdout)["payload"] is None
    assert accepted.exit_code == ExitCode.OK
    assert backend.calls == [("retention_run", {"dry_run": False})]


def test_cancel_run_requires_confirmation_before_backend_call() -> None:
    backend = FakeProcessBackend()
    result = runner.invoke(
        _app(backend),
        [
            "process",
            "cancel-run",
            "run-new",
            "--reason",
            "operator request",
            "--json",
        ],
    )

    assert result.exit_code == ExitCode.CONFIRMATION_REQUIRED
    assert backend.calls == []


def test_worker_cancelled_payload_has_stable_interrupted_exit() -> None:
    class CancelledBackend(FakeProcessBackend):
        def worker(self, **kwargs) -> WorkerDataV1:
            assert isinstance(kwargs["cancel"], Event)
            return WorkerDataV1(
                worker_id=kwargs["worker_id"],
                stopped_reason="cancelled",
                claimed_count=0,
                succeeded_count=0,
                failed_count=0,
            )

    result = runner.invoke(
        _app(CancelledBackend()),
        ["process", "worker", "--worker-id", "worker-a", "--json"],
    )

    assert result.exit_code == ExitCode.INTERRUPTED
    assert _json(result.stdout)["exit_code"] == ExitCode.INTERRUPTED
