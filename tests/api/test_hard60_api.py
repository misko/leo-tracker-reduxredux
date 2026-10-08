from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.regional_position import regional_position_router
from leo.presentation.regional_position import render_regional_position
from leo.storage.regional_position_v2 import Hard60Store
from tests.contracts.test_regional_position_v2 import document


def test_v2_serves_real_hard60_png_and_checks_inventory_and_digest(tmp_path):
    store = Hard60Store(tmp_path, read_only=False)
    doc = document()
    png = render_regional_position(doc, "V16")
    manifest = store.publish(doc, {"V16": png})
    app = FastAPI()
    app.include_router(regional_position_router(Hard60Store(tmp_path), version=2))
    client = TestClient(app)
    base = "/api/v1/scanner/tracking/scan-1/regional-position-v2"
    assert (
        client.get(base).json()["manifest"]["document"]["configuration"]["protocol"]
        == "sacramento-hard60-v1"
    )
    params = {"sha256": manifest.artifacts[0].sha256}
    response = client.get(base + "/V16.png", params=params)
    assert response.status_code == 200 and response.content == png
    assert response.headers["content-type"] == "image/png"
    assert client.get(base + "/T1AT.png", params=params).status_code == 404
    assert client.get(base + "/V16.png", params={"sha256": "sha256:" + "0" * 64}).status_code == 409
    assert client.post(base + "/V16.png", params=params).status_code == 405
