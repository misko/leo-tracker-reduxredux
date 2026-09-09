import pytest
from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.presentation.fixtures import build_fixture_repository
from leo.storage.adaptive_hop_history import (
    AdaptiveHopGlrtPresentationStore,
    AdaptiveHopPresentationStore,
)
from leo.storage.scanner_glrt import ScannerGlrtStore
from tests.scanner.adaptive_glrt_publication_fixtures import publication_fixture
from tests.storage.test_adaptive_hop_history import publish_capture


def client_for(root, **kwargs):
    return TestClient(create_app(build_fixture_repository(root), artifact_root=root, **kwargs))


def test_additive_history_detail_glrt_and_head_without_legacy_aliasing(tmp_path):
    capture = publish_capture(tmp_path, count=30, mode="shadow")
    history = AdaptiveHopPresentationStore(tmp_path)
    client = client_for(
        tmp_path,
        adaptive_hop_sessions=history,
        adaptive_scanner_glrt=AdaptiveHopGlrtPresentationStore(tmp_path),
    )
    base = "/api/v1/scanner/adaptive-sessions"
    url = f"{base}/{capture.session_id}"
    assert client.get(base).json() == history.page(cursor=0, limit=20).model_dump(mode="json")
    assert client.get(url).json() == history.detail(capture.session_id).model_dump(mode="json")
    assert client.get(url + "/glrt").status_code == 404
    publication = publication_fixture(capture.manifest.receipt, capture.manifest_sha256)
    ScannerGlrtStore(tmp_path).publish(publication)
    assert client.get(url + "/glrt").json() == publication.model_dump(mode="json")
    for route in (base, url, url + "/glrt"):
        assert client.head(route).status_code == 200 and client.head(route).content == b""
        assert client.post(route).status_code == 405
    assert client.get(base + "/missing").status_code == 404
    assert client.get(base + "/bad%20id").status_code == 422
    assert client.get(base + "?limit=21").status_code == 422
    assert client.get(base + "?cursor=-1").status_code == 422
    assert (
        client.get(url.replace("adaptive-sessions", "persistent-sessions") + "/glrt").status_code
        == 404
    )


@pytest.mark.parametrize("suffix", ["", "/test", "/test/glrt"])
def test_missing_and_broken_adapters_are_distinct_sanitized_errors(tmp_path, suffix):
    base = "/api/v1/scanner/adaptive-sessions" + suffix
    assert client_for(tmp_path).get(base).status_code == 404

    class Broken:
        def page(self, **kwargs):
            raise ValueError("private storage path")

        def detail(self, session_id):
            raise ValueError("private storage path")

    response = client_for(
        tmp_path, adaptive_hop_sessions=Broken(), adaptive_scanner_glrt=Broken()
    ).get(base)
    assert response.status_code == 409
    assert "private storage" not in response.text


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_full_300_second_actual_visit_metadata_inventory(
    tmp_path, monkeypatch, record_property, rate, mode
):
    """Full source metadata only: no IQ, network acquisition or ARM load qualification."""
    from time import perf_counter

    from leo.contracts.recording import CompressionSettingsV1
    from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopPolicyV1
    from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1
    from leo.storage.adaptive_hop import (
        AdaptiveHopIqManifestV1,
        AdaptiveHopIqStore,
        PublishedAdaptiveHopIqSession,
    )
    from tests.scanner.adaptive_hop_fixtures import receipt_fixture, timing_fixture

    receipt = receipt_fixture(
        complete=True,
        plan=AdaptiveHopPlanV1(
            geometry=compile_persistent_hop_plan_v1(sample_rate_hz=rate, transition_guard_us=1000),
            policy=AdaptiveHopPolicyV1(mode=mode, generation=71),
        ),
    )
    sample_count = receipt.plan.geometry.valid_visit_samples
    digest = "sha256:" + "d" * 64
    chunks = []
    for first in range(0, receipt.complete_visit_count, 8):
        count = min(8, receipt.complete_visit_count - first)
        chunks.append(
            dict(
                chunk_index=first // 8,
                first_visit_index=first,
                visit_count=count,
                sample_start=first * sample_count,
                sample_count=count * sample_count,
                relative_path=f"iq-block-{first // 8:06d}.ci16.zst",
                uncompressed_bytes=count * sample_count * 8,
                compressed_bytes=1,
                uncompressed_sha256=digest,
                compressed_sha256=digest,
            )
        )
    manifest = AdaptiveHopIqManifestV1(
        session_id=receipt.session_id,
        created_utc_ns=1780000000000000000,
        finalized_utc_ns=1780000300000000000,
        receipt=receipt,
        timing=timing_fixture(receipt),
        chunks=tuple(chunks),
        total_sample_count=receipt.valid_sample_count,
        uncompressed_bytes=receipt.valid_sample_count * 8,
        compressed_bytes=len(chunks),
        uncompressed_sha256=digest,
        compression=CompressionSettingsV1(policy_id="synthetic-metadata-only"),
    )
    session = PublishedAdaptiveHopIqSession(receipt.session_id, manifest, digest)
    monkeypatch.setattr(AdaptiveHopIqStore, "inspect", lambda *args: session)
    monkeypatch.setattr(AdaptiveHopIqStore, "iter_sessions", lambda *args: iter((session,)))
    client = client_for(tmp_path, adaptive_hop_sessions=AdaptiveHopPresentationStore(tmp_path))
    before = perf_counter()
    response = client.get(f"/api/v1/scanner/adaptive-sessions/{receipt.session_id}")
    elapsed = perf_counter() - before
    assert response.status_code == 200
    data = response.json()
    assert 2400 < len(data["visits"]) <= 2500
    assert (
        data["capture"]["started_visits"]
        == data["capture"]["retained_visits"]
        == receipt.complete_visit_count
    )
    assert data["capture"]["capture_qualified"]
    assert data["capture"]["source_span_seconds"] >= 300
    assert all(v["retained"] for v in data["visits"])
    assert [v["target_index"] for v in data["visits"]] == [e.target_index for e in receipt.events]
    assert data["visits"][-1]["valid_end_seconds"] == data["capture"]["source_span_seconds"]
    assert data["source_origin_counter"] == str(2**53 + 17)
    assert client.get("/api/v1/scanner/adaptive-sessions").json()["items"][0] == data["capture"]
    record_property("metadata_only", True)
    record_property("visits", len(data["visits"]))
    record_property("response_bytes", len(response.content))
    record_property("projection_and_ASGI_seconds", elapsed)
