from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.regional_position import regional_position_router
from leo.presentation.regional_position import regional_position_figure, render_regional_position
from leo.storage.regional_position_v3 import B7Store
from tests.contracts.test_regional_position_v3 import document


def test_b7_real_png_roundtrip_and_stale_digest_rejection(tmp_path):
    doc = document()
    figure = regional_position_figure(doc, "V16")
    assert "B7 / Hard60" in figure._suptitle.get_text()
    assert "accepted B1" in figure.axes[0].get_title()
    png = render_regional_position(doc, "V16")
    store = B7Store(tmp_path, read_only=False)
    manifest = store.publish(doc, {"V16": png})
    app = FastAPI()
    app.include_router(regional_position_router(B7Store(tmp_path), version=3))
    client = TestClient(app)
    base = "/api/v1/scanner/tracking/scan-1/regional-position-v3"
    assert client.get(base).json()["manifest"]["document"]["schema_version"] == 3
    response = client.get(base + "/V16.png", params={"sha256": manifest.artifacts[0].sha256})
    assert response.status_code == 200 and response.content == png
    assert response.headers["content-type"] == "image/png"
    assert client.get(base + "/V16.png", params={"sha256": "sha256:" + "0" * 64}).status_code == 409
