from hashlib import sha256
import json

import pytest

from reports.ALGO08.v3.north_owned_capture import commitment, load_commitment


def test_packed_authority_binds_only_its_own_representation(tmp_path):
    data = dict(index_sha256="rows", decoded_sha256="raw", bytes={"prefix.ci16p": 2, "tail.ci16p": 3},
                manifest_compressed_sha256="not-the-root")
    authority = commitment("packed", "owned-seek-root", data, 1)
    assert authority == {
        "schema": "private-owned-capture-packed-ci16-v1", "archive_root_sha256": "owned-seek-root",
        "indexes_sha256": "rows", "logical_decoded_sha256": "raw",
        "emitted_objects": {"prefix.ci16p": 2, "tail.ci16p": 3}, "windows": 1,
    }
    file = tmp_path / "authority.json"
    content = json.dumps(authority).encode()
    file.write_bytes(content)
    pin = sha256(content).hexdigest()
    assert load_commitment(file, pin, "packed") == authority
    with pytest.raises(ValueError, match="requested representation"):
        load_commitment(file, pin, "ordinary")
    file.write_bytes(content + b" ")
    with pytest.raises(ValueError, match="Unexpected source digest"):
        load_commitment(file, pin, "packed")


def test_empty_or_unknown_capture_cannot_create_a_commitment():
    with pytest.raises(ValueError, match="Incomplete"):
        commitment("packed", "owned-root", {"bytes": {}}, 1)
    with pytest.raises(ValueError, match="Incomplete"):
        commitment("unspecified", "owned-root", {"bytes": {"encoded": 3}}, 1)
