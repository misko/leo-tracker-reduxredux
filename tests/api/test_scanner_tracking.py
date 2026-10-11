from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import leo.application.scanner_tracking as tracking
from leo.api.scanner_tracking import scanner_tracking_router
from leo.storage.scanner_tracking import ScannerTrackingStore
from tests.application.test_scanner_tracking import service


@pytest.mark.parametrize("channel", [1, 8])
def test_shared_endpoint_serves_partial_trajectory_and_closed_evidence(
    tmp_path, monkeypatch, channel
):
    runner, store = service(tmp_path, monkeypatch, archive_error=True)
    rows = tuple(replace(row, channel=channel) for row in tracking.project_scanner_candidates(None))
    monkeypatch.setattr(tracking, "project_scanner_candidates", lambda _: rows)
    runner.run("scan-test")
    app = FastAPI()
    app.include_router(scanner_tracking_router(ScannerTrackingStore(tmp_path)))
    client = TestClient(app)
    product = client.get("/api/v1/scanner/tracking/scan-test").json()["product"]
    assert product["schema_version"] == 16
    assert {t["channel"] for t in product["tracklets"]} == {channel}
    assert product["review_limit"] == runner.review_limit
    assert product["review_selection_policy"] == "longest-support-observations-identity-v1"
    assert product["control_comparison_policy"] == "polynomial-and-wrong-time-diagnostic-only-v1"
    assert (
        client.get("/api/v1/scanner/tracking/scan-test").json()["product"]["tle_state"]
        == "unavailable"
    )
    assert (
        client.get("/api/v1/scanner/tracking/scan-test/trajectory.png").headers["content-type"]
        == "image/png"
    )
    assert product["position_diagnostic"]["position_fix_claimed"] is False
    assert client.get(
        "/api/v1/scanner/tracking/scan-test/cfo-track-overlay.png"
    ).content.startswith(b"\x89PNG\r\n\x1a\n")
    assert (
        client.get("/api/v1/scanner/tracking/scan-test/position-diagnostic.png").headers[
            "content-type"
        ]
        == "image/png"
    )
    assert client.get("/api/v1/scanner/tracking/scan-test/trajectory-tle.png").status_code == 404
    assert client.get("/api/v1/scanner/tracking/scan-test/unknown.png").status_code == 422
    assert client.get("/api/v1/scanner/tracking/scan-test/tle-review-128.png").status_code == 404
    assert client.get("/api/v1/scanner/tracking/scan-test/tle-review-129.png").status_code == 422
    assert client.get("/api/v1/scanner/tracking/another-scan").json()["state"] == "pending"
