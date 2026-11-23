from hashlib import sha256
from io import BytesIO
import os

import pytest

from reports.ALGO08.v3.sparse_cold_input import (
    cache_pages,
    copy_bounded,
    expected_prefix,
    private_identity,
    source_member_name,
)


def test_copy_authenticates_exact_bytes_and_does_not_write_above_limit():
    original = b"signed compressed member"
    digest = sha256(original).hexdigest()
    output = BytesIO()
    assert copy_bounded(BytesIO(original), output, limit=len(original), exact_size=len(original),
                        expected_hash="sha256:" + digest) == len(original)
    assert output.getvalue() == original
    oversize = BytesIO()
    with pytest.raises(ValueError, match="byte bound"):
        copy_bounded(BytesIO(original + b"!"), oversize, limit=len(original), expected_hash=digest)
    assert len(oversize.getvalue()) <= len(original)
    with pytest.raises(ValueError, match="authenticated source"):
        copy_bounded(BytesIO(original + b"!"), BytesIO(), limit=128, expected_hash=digest)


def test_private_cache_rejects_hardlinks_and_outside_paths_before_advice(tmp_path, monkeypatch):
    private = tmp_path / "fixture"
    private.mkdir(mode=0o700)
    saved = tmp_path / "signed-original"
    saved.write_bytes(b"seal")
    path = private / "copy"
    path.write_bytes(saved.read_bytes())
    expected = private_identity(path, private)
    assert expected != private_identity(saved, tmp_path)
    calls = []

    def advise(fd, position, count, flag):
        calls.append((os.fstat(fd).st_ino, position, count, flag))

    monkeypatch.setattr(os, "posix_fadvise", advise)
    assert cache_pages(path, private, expected, lambda fd, size: 0, cold=True) == 0
    assert calls == [(expected[1], 0, 0, os.POSIX_FADV_DONTNEED)]
    hardlink = private / "shared"
    hardlink.hardlink_to(saved)
    with pytest.raises(ValueError, match="private file inodes"):
        cache_pages(hardlink, private, expected, lambda fd, size: 0, cold=True)
    with pytest.raises(ValueError, match="owner-private trial root"):
        cache_pages(saved, private, expected, lambda fd, size: 0, cold=True)
    assert len(calls) == 1


def test_archive_rows_preserve_identity_and_empty_the_suffix_only_inside_scope():
    early = dict(visit_index=63, receiver_id=1, candidates=[{"candidate_rank": 1}])
    tail = dict(visit_index=64, receiver_id=0, candidates=[{"candidate_rank": 0}], rf_hz=17)
    beyond = dict(visit_index=192, receiver_id=0, candidates=[{"candidate_rank": 0}])
    assert expected_prefix({"source": {"probes": [early, tail, beyond]}}, 64) == [
        early, dict(tail, candidates=[]),
    ]
    assert tail["candidates"]
    assert source_member_name("iq-000001.ci16.zst") == "iq-000001.ci16.zst"
    for name in ("", "..", "/var/tmp/payload", "../foreign"):
        with pytest.raises(ValueError, match="basename"):
            source_member_name(name)
