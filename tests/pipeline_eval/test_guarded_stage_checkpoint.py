from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import guarded_cfo_0016_stage as stage
from guarded_stage_checkpoint import Extent, checkpoint, identity, staging_lock, verified_extents, write_checkpoint


def pin(blob):
    return "sha256:" + sha256(blob).hexdigest()


@pytest.fixture
def stopped(tmp_path, monkeypatch):
    source, root = tmp_path / "original", tmp_path / "local"
    root.mkdir()
    extent = Extent(Path("segment/payload"), 8, pin(b"abcdefgh"))
    target = root / extent.relative
    target.parent.mkdir()
    source.write_bytes(b"abcdefgh")
    journal, lock_file = root / "checkpoint.json", tmp_path / "gauss.lock"
    lock_file.touch()
    monkeypatch.setattr(stage, "BLOCK", 3)
    monkeypatch.setattr(stage, "sleep", lambda _: None)

    def interrupted(_, count):
        assert count == 3
        raise InterruptedError("controlled stop")

    with lock_file.open("rb") as lock, pytest.raises(InterruptedError):
        stage.copy_member(source, target, extent.size, extent.sha256, lock,
                          SimpleNamespace(wait_s=0, progress=interrupted), journal=journal)
    assert target.read_bytes() == b"abc"
    return source, root, extent, journal, lock_file


def test_restarted_copy_reads_only_the_signed_missing_suffix(stopped, monkeypatch):
    source, root, extent, journal, lock_file = stopped
    complete, partial = verified_extents(root, [extent], json.loads(journal.read_text()))
    assert not complete and partial.offset == 3
    original_open = Path.open
    source_reads = []

    class Reader:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def read(self, limit):
            start = self.stream.tell()
            payload = self.stream.read(limit)
            source_reads.append((start, len(payload)))
            return payload

    @contextmanager
    def observed(stream):
        with stream:
            yield Reader(stream)

    def open_input(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return observed(stream) if path == source else stream

    monkeypatch.setattr(Path, "open", open_input)
    with lock_file.open("rb") as lock:
        stage.copy_member(source, root / extent.relative, extent.size, extent.sha256, lock,
                          SimpleNamespace(wait_s=0, progress=lambda *_: None), partial=partial, journal=journal)
    assert source_reads == [(3, 3), (6, 2)]
    assert verified_extents(root, [extent], json.loads(journal.read_text())) == ({extent.relative}, None)


def test_restarted_copy_refuses_modified_local_prefix(stopped):
    _, root, extent, journal, _ = stopped
    (root / extent.relative).write_bytes(b"xbc")
    with pytest.raises(ValueError, match="checkpoint prefix changed"):
        verified_extents(root, [extent], json.loads(journal.read_text()))


def test_restarted_copy_refuses_changed_source_before_append(stopped):
    source, root, extent, journal, lock_file = stopped
    _, partial = verified_extents(root, [extent], json.loads(journal.read_text()))
    source.write_bytes(b"abcdXfgh")
    with lock_file.open("rb") as lock, pytest.raises(ValueError, match="source identity changed"):
        stage.copy_member(source, root / extent.relative, extent.size, extent.sha256, lock,
                          SimpleNamespace(wait_s=0, progress=lambda *_: None), partial=partial, journal=journal)
    assert (root / extent.relative).read_bytes() == b"abc"


def test_checkpoint_handles_a_stop_before_the_append(stopped):
    source, root, extent, journal, _ = stopped
    write_checkpoint(journal, checkpoint(extent, identity(source.stat()), [(3, pin(b"abc")), (6, pin(b"abcdef"))]))
    _, earlier = verified_extents(root, [extent], json.loads(journal.read_text()))
    assert earlier.offset == 3
    (root / extent.relative).write_bytes(b"abcdef")
    _, later = verified_extents(root, [extent], json.loads(journal.read_text()))
    assert later.offset == 6
    (root / extent.relative).write_bytes(b"abcd")
    with pytest.raises(ValueError, match="no matching sealed checkpoint"):
        verified_extents(root, [extent], json.loads(journal.read_text()))


def test_two_concurrent_stagers_cannot_hold_the_same_lock(tmp_path):
    path = tmp_path / "stage.lock"
    with staging_lock(path):
        with pytest.raises(RuntimeError, match="exclusive lock"):
            with staging_lock(path):
                pytest.fail("second invocation acquired the active lock")
    with staging_lock(path):
        assert path.is_file()


def test_finished_stage_invocation_verifies_local_files_without_source_copy(tmp_path, monkeypatch):
    recording = tmp_path / "source"
    root = tmp_path / "staged"
    manifest, index, payload = "manifest", "index", "payload"
    files = {}
    for kind in stage.COPY_ORDER:
        data = kind.encode()
        local = root / recording.name / "segment" / kind
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        files[kind] = [(recording / "segment" / kind, len(data), pin(data))]
    extents = {kind: entries[0][1] for kind, entries in files.items()}
    (root / "staging.json").write_text(json.dumps({"inventory": stage.ORIGINAL.inventory,
                                                   "copied_bytes": sum(extents.values())}))
    monkeypatch.setattr(stage, "RECORDING", recording)
    monkeypatch.setattr(stage, "signed_members", lambda: (None, None, files, extents))
    monkeypatch.setattr(stage, "cache_states", lambda _: {})
    monkeypatch.setattr(stage, "copy_member", lambda *args, **kwargs: pytest.fail("completed copy repeated"))
    stage.stage_locked(root, resume=True)
    stage.stage_locked(root, resume=True)
    (root / recording.name / "segment" / index).write_bytes(b"INDEX")
    with pytest.raises(ValueError, match="signed bytes"):
        stage.stage_locked(root, resume=True)
