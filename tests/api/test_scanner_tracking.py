from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.scanner_tracking import scanner_tracking_router
from leo.storage.scanner_tracking import ScannerTrackingStore
from tests.application.test_scanner_tracking import service


def test_shared_endpoint_serves_partial_trajectory_and_closed_evidence(tmp_path, monkeypatch):
    runner, store = service(tmp_path, monkeypatch, archive_error=True)
    runner.run("scan-test")
    app = FastAPI()
    app.include_router(scanner_tracking_router(ScannerTrackingStore(tmp_path)))
    client = TestClient(app)
    product = client.get("/api/v1/scanner/tracking/scan-test").json()["product"]
    assert product["schema_version"] == 13
    assert product["review_limit"] == 64
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
    assert client.get("/api/v1/scanner/tracking/scan-test/trajectory-tle.png").status_code == 404
    assert client.get("/api/v1/scanner/tracking/scan-test/unknown.png").status_code == 422
    assert client.get("/api/v1/scanner/tracking/scan-test/tle-review-128.png").status_code == 404
    assert client.get("/api/v1/scanner/tracking/scan-test/tle-review-129.png").status_code == 422
    assert client.get("/api/v1/scanner/tracking/another-scan").json()["state"] == "pending"
