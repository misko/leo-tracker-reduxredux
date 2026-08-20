from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from leo.api import create_app
from leo.application import StandardReprocessError, StandardReprocessResultV1
from leo.presentation.fixtures import build_fixture_repository, write_fixture_artifacts


class _Reprocessor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def queue(self, session_id: str) -> StandardReprocessResultV1:
        self.calls.append(session_id)
        if self.fail:
            raise StandardReprocessError("recording already has an active analysis run")
        return StandardReprocessResultV1(
            session_id=session_id,
            run_id=f"reprocess-{'a' * 32}",
            pipeline_release_id="b" * 40,
            previous_current_run_id="old-current",
            queued_job_count=7,
        )


def _client(tmp_path: Path, reprocessor: _Reprocessor) -> TestClient:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    return TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_reprocessor=reprocessor,
        )
    )


def test_reprocess_action_queues_new_run_and_returns_accepted(tmp_path: Path) -> None:
    reprocessor = _Reprocessor()
    response = _client(tmp_path, reprocessor).post("/api/v2/control/recordings/session-a/reprocess")

    assert response.status_code == 202
    assert response.json() == {
        "schema_version": 1,
        "session_id": "session-a",
        "run_id": f"reprocess-{'a' * 32}",
        "pipeline_release_id": "b" * 40,
        "previous_current_run_id": "old-current",
        "queued_job_count": 7,
        "state": "queued",
    }
    assert reprocessor.calls == ["session-a"]


def test_reprocess_action_reports_active_run_conflict_and_rejects_bad_id(tmp_path: Path) -> None:
    reprocessor = _Reprocessor(fail=True)
    client = _client(tmp_path, reprocessor)

    conflict = client.post("/api/v2/control/recordings/session-a/reprocess")
    invalid = client.post("/api/v2/control/recordings/not%2Fa%2Fsession/reprocess")

    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "recording already has an active analysis run"
    assert invalid.status_code in {404, 422}
