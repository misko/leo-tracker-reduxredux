from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from leo.api import create_app
from leo.application import (
    ResearchReprocessResultV1,
    StandardReprocessError,
    StandardReprocessResultV1,
)
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


class _ResearchReprocessor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def queue(self, session_id: str) -> ResearchReprocessResultV1:
        self.calls.append(session_id)
        return ResearchReprocessResultV1(
            session_id=session_id,
            run_id=f"research-{'c' * 32}",
            pipeline_release_id="b" * 40,
            previous_research_run_id="old-research",
            queued_job_count=8,
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


def test_research_action_and_control_status_are_independent(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    standard = _Reprocessor()
    research = _ResearchReprocessor()
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_reprocessor=standard,
            research_reprocessor=research,
        )
    )

    status = client.get("/api/v2/control/status")
    response = client.post("/api/v2/control/recordings/session-a/research")

    assert status.json() == {
        "schema_version": 2,
        "standard_reprocess_enabled": True,
        "research_reprocess_enabled": True,
    }
    assert response.status_code == 202
    assert response.json() == {
        "schema_version": 1,
        "pipeline_lane": "research",
        "session_id": "session-a",
        "run_id": f"research-{'c' * 32}",
        "pipeline_release_id": "b" * 40,
        "previous_research_run_id": "old-research",
        "queued_job_count": 8,
        "scheduling_priority": "lower_than_standard",
        "state": "queued",
    }
    assert standard.calls == []
    assert research.calls == ["session-a"]
