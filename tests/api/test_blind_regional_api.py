from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.blind_regional import blind_regional_router
from leo.storage.blind_regional import NAMES, BlindRegionalStore
from tests.storage.test_blind_regional_store import document


def test_blind_api_status_and_digest_bound_png(tmp_path):
    store = BlindRegionalStore(tmp_path, read_only=False)
    images = {name: b"\x89PNG\r\n\x1a\n" + name.encode() for name in NAMES}
    manifest = store.publish(document(), images)
    app = FastAPI()
    app.include_router(blind_regional_router(BlindRegionalStore(tmp_path)))
    client = TestClient(app)
    status = client.get("/api/v1/scanner/tracking/scan-one/blind-regional")
    assert status.status_code == 200 and status.json()["state"] == "complete"
    ref = next(x for x in manifest.artifacts if x.name == "blind-position")
    url = "/api/v1/scanner/tracking/scan-one/blind-regional/blind-position.png"
    assert client.get(url, params={"sha256": ref.sha256}).content == images["blind-position"]
    assert client.get(url, params={"sha256": "sha256:" + "b" * 64}).status_code == 409
