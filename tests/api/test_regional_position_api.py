from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.regional_position import regional_position_router
from leo.presentation.regional_position import render_regional_position
from leo.storage.regional_position import RegionalPositionStore
from tests.contracts.test_regional_position_products import document

BASE = "/api/v1/scanner/tracking/scan-1/regional-position-v1"


def test_serves_two_real_verified_pngs_and_rejects_stale_digest(tmp_path):
    store = RegionalPositionStore(tmp_path, read_only=False)
    doc = document()
    images = {method: render_regional_position(doc, method) for method in ("T1AT", "V16")}
    manifest = store.publish(doc, images)
    app = FastAPI()
    app.include_router(regional_position_router(RegionalPositionStore(tmp_path)))
    client = TestClient(app)
    assert client.get(BASE).json()["manifest"]["document"]["methods"][1]["name"] == "V16"
    for artifact in manifest.artifacts:
        url = BASE + f"/{artifact.name}.png"
        response = client.get(url, params={"sha256": artifact.sha256})
        assert response.status_code == 200
        assert response.content == images[artifact.name]
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert client.get(url, params={"sha256": "sha256:" + "0" * 64}).status_code == 409
        assert client.post(url).status_code == 405
    (tmp_path / store.namespace / "scan-1" / "V16.png").write_bytes(b"corrupted")
    assert (
        client.get(BASE + "/V16.png", params={"sha256": manifest.artifacts[1].sha256}).status_code
        == 409
    )


def test_pending_and_invalid_routes(tmp_path):
    app = FastAPI()
    app.include_router(regional_position_router(RegionalPositionStore(tmp_path)))
    client = TestClient(app)
    assert client.get(BASE).json()["state"] == "pending"
    params = {"sha256": "sha256:" + "0" * 64}
    assert client.get(BASE + "/T1AT.png", params=params).status_code == 404
    assert client.get(BASE + "/other.png", params=params).status_code == 422
    assert client.get(BASE + "/T1AT.png").status_code == 422
