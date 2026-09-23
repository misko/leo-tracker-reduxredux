from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.adaptive_tle_position import adaptive_tle_position_router
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore
from tests.contracts.test_adaptive_tle_position import document


def test_api_serves_digest_bound_map_and_machine_document(tmp_path):
    image = b"\x89PNG\r\n\x1a\nmap"
    writer = AdaptiveTlePositionStore(tmp_path, read_only=False)
    manifest = writer.publish(document(), image)
    app = FastAPI()
    app.include_router(adaptive_tle_position_router(AdaptiveTlePositionStore(tmp_path)))
    client = TestClient(app)
    url = "/api/v1/scanner/tracking/scan-1/adaptive-tle-position"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["manifest"]["document"]["position_fix_claimed"] is False
    map_url = url + "/map.png"
    assert client.get(map_url, params={"sha256": manifest.artifacts[0].sha256}).content == image
    assert client.get(map_url, params={"sha256": "sha256:" + "b" * 64}).status_code == 409
