from fastapi.testclient import TestClient

from leo.analysis.starlink.refinement_comparison import comparison_metrics
from leo.api.app import create_app
from leo.presentation.fixtures import build_fixture_repository
from leo.presentation.scanner_refinement import render_scanner_refinement
from leo.storage.scanner_refinement import ScannerRefinementStore
from tests.scanner.refinement_fixtures import comparison_fixture


def test_api_serves_saved_comparison_pngs_evidence_and_honest_pending_state(tmp_path):
    store = ScannerRefinementStore(tmp_path, read_only=False)
    client = TestClient(
        create_app(
            build_fixture_repository(tmp_path),
            artifact_root=tmp_path,
            scanner_refinement=ScannerRefinementStore(tmp_path),
        )
    )
    url = "/api/v1/scanner/refinement-comparisons/scan-one"
    assert client.get(url).json()["state"] == "not_started"
    assert client.get(url + "/shift-recovery.png").status_code == 404
    e = comparison_fixture()
    pngs = render_scanner_refinement(e)
    store.publish(e, comparison_metrics(e.rows), pngs)
    assert client.get(url).json()["state"] == "complete"
    for name, png in pngs.items():
        assert client.get(url + f"/{name}.png").content == png
        assert client.head(url + f"/{name}.png").status_code == 200
    assert client.get(url + "/evidence.json").json() == e.model_dump(mode="json")
    assert client.post(url).status_code == 405
    assert client.get(url + "/not-an-artifact.png").status_code == 422
    assert client.get(url.replace("scan-one", "bad%20id")).status_code == 422
    (tmp_path / "scanner-refinement-comparisons/scan-one/shift-recovery.png").write_bytes(b"bad")
    response = client.get(url + "/shift-recovery.png")
    assert response.status_code == 409
    assert str(tmp_path) not in response.text
