from dataclasses import replace

import pytest

import leo.storage.adaptive_hop_analysis as storage
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from leo.storage.errors import BundleCorruptionError
from tests.presentation.adaptive_overview_fixtures import rendered_fixture
from tests.storage.test_adaptive_hop_analysis import directory, fixture


def publish(monkeypatch, root):
    binding, products = fixture(monkeypatch)
    store = AdaptiveHopAnalysisStore(root)
    with store.job(binding, writable=True) as job:
        for product in products:
            job.write_visit(product)
        job.finalize_metrics()
    return store, binding, products


def test_snapshot_is_metadata_only_and_never_claims_liveness(monkeypatch, tmp_path):
    store, binding, products = publish(monkeypatch, tmp_path)
    with store.job(binding, writable=True) as job:
        monkeypatch.setattr(
            job, "_read_visit", lambda _: pytest.fail("status must not decode metrics")
        )
        status = job.status()
        assert status.state == "metrics_complete" and status.checkpoint_visits == 2
        assert (
            status.progress_basis == "sealed_metrics_manifest"
            and status.worker_activity == "not_observed"
        )
    store.close()


def test_atomic_overview_publishing_streamed_metrics_and_idempotence(monkeypatch, tmp_path):
    store, binding, products = publish(monkeypatch, tmp_path)
    rendered = rendered_fixture()
    with store.job(binding, writable=True) as job:
        assert tuple(job.published_visits()) == products
        manifest = job.publish_overview(rendered)
        assert job.publish_overview(rendered) == manifest
        status = job.status()
        assert status.state == "figures_ready" and status.overview == manifest
        for artifact in manifest.artifacts:
            assert (
                job.read_artifact(artifact.name, expected_sha256=artifact.sha256)
                == rendered.artifacts[artifact.name]
            )
        with pytest.raises(BundleCorruptionError):
            job.publish_overview(replace(rendered, association_count=1))
    with store.job(binding) as job, pytest.raises(PermissionError):
        job.publish_overview(rendered)
    store.close()


def test_overview_failure_does_not_hide_metrics_and_retry_reuses_identical_files(
    monkeypatch, tmp_path
):
    store, binding, _ = publish(monkeypatch, tmp_path)
    original = storage._publish

    def interrupted(directory, name, payload, maximum):
        if name == "overview-manifest.v1.json":
            raise OSError("injected publication failure")
        original(directory, name, payload, maximum)

    with store.job(binding, writable=True) as job:
        monkeypatch.setattr(storage, "_publish", interrupted)
        with pytest.raises(OSError, match="injected"):
            job.publish_overview(rendered_fixture())
        assert job.status().state == "metrics_complete"
        monkeypatch.setattr(storage, "_publish", original)
        job.publish_overview(rendered_fixture())
        assert job.status().state == "figures_ready"
    store.close()


@pytest.mark.parametrize("fault", ["bad-png", "missing-png", "extra", "count"])
def test_invalid_overview_is_rejected_before_publication(monkeypatch, tmp_path, fault):
    store, binding, _ = publish(monkeypatch, tmp_path)
    rendered = rendered_fixture()
    artifacts = dict(rendered.artifacts)
    if fault == "bad-png":
        artifacts["coverage"] = b"not-a-png"
    if fault == "missing-png":
        artifacts.pop("coverage")
    if fault == "extra":
        artifacts["../unsafe"] = artifacts["coverage"]
    rendered = replace(
        rendered, artifacts=artifacts, selected_observation_count=5 if fault == "count" else 0
    )
    with store.job(binding, writable=True) as job:
        with pytest.raises(ValueError):
            job.publish_overview(rendered)
        assert job.status().state == "metrics_complete"
    store.close()


@pytest.mark.parametrize("fault", ["digest", "symlink", "corrupt", "missing", "manifest"])
def test_artifact_reads_reject_misbound_or_corrupt_publications(monkeypatch, tmp_path, fault):
    store, binding, _ = publish(monkeypatch, tmp_path)
    with store.job(binding, writable=True) as job:
        manifest = job.publish_overview(rendered_fixture())
    path = directory(tmp_path, binding)
    png = path / "overview-v1-coverage.png"
    if fault == "corrupt":
        data = bytearray(png.read_bytes())
        data[-20] ^= 1
        png.write_bytes(data)
    if fault in ("symlink", "missing"):
        saved = tmp_path / "preserved-png"
        png.rename(saved)
        if fault == "symlink":
            png.symlink_to(saved)
    if fault == "manifest":
        (path / "overview-manifest.v1.json").write_bytes(b"{}")
    expected = "sha256:" + "9" * 64 if fault == "digest" else manifest.artifacts[0].sha256
    with store.job(binding) as job, pytest.raises((OSError, ValueError, BundleCorruptionError)):
        job.read_artifact("coverage", expected_sha256=expected)
    store.close()


def test_partial_file_inventory_is_explicitly_unverified(monkeypatch, tmp_path):
    binding, products = fixture(monkeypatch)
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as job:
        job.write_visit(products[0])
        monkeypatch.setattr(job, "_read_visit", lambda _: pytest.fail("not a decoding endpoint"))
        status = job.status()
        assert status.state == "partial" and status.checkpoint_visits == 1
        assert status.progress_basis == "file_inventory" and status.metrics_manifest_sha256 is None
    store.close()


def test_missing_analysis_adapter_is_readonly_and_independent_of_capture(monkeypatch, tmp_path):
    from tests.storage.test_adaptive_hop_history import publish_capture

    capture = publish_capture(tmp_path, count=2)
    paths = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    presentation = AdaptiveHopAnalysisPresentationStore(tmp_path)
    status = presentation.status(capture.session_id)
    assert status.state == "not_started" and status.total_visits == 1
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == paths
    assert presentation.status("missing") is None
