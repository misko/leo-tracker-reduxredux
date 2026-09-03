from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.presentation.fixtures import build_fixture_repository
from leo.scanner import (
    PersistentHopAnalysisStatusV1,
    PersistentHopAnalysisStatusV2,
    PersistentHopHistoryItemV1,
    PersistentHopHistoryItemV2,
    PersistentHopHistoryItemV3,
    PersistentHopHistoryPageV1,
    PersistentHopHistoryPageV2,
    PersistentHopHistoryPageV3,
    PersistentHopSessionDetailV1,
    PersistentHopSessionDetailV2,
    compile_persistent_hop_plan_v1,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop_tracking import (
    PersistentHopCandidateRecurrencePageV1,
    PersistentHopTrackingDetailV1,
    PersistentHopTrackingStatusV1,
)


class _HistoryReader:
    def __init__(self, item: PersistentHopHistoryItemV1) -> None:
        self.item = item
        self.calls: list[tuple[int, int]] = []

    def page(self, *, cursor: int, limit: int) -> PersistentHopHistoryPageV1:
        self.calls.append((cursor, limit))
        return PersistentHopHistoryPageV1(
            cursor=cursor,
            limit=limit,
            total=1,
            next_cursor=None,
            items=(self.item,) if cursor == 0 else (),
        )


class _PresentationReader:
    def __init__(self, item: PersistentHopHistoryItemV1) -> None:
        self.item = item
        self.status = PersistentHopAnalysisStatusV1(
            session_id=item.session_id,
            state="pending",
            total_visits=item.visit_count,
            analyzed_visits=0,
            updated_at=item.finalized_at,
        )

    def page_v2(self, *, cursor: int, limit: int) -> PersistentHopHistoryPageV2:
        return PersistentHopHistoryPageV2(
            cursor=cursor,
            limit=limit,
            total=1,
            next_cursor=None,
            items=(PersistentHopHistoryItemV2(capture=self.item, analysis=self.status),),
        )

    def detail(self, session_id: str) -> PersistentHopSessionDetailV1 | None:
        if session_id != self.item.session_id:
            return None
        return PersistentHopSessionDetailV1(capture=self.item, analysis=self.status)

    def artifact(self, session_id: str, artifact: str) -> bytes | None:
        return None


class _FractionalPresentationReader:
    def __init__(self, item: PersistentHopHistoryItemV1) -> None:
        self.item = item
        self.status = PersistentHopAnalysisStatusV2(
            session_id=item.session_id,
            state="pending",
            total_visits=item.visit_count,
            analyzed_visits=0,
            updated_at=item.finalized_at,
        )

    def page_v3(self, *, cursor: int, limit: int) -> PersistentHopHistoryPageV3:
        return PersistentHopHistoryPageV3(
            cursor=cursor,
            limit=limit,
            total=1,
            next_cursor=None,
            items=(PersistentHopHistoryItemV3(capture=self.item, analysis=self.status),),
        )

    def detail_v2(self, session_id: str) -> PersistentHopSessionDetailV2 | None:
        if session_id != self.item.session_id:
            return None
        return PersistentHopSessionDetailV2(capture=self.item, analysis=self.status)

    def artifact(self, session_id: str, artifact: str) -> bytes | None:
        return None


class _TrackingReader:
    def __init__(self, item: PersistentHopHistoryItemV1) -> None:
        self.item = item

    def detail(self, session_id: str) -> PersistentHopTrackingDetailV1 | None:
        if session_id != self.item.session_id:
            return None
        return PersistentHopTrackingDetailV1(
            status=PersistentHopTrackingStatusV1(
                session_id=session_id,
                state="running",
                phase="tle-matching",
                completed_groups=1,
                total_groups=3,
                updated_at=self.item.finalized_at,
            )
        )

    def artifact(self, session_id: str) -> bytes | None:
        return None

    def recurrences(self) -> PersistentHopCandidateRecurrencePageV1:
        return PersistentHopCandidateRecurrencePageV1(items=())


def _history_item() -> PersistentHopHistoryItemV1:
    radio = FakePersistentHopRadio(radio_id="radio-history", serial="serial-history")
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=5_000_000)
    radio.open()
    session = radio.begin_session(plan, session_id="scan-hop-history")
    session.read_visit()
    session.read_visit()
    session.request_cancel()
    receipt = session.finish()
    radio.close()
    captured = datetime(2026, 9, 3, 2, 20, tzinfo=UTC)
    return PersistentHopHistoryItemV1(
        captured_at=captured,
        finalized_at=captured + timedelta(seconds=1),
        session_id=receipt.session_id,
        radio_id=receipt.radio_id,
        sample_rate_hz=plan.sample_rate_hz,
        bandwidth_hz=plan.bandwidth_hz,
        visit_count=len(receipt.visits),
        target_coverage=receipt.target_coverage,
        capture_outcome=receipt.capture_outcome,
        terminal_state=receipt.terminal_status.state,
        terminal_reason=receipt.terminal_status.reason,
        valid_duty_ppm=receipt.valid_duty_ppm,
        continuity_attested=receipt.continuity_attested,
        restoration_status=receipt.restoration.status,
        qualified=receipt.qualified,
    )


def test_persistent_hop_history_api_exposes_capture_evidence_without_legacy_report(
    tmp_path: Path,
) -> None:
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    reader = _HistoryReader(_history_item())
    client = TestClient(
        create_app(
            build_fixture_repository(bulk),
            artifact_root=bulk,
            persistent_hop_sessions=reader,
        )
    )

    response = client.get("/api/v1/scanner/persistent-sessions?cursor=0&limit=20")

    assert response.status_code == 200
    assert reader.calls == [(0, 20)]
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["session_id"] == "scan-hop-history"
    assert item["sample_rate_hz"] == item["bandwidth_hz"] == 5_000_000
    assert item["visit_count"] == 2
    assert [coverage["visit_count"] for coverage in item["target_coverage"]] == [
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
    assert item["terminal_state"] == "cancelled"
    assert item["analysis_state"] == "pending_backpressure"
    assert "report" not in item


def test_persistent_hop_history_api_is_explicitly_unavailable_without_reader(
    tmp_path: Path,
) -> None:
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    client = TestClient(create_app(build_fixture_repository(bulk), artifact_root=bulk))

    response = client.get("/api/v1/scanner/persistent-sessions")

    assert response.status_code == 404
    assert response.json()["detail"] == "persistent-hop session history is not available"


def test_persistent_hop_v2_detail_returns_pending_as_success_without_requesting_artifacts(
    tmp_path: Path,
) -> None:
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    reader = _PresentationReader(_history_item())
    client = TestClient(
        create_app(
            build_fixture_repository(bulk),
            artifact_root=bulk,
            persistent_hop_presentations=reader,
        )
    )

    page = client.get("/api/v2/scanner/persistent-sessions?cursor=0&limit=5")
    detail = client.get("/api/v2/scanner/persistent-sessions/scan-hop-history")
    missing = client.get("/api/v2/scanner/persistent-sessions/scan-hop-history/coverage.png")

    assert page.status_code == 200
    assert page.json()["items"][0]["analysis"]["state"] == "pending"
    assert detail.status_code == 200
    assert detail.json()["product"] is None
    assert missing.status_code == 404


def test_persistent_hop_v3_exposes_fractional_analysis_without_changing_v2(
    tmp_path: Path,
) -> None:
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    item = _history_item()
    legacy = _PresentationReader(item)
    fractional = _FractionalPresentationReader(item)
    client = TestClient(
        create_app(
            build_fixture_repository(bulk),
            artifact_root=bulk,
            persistent_hop_presentations=legacy,
            persistent_hop_presentations_v2=fractional,
        )
    )

    legacy_page = client.get("/api/v2/scanner/persistent-sessions?cursor=0&limit=5")
    current_page = client.get("/api/v3/scanner/persistent-sessions?cursor=0&limit=5")
    detail = client.get("/api/v3/scanner/persistent-sessions/scan-hop-history")
    missing = client.get("/api/v3/scanner/persistent-sessions/scan-hop-history/coverage.png")

    assert legacy_page.status_code == 200
    assert legacy_page.json()["items"][0]["analysis"]["schema_version"] == 1
    assert current_page.status_code == 200
    assert current_page.json()["items"][0]["analysis"] == {
        "schema_version": 2,
        "session_id": "scan-hop-history",
        "analysis_id": "persistent-hop-fractional-glrt64-cfo-v2",
        "state": "pending",
        "total_visits": 2,
        "analyzed_visits": 0,
        "updated_at": item.finalized_at.isoformat().replace("+00:00", "Z"),
        "failure_summary": None,
    }
    assert detail.status_code == 200 and detail.json()["schema_version"] == 2
    assert missing.status_code == 404


def test_persistent_hop_v4_exposes_tracking_progress_and_recurrence(
    tmp_path: Path,
) -> None:
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    tracking = _TrackingReader(_history_item())
    client = TestClient(
        create_app(
            build_fixture_repository(bulk),
            artifact_root=bulk,
            persistent_hop_tracking=tracking,
        )
    )

    detail = client.get("/api/v4/scanner/persistent-sessions/scan-hop-history/tracking")
    missing = client.get("/api/v4/scanner/persistent-sessions/scan-hop-history/trajectory-tle.png")
    unknown = client.get("/api/v4/scanner/persistent-sessions/unknown/tracking")
    recurrence = client.get("/api/v4/scanner/tle-candidate-recurrences")

    assert detail.status_code == 200
    assert detail.json()["status"]["phase"] == "tle-matching"
    assert detail.json()["product"] is None
    assert missing.status_code == 404
    assert unknown.status_code == 404
    assert recurrence.status_code == 200 and recurrence.json()["items"] == []
