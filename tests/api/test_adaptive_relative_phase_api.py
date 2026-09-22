from leo.contracts.digests import sha256_digest
from leo.presentation.adaptive_relative_phase import render_relative_phase
from leo.scanner.adaptive_relative_phase import RelativePhaseArtifactV1, RelativePhaseManifestV1
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from leo.storage.adaptive_relative_phase import RelativePhaseStore
from tests.api.test_adaptive_hop_history_api import client_for
from tests.storage.test_adaptive_hop_history import publish_capture


def test_read_only_status_and_hash_bound_pngs(tmp_path, monkeypatch):
    capture = publish_capture(tmp_path, count=2)
    presentation = AdaptiveHopAnalysisPresentationStore(tmp_path)
    client = client_for(tmp_path, adaptive_hop_analysis=presentation)
    route = f"/api/v1/scanner/adaptive-sessions/{capture.session_id}/analysis/relative-phase"
    response = client.get(route)
    assert response.status_code == 200
    pending = response.json()
    assert pending["state"] == "pending"
    assert not (tmp_path / "scanner-adaptive-relative-phase-v1").exists()
    images = render_relative_phase([], session_id=capture.session_id, total_visits=2)
    manifest = RelativePhaseManifestV1(
        session_id=capture.session_id,
        input_manifest_sha256=pending["input_manifest_sha256"],
        glrt_binding_sha256=presentation.status(
            capture.session_id, probe_stride_ms=120
        ).binding_sha256,
        binding_sha256=pending["binding_sha256"],
        state="insufficient_signal",
        total_visit_count=2,
        selected_visits=(),
        supported_visit_count=0,
        pilot_checked_visit_count=0,
        receiver_geometry_digest=None,
        artifacts=tuple(
            RelativePhaseArtifactV1(name=k, sha256=sha256_digest(v), byte_count=len(v))
            for k, v in images.items()
        ),
    )
    with RelativePhaseStore(tmp_path).job(
        capture.session_id, manifest.binding_sha256, writable=True
    ) as job:
        job.finalize(manifest, images)
    assert client.get(route).json()["state"] == "insufficient_signal"
    assert client.get(route).headers["cache-control"] == "no-store"
    for artifact in manifest.artifacts:
        url = (
            f"{route}/{artifact.name}.png?binding_sha256={manifest.binding_sha256}"
            f"&artifact_sha256={artifact.sha256}"
        )
        response = client.get(url)
        assert response.status_code == 200 and response.content == images[artifact.name]
        assert response.headers["content-type"] == "image/png"
        assert client.head(url).status_code == 200
        assert client.get(url.replace(artifact.sha256, "sha256:" + "0" * 64)).status_code == 409
