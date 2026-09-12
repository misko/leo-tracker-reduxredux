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
    assert client.get("/api/v1/scanner/tracking/another-scan").json()["state"] == "pending"
