from collections import Counter
import numpy as np
import pytest
import zstandard as zstd

from reports.ALGO08.v3.dense_zstd_backend import OwnedBytesStream
from reports.ALGO08.v3.native_verified_drain import ZSTD
from reports.ALGO08.v3.zstd_assembly_trial import backend


@pytest.mark.parametrize("mode", ["asm", "c"])
def test_local_switch_keeps_stream_checksum_and_native_output(mode):
    if not ZSTD.is_file():
        pytest.fail("This component's same-build switch requires the installed libzstd 1.5.7 test library")
    decoder = backend(mode)
    payload = b"0123456" * 1000
    frame = zstd.ZstdCompressor(write_checksum=True).compress(payload)
    with_stream = lambda data: OwnedBytesStream(decoder, np.frombuffer(data, dtype="u1"), Counter(), zstd.ZstdError)
    stream = with_stream(frame)
    try:
        assert stream.read(400) + stream.read(len(payload)-400) == payload
        assert stream.read(1) == b""
    finally:
        stream.close()
    broken = frame[:-1] + bytes((frame[-1] ^ 1,))
    stream = with_stream(broken)
    try:
        with pytest.raises(zstd.ZstdError, match="rejected"):
            stream.read(len(payload)+1)
    finally:
        stream.close()
