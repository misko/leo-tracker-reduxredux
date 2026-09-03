from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.presentation.fixtures import build_fixture_repository
from leo.scanner import (
    PersistentHopHistoryItemV1,
    PersistentHopHistoryPageV1,
    compile_persistent_hop_plan_v1,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio


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
