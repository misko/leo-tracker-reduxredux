"""Checks for the Linux O_DIRECT descriptor research adapter."""

from errno import EINVAL, ELOOP
import os

import pytest

from leo.storage.errors import BundleCorruptionError
from reports.ALGO08.v3.dense_direct_cold import DirectUnavailable, direct_or_buffered, read_direct


pytestmark = pytest.mark.hardware  # Linux O_DIRECT on a private supporting filesystem.


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "payload.zst"
    payload = (bytes(range(233)) * 101)[:-3]
    with path.open("wb") as out:
        out.write(payload)
        out.flush()
        os.fsync(out.fileno())
    return path, payload


def test_real_non_aligned_eof_returns_only_original_bytes(source):
    path, payload = source
    stats = {}
    result = read_direct(path, len(payload), stats)
    assert result.readonly and result == payload
    assert stats["accepted_bytes"] == len(payload) < stats["rounded_bytes"]
    assert stats["rounded_bytes"] % stats["offset_align"] == 0
    assert stats["calls"] >= 1


def test_aligned_short_reads_continue_at_matching_offsets(source):
    path, payload = source
    offsets = []

    def read(fd, vec, offset):
        offsets.append(offset)
        extent = payload[offset:offset + 4096]
        vec[0][:len(extent)] = extent
        return len(extent)

    result = read_direct(path, len(payload), {}, alignment=lambda fd: (4096, 512), read=read)
    assert result == payload
    assert offsets == list(range(0, len(payload), 4096))


@pytest.mark.parametrize("change", ("ended", "grown", "modified"))
def test_short_eof_and_changed_file_are_rejected(source, change):
    path, payload = source

    def read(fd, vec, offset):
        if change == "ended":
            return 0
        if change == "grown":
            with path.open("ab") as stream:
                stream.write(b"x")
            return len(payload) + 1
        path.write_bytes(b"x" * len(payload))
        return len(payload)

    message = "ended" if change == "ended" else "changed"
    with pytest.raises(BundleCorruptionError, match=message):
        read_direct(path, len(payload), {}, alignment=lambda fd: (512, 512), read=read)


@pytest.mark.parametrize("mode", ("missing", "errno", "unaligned"))
def test_only_capability_failures_restart_buffered(source, mode):
    path, payload = source
    stats = {}

    def read(fd, vec, offset):
        if mode == "errno":
            raise OSError(EINVAL, "unsupported direct read")
        return 17

    def align(fd):
        if mode == "missing":
            raise DirectUnavailable
        return 512, 512

    def attempt(path, size, stats):
        return read_direct(path, size, stats, alignment=align, read=read)

    assert direct_or_buffered(path, len(payload), lambda p, size: p.read_bytes(), stats, direct=attempt) == payload
    assert stats == {"fallbacks": 1}


def test_refuses_symlinks_hardlinks_and_excess_bound(source):
    path, payload = source
    with pytest.raises(BundleCorruptionError, match="bound"):
        read_direct(path, len(payload) - 1, {})
    symlink = path.with_suffix(".symlink")
    symlink.symlink_to(path)
    with pytest.raises(OSError) as error:
        read_direct(symlink, len(payload), {})
    assert error.value.errno == ELOOP
    os.link(path, path.with_suffix(".hardlink"))
    with pytest.raises(BundleCorruptionError, match="not one regular file"):
        read_direct(path, len(payload), {})
