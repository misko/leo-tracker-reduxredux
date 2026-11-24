from hashlib import sha256
import errno
import os

import pytest

from reports.ALGO08.v3.first_member_0419 import INVENTORY_PIN, authenticate, payload_cache, select_first


def test_signed_first_selection_cannot_move_to_a_later_segment(tmp_path):
    first = {"path": str(tmp_path / "first"), "scope": "segment-00000000", "manifest_digest": "sha256:first"}
    next_ = {"path": str(tmp_path / "later"), "scope": "segment-00000001", "manifest_digest": "sha256:later"}
    inventory = {"segments": [first, next_], "window_count": 77}
    request = {"case": "DS30-0419", "inventory": "sha256:" + INVENTORY_PIN, "issued": 77,
               "recording": str(tmp_path), "manifests": [[first["path"] + "/manifest.json", "sha256:first"]]}
    assert select_first(request, inventory)[1] == first
    with pytest.raises(ValueError, match="First enrolled"):
        select_first(request, dict(inventory, segments=[next_, first]))


def test_payload_observation_reads_no_data_and_retains_query_errors(tmp_path, monkeypatch):
    target = tmp_path / "member.ci16.zst"
    content = b"x" * 8193
    target.write_bytes(content)
    assert authenticate(content, sha256(content).hexdigest()) == content

    def data_read(*args):
        raise AssertionError("Admission must not read waveform data")

    for operation in ("read", "pread", "preadv"):
        monkeypatch.setattr(os, operation, data_read)
    report = payload_cache(target, len(content), lambda fd, size: 0, 4096)
    assert report["file_pages"] == 3 and report["cached_pages"] == 0

    def unsupported(fd, size):
        raise OSError(errno.EOPNOTSUPP, "Cache observation unavailable")

    report = payload_cache(target, len(content), unsupported, 4096)
    assert report["cached_pages"] is None and report["cache_error"] == "ENOTSUP"
