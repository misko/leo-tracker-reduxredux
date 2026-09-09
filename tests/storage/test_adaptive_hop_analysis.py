import json
import os
from pathlib import Path

import pytest
import zstandard as zstd

import leo.scanner.adaptive_hop_analysis as detector
import leo.storage.adaptive_hop_analysis as storage
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopAnalysisSource,
    analyze_adaptive_hop_visit,
)
from leo.scanner.adaptive_hop_products import AdaptiveHopAnalysisBindingV1
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from tests.scanner.test_adaptive_hop_analysis import Reader
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell


def fixture(monkeypatch, *, rate=2_500_000, mode="adaptive", count=3, stride=10):
    reader = Reader(rate=rate, mode=mode, count=count)
    source = AdaptiveHopAnalysisSource(reader)
    cfg = AdaptiveHopAnalysisConfigurationV1(sample_rate_hz=rate, probe_stride_ms=stride)
    binding = AdaptiveHopAnalysisBindingV1(
        receipt=source.receipt,
        input_manifest_sha256=source.input_manifest_sha256,
        configuration=cfg,
    )
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    products = tuple(
        analyze_adaptive_hop_visit(source, i, configuration=cfg) for i in range(len(source.visits))
    )
    return binding, products


def directory(root, binding):
    return root / "scanner-adaptive-analysis" / binding.session_id / binding.sha256[7:]


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_checkpoint_restart_full_metrics_seal_and_idempotence(monkeypatch, tmp_path, rate, mode):
    binding, products = fixture(monkeypatch, rate=rate, mode=mode)
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as job:
        reference = job.write_visit(products[0])
        assert reference.probe_count == 22 and reference.fractional_candidate_count == 44
        assert reference.passed_fractional_candidate_count == 22
        assert job.completed_visits() == (0,) and job.manifest() is None
        assert job.write_visit(products[0]) == reference
        with pytest.raises(ValueError, match="every complete visit"):
            job.finalize_metrics()
    store.close()
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as job:
        assert job.completed_visits() == (0,)
        job.write_visit(products[1])
        manifest = job.finalize_metrics()
        assert manifest.complete_visit_count == 2 and manifest.binding_sha256 == binding.sha256
        assert job.verify() == manifest == job.finalize_metrics()
        assert job.read_visit(0) == products[0]
    with pytest.raises(RuntimeError, match="closed"):
        job.read_visit(0)
    store.close()
    read_only = AdaptiveHopAnalysisStore(tmp_path, read_only=True)
    with read_only.job(binding) as job:
        assert job.verify() == manifest and job.read_visit(1) == products[1]
        with pytest.raises(PermissionError):
            job.write_visit(products[1])
        with pytest.raises(PermissionError):
            job.finalize_metrics()
    with pytest.raises(PermissionError), read_only.job(binding, writable=True):
        pass
    read_only.close()


def test_readonly_missing_and_qnap_or_symlink_root_create_nothing(monkeypatch, tmp_path):
    binding, _ = fixture(monkeypatch)
    store = AdaptiveHopAnalysisStore(tmp_path, read_only=True)
    with pytest.raises(BundleNotFoundError), store.job(binding):
        pass
    assert list(tmp_path.iterdir()) == []
    store.close()
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        AdaptiveHopAnalysisStore(alias)
    with pytest.raises(ValueError):
        AdaptiveHopAnalysisStore(Path("/mnt/qnap01/forbidden"))


def test_worker_lock_prevents_competing_writer_but_allows_reader(monkeypatch, tmp_path):
    binding, products = fixture(monkeypatch)
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as first:
        first.write_visit(products[0])
        with pytest.raises(BlockingIOError), store.job(binding, writable=True):
            pass
        with store.job(binding) as reader:
            assert reader.completed_visits() == (0,)
    with store.job(binding, writable=True) as resumed:
        assert resumed.read_visit(0) == products[0]
    store.close()


@pytest.mark.parametrize(
    "fault",
    [
        "binding",
        "visit",
        "manifest",
        "trailing",
        "expansion",
        "symlink",
        "hardlink",
        "filename",
        "missing",
        "valid_tamper",
    ],
)
def test_corruption_never_becomes_complete(monkeypatch, tmp_path, fault):
    binding, products = fixture(monkeypatch)
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as job:
        for product in products:
            job.write_visit(product)
        job.finalize_metrics()
    path = directory(tmp_path, binding)
    visit = path / "visit-000000.v1.json.zst"
    if fault in ("binding", "manifest"):
        (
            path / ("binding.v1.json" if fault == "binding" else "metrics-manifest.v1.json")
        ).write_bytes(b"{}")
    elif fault == "visit":
        visit.write_bytes(b"bad")
    elif fault == "trailing":
        visit.write_bytes(visit.read_bytes() + b"unreferenced")
    elif fault == "expansion":
        visit.write_bytes(zstd.ZstdCompressor().compress(b"a" * (storage._MAX_VISIT + 1)))
    elif fault in ("symlink", "hardlink", "missing"):
        moved = tmp_path / "preserved-original"
        visit.rename(moved)
        if fault == "symlink":
            visit.symlink_to(moved)
        if fault == "hardlink":
            os.link(moved, visit)
    elif fault == "filename":
        (path / "visit-001000.v1.json.zst").write_bytes(visit.read_bytes())
    else:
        document = products[0].model_dump(mode="json")
        document["probes"][0]["candidates"][0]["acquired_cfo_hz"] += 1
        sealed = {"document": document, "sha256": sha256_digest(canonical_json_bytes(document))}
        visit.write_bytes(zstd.ZstdCompressor().compress(canonical_json_bytes(sealed)))
    with pytest.raises((BundleCorruptionError, ValueError, OSError)), store.job(binding) as job:
        job.verify()
    store.close()


def test_checkpoint_cannot_change_configuration_or_science(monkeypatch, tmp_path):
    binding, products = fixture(monkeypatch)
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as job:
        job.write_visit(products[0])
        payload = products[0].model_dump()
        payload["probes"][0]["candidates"][0]["acquired_cfo_hz"] += 1
        with pytest.raises(BundleCorruptionError, match="overwritten"):
            job.write_visit(type(products[0]).model_validate(payload))
        payload = products[0].model_dump()
        payload["input_manifest_sha256"] = "sha256:" + "2" * 64
        with pytest.raises(BundleCorruptionError, match="source manifest"):
            job.write_visit(type(products[0]).model_validate(payload))
        assert job.read_visit(0) == products[0]
    alternate, other = fixture(monkeypatch, stride=120)
    assert alternate.sha256 != binding.sha256
    with store.job(alternate, writable=True) as job:
        assert job.completed_visits() == ()
        with pytest.raises(BundleCorruptionError, match="configuration"):
            job.write_visit(products[0])
        job.write_visit(other[0])
    store.close()


def test_failed_partial_is_retained_but_never_counted_and_retry_resumes(monkeypatch, tmp_path):
    binding, products = fixture(monkeypatch)
    store = AdaptiveHopAnalysisStore(tmp_path)
    publish = storage._publish
    with store.job(binding, writable=True) as job:

        def failed(directory, name, payload, maximum):
            (directory.io_root / f".{name}.failed.partial").write_bytes(payload[:13])
            raise OSError("injected publication failure")

        monkeypatch.setattr(storage, "_publish", failed)
        with pytest.raises(OSError, match="injected"):
            job.write_visit(products[0])
        assert job.completed_visits() == () and job.manifest() is None
        monkeypatch.setattr(storage, "_publish", publish)
    with store.job(binding, writable=True) as job:
        job.write_visit(products[0])
        assert job.completed_visits() == (0,)
    assert len(list(directory(tmp_path, binding).glob("*.partial"))) == 1
    store.close()


def test_empty_cancelled_source_has_complete_empty_metrics(monkeypatch, tmp_path):
    binding, products = fixture(monkeypatch, count=0)
    assert products == ()
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as job:
        manifest = job.finalize_metrics()
        assert manifest.visits == () and manifest.complete_visit_count == 0
    store.close()


def test_large_integer_epochs_survive_persisted_json(monkeypatch, tmp_path):
    binding, products = fixture(monkeypatch)
    store = AdaptiveHopAnalysisStore(tmp_path)
    with store.job(binding, writable=True) as job:
        job.write_visit(products[0])
    compressed = (directory(tmp_path, binding) / "visit-000000.v1.json.zst").read_bytes()
    document = json.loads(zstd.ZstdDecompressor().decompress(compressed))["document"]
    candidate = document["probes"][0]["candidates"][0]
    assert type(candidate["integer_device_sample_counter"]) is str
    assert int(candidate["integer_device_sample_counter"]) > 2**53
    assert candidate["fractional_epoch_offset_samples"] == -0.25
    store.close()
