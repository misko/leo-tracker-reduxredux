from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.position_methods import position_methods_router
from leo.storage.position_methods import PositionMethodsStore
from tests.storage.test_position_methods_store import document


def test_position_methods_api_requires_and_verifies_artifact_digest(tmp_path):
    writer = PositionMethodsStore(tmp_path, read_only=False)
    images = {
        method: b"\x89PNG\r\n\x1a\n" + method.encode()
        for method in ("expanded-doppler", "orbit-corrected", "identity-mixture")
    }
    manifest = writer.publish(document(), images)
    app = FastAPI()
    app.include_router(position_methods_router(PositionMethodsStore(tmp_path)))
    client = TestClient(app)
    status = client.get("/api/v1/scanner/tracking/scan-one/position-methods")
    assert status.status_code == 200
    assert status.json()["state"] == "complete"
    digest = manifest.artifacts[0].sha256
    url = "/api/v1/scanner/tracking/scan-one/position-methods/expanded-doppler.png"
    assert client.get(url).status_code == 422
    assert client.get(url, params={"sha256": "sha256:" + "f" * 64}).status_code == 409
    response = client.get(url, params={"sha256": digest})
    assert response.status_code == 200
    assert response.content == images["expanded-doppler"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_absent_position_methods_are_explicitly_pending(tmp_path):
    app = FastAPI()
    app.include_router(position_methods_router(PositionMethodsStore(tmp_path)))
    response = TestClient(app).get("/api/v1/scanner/tracking/scan-missing/position-methods")
    assert response.status_code == 200
    assert response.json() == {
        "schema_version": 1,
        "session_id": "scan-missing",
        "state": "pending",
        "manifest": None,
    }
