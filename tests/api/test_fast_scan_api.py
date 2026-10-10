from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.presentation.fixtures import build_fixture_repository
from leo.storage.fast_scan import FastScanStore


def test_fast_scan_publications_are_readable_and_bounded(tmp_path):
    store = FastScanStore(tmp_path)
    store.publish("run", {"run_id": "run", "points": [{"channel": 1}]})
    client = TestClient(
        create_app(build_fixture_repository(tmp_path), artifact_root=tmp_path, fast_scans=store)
    )
    assert client.get("/api/v1/fast-scans").json() == {"items": [{"run_id": "run"}]}
    assert client.get("/api/v1/fast-scans/run").json()["points"] == [{"channel": 1}]
    assert client.get("/api/v1/fast-scans/missing").status_code == 404
    assert client.get("/api/v1/fast-scans?limit=101").status_code == 422
    store.update_automatic("capture", state="tracking", session_id="fast-session")
    assert client.get("/api/v1/fast-scans/automatic").json()["items"][0]["state"] == "tracking"
