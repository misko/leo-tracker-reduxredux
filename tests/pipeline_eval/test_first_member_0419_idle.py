from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import first_member_0419_idle as idle
from guarded_cfo_0016_stage import copy_member


def pin(body):
    return "sha256:" + sha256(body).hexdigest()


def test_original_metadata_uses_two_admissions_and_exact_bytes(tmp_path):
    source = tmp_path / "source"
    stage = tmp_path / "stage"
    source.mkdir()
    stage.mkdir()
    index = b"signed index"
    member = dict(index_relative_path="windows-000000.jsonl",
                  index_sha256=pin(index), index_bytes=len(index))
    manifest = json.dumps({"chunks": [member]}).encode()
    (source / "manifest.json").write_bytes(manifest)
    (source / member["index_relative_path"]).write_bytes(index)
    admitted = []

    @contextmanager
    def slot(lock):
        admitted.append(lock)
        yield

    lock = object()
    assert idle.stage_metadata(source, stage, pin(manifest), member, SimpleNamespace(slot=slot), lock) == (
        len(manifest) + len(index))
    assert admitted == [lock, lock]
    assert (stage / "manifest.json").read_bytes() == manifest
    assert (stage / member["index_relative_path"]).read_bytes() == index


def test_standard_verification_stops_at_the_first_member(monkeypatch, tmp_path):
    waves = np.arange(8, dtype="<i2").reshape((2, 2, 2))
    visits = [SimpleNamespace(index=SimpleNamespace(sequence=idx), samples=waves) for idx in range(2)]

    def windows(*, stop_sequence):
        assert stop_sequence == 2
        yield from visits

    reader = SimpleNamespace(manifest_sha256="signed manifest", windows=windows)
    monkeypatch.setattr(idle, "ShortWindowReader", lambda _: reader)
    chunk = dict(window_count=2, uncompressed_bytes=waves.nbytes * 2,
                 uncompressed_sha256=pin(waves.tobytes() * 2))
    assert idle.verified_local(tmp_path, reader.manifest_sha256, chunk)["visits"] == 2
    with pytest.raises(ValueError, match="entire first member"):
        idle.verified_local(tmp_path, reader.manifest_sha256, chunk | {"uncompressed_sha256": pin(b"bad")})
    visits[-1].index.sequence = 3
    with pytest.raises(ValueError, match="sequence"):
        idle.verified_local(tmp_path, reader.manifest_sha256, chunk)


def test_copy_refuses_wrong_device_and_symlink_before_a_payload_read(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"abc")
    redirected = tmp_path / "redirected"
    redirected.symlink_to(source)
    target = tmp_path / "target"
    lock_path = tmp_path / "lock"
    lock_path.touch()
    device = source.stat().st_dev
    pacing = SimpleNamespace(wait_s=0.)
    with lock_path.open("rb") as lock:
        with pytest.raises(ValueError, match="expected bounded regular file"):
            copy_member(source, target, 3, pin(b"abc"), lock, pacing, required_device=device + 1)
        with pytest.raises(OSError):
            copy_member(redirected, target, 3, pin(b"abc"), lock, pacing, required_device=device)
    assert not target.exists()
