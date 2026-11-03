"""Discovery reuse cannot hide changed bytes, fresh consumption checks or retries."""

import os

import pytest

from leo.storage import fast_graph_position as module


def fixture(tmp_path):
    folder = tmp_path / "fast-scan-tracking-inputs"
    folder.mkdir()
    path = folder / "scan.json"
    path.write_text("original")
    return module.FastGraphPositionStore(tmp_path), path


def test_stable_discovery_reuses_digest_but_consumption_rehashes(tmp_path, monkeypatch):
    store, path = fixture(tmp_path)
    original, calls = module.sha, []

    def counted(source):
        calls.append(source)
        return original(source)

    monkeypatch.setattr(module, "sha", counted)
    job = next(store.inputs())
    assert next(store.inputs()) == job
    assert calls == [path]
    store.verify_input(job)
    assert calls == [path, path]


@pytest.mark.parametrize("replacement", [False, True])
def test_same_size_and_restored_mtime_does_not_hide_change(tmp_path, replacement):
    store, path = fixture(tmp_path)
    job = next(store.inputs())
    before = path.stat()
    if replacement:
        other = path.with_suffix(".new")
        other.write_text("modified")
        os.utime(other, ns=(before.st_atime_ns, before.st_mtime_ns))
        other.replace(path)
    else:
        path.write_text("modified")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    changed = next(store.inputs())
    assert changed["job_id"] != job["job_id"]
    assert changed["input_sha256"] == module.sha(path)
    with pytest.raises(ValueError, match="identity changed"):
        store.verify_input(job)


def test_consumption_rejects_bytes_even_if_metadata_cache_is_stale(tmp_path, monkeypatch):
    store, path = fixture(tmp_path)
    identity = module._discovery_file_identity(path)
    monkeypatch.setattr(module, "_discovery_file_identity", lambda _: identity)
    job = next(store.inputs())
    path.write_text("modified")
    assert next(store.inputs()) == job
    with pytest.raises(ValueError, match="identity changed"):
        store.verify_input(job)


def test_concurrent_change_is_not_cached(tmp_path, monkeypatch):
    store, path = fixture(tmp_path)
    original = module.sha

    def changed(source):
        digest = original(source)
        source.write_text("changed during read")
        return digest

    monkeypatch.setattr(module, "sha", changed)
    with pytest.raises(ValueError, match="during discovery"):
        next(store.inputs())
    assert not store._discovery_digests
    monkeypatch.setattr(module, "sha", original)
    assert next(store.inputs())["input_sha256"] == original(path)


def test_deleted_inputs_are_not_emitted_and_status_is_not_cached(tmp_path):
    store, path = fixture(tmp_path)
    job = next(store.inputs())
    for state in ("complete", "running", "failed", "unavailable"):
        store.update(job, state=state)
        assert next(store.inputs()) == job
        assert store.status(job["job_id"])["state"] == state
    path.unlink()
    assert list(store.inputs()) == []


def test_cache_is_bounded_without_changing_job_identity(tmp_path, monkeypatch):
    store, path = fixture(tmp_path)
    monkeypatch.setattr(module, "_DISCOVERY_DIGEST_LIMIT", 2)
    for i in range(3):
        path.with_name(f"scan-{i}.json").write_text(str(i))
    first = list(store.inputs())
    assert len(store._discovery_digests) == 2
    assert list(store.inputs()) == first
    assert len(store._discovery_digests) == 2
