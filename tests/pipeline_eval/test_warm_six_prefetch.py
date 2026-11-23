import errno
import os

import pytest

from reports.ALGO08.v3 import warm_six_prefetch as trial


def test_residency_requires_both_signed_files_in_all_six_members():
    full = dict(observed_members=1, unavailable={}, cached_pages=9, observed_file_pages=9)
    assert trial.all_resident([dict(payload=full, index=full) for _ in range(6)])
    gap = dict(full, cached_pages=8)
    assert not trial.all_resident([dict(payload=full, index=full)] * 5 + [dict(payload=full, index=gap)])
    assert not trial.all_resident([dict(payload=full, index=full)] * 5)


def test_cache_only_guard_advances_the_original_descriptor_without_retry(tmp_path, monkeypatch):
    path = tmp_path / "member"
    path.write_bytes(b"signed resident bytes")
    reads = trial.ResidentReads()

    def positional(fd, buffers, offset):
        view, = buffers
        body = os.pread(fd, len(view), offset)
        view[:len(body)] = body
        return len(body)

    monkeypatch.setattr(trial, "read_nowait", positional)
    with path.open("rb") as stream:
        assert reads.read(stream.fileno(), 6) == b"signed"
        assert os.lseek(stream.fileno(), 0, os.SEEK_CUR) == 6

        def would_block(*_):
            raise OSError(errno.EAGAIN, "not resident")

        monkeypatch.setattr(trial, "read_nowait", would_block)
        with pytest.raises(trial.ColdPage, match="offset 6"):
            reads.read(stream.fileno(), 2)
        assert os.lseek(stream.fileno(), 0, os.SEEK_CUR) == 6


def test_public_guard_requires_residency_on_the_same_device(tmp_path, monkeypatch):
    path = tmp_path / "member"
    path.write_bytes(b"hello")
    monkeypatch.setattr(trial.subprocess, "check_output", lambda *args, **kwargs: "tmpfs\n")
    resident = [1]
    reads = trial.ResidentTmpfsReads(tmp_path, lambda _, size: resident[0])
    with path.open("rb") as stream:
        assert reads.read(stream.fileno(), 1) == b"h"
        resident[0] = 0
        with pytest.raises(trial.ColdPage, match="lost residency"):
            reads.read(stream.fileno(), 1)
        assert os.lseek(stream.fileno(), 0, os.SEEK_CUR) == 1
