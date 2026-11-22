from ctypes.util import find_library
from hashlib import sha256

import numpy as np
import pytest
import zstandard as zstd

from tools.pipeline_eval.variants.experimental.deferred_receiver import _immutable_iq
from tools.pipeline_eval.variants.experimental.receiver_zstd_arena import DecodeArena, runtime


@pytest.fixture(scope="module")
def library():
    path = find_library("zstd")
    if path is None:
        pytest.skip("The optional native decoder requires the system libzstd runtime")
    return runtime(path)


@pytest.fixture(params=[False, True], ids=["direct", "stable"])
def decoder(library, request):
    if request.param and library.ZSTD_versionNumber() != 10507:
        pytest.skip("The stable-output flag is qualified with libzstd 1.5.7")
    with DecodeArena(library, stable=request.param) as arena:
        yield arena


@pytest.mark.parametrize("advertise", [False, True])
def test_reuse_preserves_both_complete_frames(decoder, advertise):
    values = np.random.default_rng(37).integers(0, 256, 54_321, dtype=np.uint8)
    compressed = zstd.ZstdCompressor(write_content_size=advertise, write_checksum=True)
    output = np.empty(60_000, dtype=np.uint8)
    for expected in (values.tobytes(), values[::-1].tobytes()):
        frame = compressed.compress(expected)
        with memoryview(frame) as readonly:
            assert decoder.decode(readonly, output, len(expected))
        assert sha256(output[: len(expected)]).digest() == sha256(expected).digest()


def test_ineligible_extent_and_corruption_leave_decode_to_the_canonical_caller(decoder):
    expected = b"6000 samples" * 500
    compressor = zstd.ZstdCompressor(write_content_size=False, write_checksum=True)
    frame = compressor.compress(expected)
    corrupt_checksum = frame[:-1] + bytes([frame[-1] ^ 1])
    output = np.empty(len(expected) + 100, dtype=np.uint8)
    for invalid in (
        frame[:-1],
        frame + b"extra bytes",
        frame + compressor.compress(b""),
        frame + frame,
        corrupt_checksum,
        b"not a frame",
        b"",
    ):
        assert not decoder.decode(invalid, output, len(expected))
    assert not decoder.decode(frame, output, len(expected) - 1)
    assert not decoder.decode(frame, output, len(expected) + 1)
    assert not decoder.decode(frame, output, 129 * 1024**2)
    assert not decoder.decode(frame, output[::2], len(expected))
    declared = zstd.ZstdCompressor().compress(expected)
    assert not decoder.decode(declared, output, len(expected) - 1)
    assert decoder.decode(frame, output, len(expected))  # Reset after all failures.
    with zstd.ZstdDecompressor().stream_reader(frame + compressor.compress(b"")) as original:
        assert original.read() == expected


def test_deferred_receiver_keeps_its_snapshot_when_the_arena_is_overwritten(decoder):
    output = np.empty(1_600_000, dtype=np.uint8)
    compress = zstd.ZstdCompressor().compress
    original = b"\xa5" * output.size
    assert decoder.decode(compress(original), output, len(original))
    with memoryview(output).toreadonly() as view:
        window = np.frombuffer(view, dtype="<i2").reshape((200_000, 2, 2))
        retained = _immutable_iq(window)
    assert not retained.flags.writeable
    assert not np.shares_memory(window, retained)
    assert decoder.decode(compress(bytes(output.size)), output, output.size)
    assert retained.tobytes() == original
