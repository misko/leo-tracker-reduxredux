from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.presentation.fixtures import build_fixture_repository
from leo.storage.scanner_glrt import ScannerGlrtPresentationStore, ScannerGlrtStore
from tests.scanner.glrt_publication_fixtures import make_capture, make_publication


def test_api_serves_exact_uint64_and_unqualified_evidence_independently_of_dense_analysis(tmp_path):
    iq, capture = make_capture(tmp_path)
    publication = make_publication(capture)
    store = ScannerGlrtStore(tmp_path)
    store.publish(publication)
    client = TestClient(
        create_app(
            build_fixture_repository(tmp_path),
            artifact_root=tmp_path,
            scanner_glrt=ScannerGlrtPresentationStore(
                iq, ScannerGlrtStore.open_read_only(tmp_path)
            ),
        )
    )
    url = f"/api/v1/scanner/persistent-sessions/{capture.session_id}/glrt"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == publication.model_dump(mode="json")
    assert response.json()["evidence"]["results"][0]["epoch_sample_counter"] == str(
        publication.evidence.results[0].epoch_sample_counter
    )
    assert not response.json()["evidence"]["classification_complete"]
    assert client.head(url).status_code == 200 and client.head(url).content == b""
    assert client.get("/api/v1/scanner/persistent-sessions/missing/glrt").status_code == 404
    assert client.get("/api/v1/scanner/persistent-sessions/bad%20id/glrt").status_code == 422
    assert client.post(url).status_code == 405


def test_missing_or_failed_evidence_never_becomes_an_empty_success(tmp_path):
    client = TestClient(create_app(build_fixture_repository(tmp_path), artifact_root=tmp_path))
    url = "/api/v1/scanner/persistent-sessions/test/glrt"
    assert client.get(url).status_code == 404

    class Broken:
        def detail(self, session_id):
            raise ValueError("private path and corrupt source binding")

    client = TestClient(
        create_app(
            build_fixture_repository(tmp_path),
            artifact_root=tmp_path,
            scanner_glrt=Broken(),
        )
    )
    response = client.get(url)
    assert response.status_code == 409
    assert "private path" not in response.text
