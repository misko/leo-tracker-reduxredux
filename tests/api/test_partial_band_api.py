from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.partial_band import partial_band_router
from leo.contracts.partial_band import PartialBandStatusV1

SID = "scan-fw-0123456789abcdef"
DIGEST = "sha256:" + "a" * 64


def test_read_only_status_and_digest_bound_artifacts():
    calls = []
    reader = SimpleNamespace(
        status=lambda sid, digest: PartialBandStatusV1(
            session_id=sid, binding_sha256=digest, state="not_started", completed_visits=0
        ),
        artifact=lambda *args: calls.append(args) or b"\x89PNG\r\n\x1a\nfixture",
    )
    app = FastAPI()
    app.include_router(partial_band_router(reader))
    client = TestClient(app)
    path = f"/api/v1/scanner/adaptive-sessions/{SID}/partial-band"
    assert (
        client.get(path, params={"input_manifest_sha256": DIGEST}).json()["state"] == "not_started"
    )
    response = client.get(
        path + "/coverage.png", params={"input_manifest_sha256": DIGEST, "artifact_sha256": DIGEST}
    )
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert calls == [(SID, DIGEST, "coverage.png", DIGEST)]
    assert client.post(path).status_code == 405
    assert (
        client.get(
            path + "/unknown.png",
            params={"input_manifest_sha256": DIGEST, "artifact_sha256": DIGEST},
        ).status_code
        == 422
    )
    assert client.get(path, params={"input_manifest_sha256": "bad"}).status_code == 422


def test_corrupt_evidence_is_409_not_missing():
    def fail(*args):
        raise ValueError("corruption")

    app = FastAPI()
    app.include_router(partial_band_router(SimpleNamespace(status=fail)))
    response = TestClient(app).get(
        f"/api/v1/scanner/adaptive-sessions/{SID}/partial-band",
        params={"input_manifest_sha256": DIGEST},
    )
    assert response.status_code == 409
