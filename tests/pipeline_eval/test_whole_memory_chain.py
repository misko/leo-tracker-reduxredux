from hashlib import sha256
from random import Random

import pytest
import zstandard as zstd

from tools.pipeline_eval.qualification.whole_memory_chain_worker import BLOCK, AuthenticatedMember


def test_streams_and_authenticates_the_complete_compressed_member(tmp_path):
    raw = Random(0).randbytes(3 * BLOCK + 9)
    compressed = zstd.ZstdCompressor().compress(raw)
    path = tmp_path / "sample.ci16.zst"
    path.write_bytes(compressed)
    verified = []
    member = AuthenticatedMember(
        path, len(compressed), "sha256:" + sha256(compressed).hexdigest(), verified
    )
    with zstd.ZstdDecompressor().stream_reader(member) as reader:
        assert reader.read(41) == raw[:41]
        assert reader.read() == raw[41:]
    assert verified == [len(compressed)]
    assert member.file.closed


def test_bounded_reads_and_trailing_bytes_cannot_bypass_authentication(tmp_path):
    path = tmp_path / "chunk"
    data = b"x" * (2 * BLOCK + 2)
    path.write_bytes(data)
    verified = []
    with pytest.raises(ValueError, match="size"):
        AuthenticatedMember(path, len(data) - 1, "sha256:wrong", verified)
    member = AuthenticatedMember(path, len(data), "sha256:wrong", verified)
    assert len(member.read(5 * BLOCK)) == BLOCK
    with pytest.raises(ValueError, match="SHA-256"):
        member.close()
    assert member.file.closed
    assert verified == []
