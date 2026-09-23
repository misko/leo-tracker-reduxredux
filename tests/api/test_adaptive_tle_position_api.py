from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.adaptive_tle_position import adaptive_tle_position_router
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore, AdaptiveTlePositionStoreV2
from tests.contracts.test_adaptive_tle_position import document, document_v2


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


def test_v2_api_is_additive_and_does_not_replace_v1_route(tmp_path):
    image = b"\x89PNG\r\n\x1a\nmap"
    writer = AdaptiveTlePositionStoreV2(tmp_path, read_only=False)
    manifest = writer.publish(document_v2(), image)
    app = FastAPI()
    app.include_router(adaptive_tle_position_router(AdaptiveTlePositionStore(tmp_path)))
    app.include_router(
        adaptive_tle_position_router(AdaptiveTlePositionStoreV2(tmp_path), version=2)
    )
    client = TestClient(app)
    url = "/api/v1/scanner/tracking/scan-1/adaptive-tle-position-v2"
    assert client.get(url).json()["manifest"]["document"]["schema_version"] == 2
    assert (
        client.get(url + "/map.png", params={"sha256": manifest.artifacts[0].sha256}).content
        == image
    )
    assert client.get(url.replace("-v2", "")).json()["state"] == "pending"
