import random

import pytest
import zstandard as zstd

from reports.ALGO08.v3.zstd_structure import MAGIC, inspect, literal_section, sequence_count


def header(size, kind, last=False):
    return ((size << 3) | (kind << 1) | last).to_bytes(3, "little")


def test_raw_and_rle_are_distinct_frame_blocks():
    data = MAGIC + bytes((32, 10)) + header(3, 0) + b"abc" + header(7, 1, True) + b"d"
    assert zstd.ZstdDecompressor().decompress(data) == b"abcddddddd"
    out = inspect(data, 10)
    assert out["block_counts"] == {"raw": 1, "rle": 1}
    assert (out["raw_block_bytes"], out["rle_block_decoded_bytes"], out["sequences"]) == (3, 7, 0)


@pytest.mark.parametrize("style,bits,width", [(0, 10, 3), (1, 10, 3), (2, 14, 4), (3, 18, 5)])
def test_huffman_sizes_and_stream_modes(style, bits, width):
    data = (2 | style << 2 | 501 << 4 | 333 << (4+bits)).to_bytes(width, "little")
    assert literal_section(data) == ("huffman_new", width, 333, 501, 1 if style == 0 else 4)


def test_sequence_count_and_truncation():
    assert sequence_count(b"\x7f") == 127
    assert sequence_count(b"\x82\x31") == 561
    assert sequence_count(b"\xff\x17\x00") == 32535
    with pytest.raises(ValueError, match="zero"):
        sequence_count(b"\x00\x00")
    with pytest.raises(ValueError, match="Truncated"):
        sequence_count(b"\xff\xff")


def test_metadata_accounts_for_complete_real_decoded_stream_and_envelope():
    rng = random.Random(17)
    payload = rng.randbytes(50000)*12 + b"last window"
    frame = zstd.ZstdCompressor(write_checksum=True).compress(payload)
    info = inspect(frame, len(payload))
    assert zstd.ZstdDecompressor().decompress(frame) == payload
    assert info["sequences"] and info["match_bytes"] > len(payload)//2 and info["checksum"]
    assert (sum(info["regenerated_literals"].values()) + info["match_bytes"]
            + info["raw_block_bytes"] + info["rle_block_decoded_bytes"] == len(payload))
    with pytest.raises(ValueError, match="trailing"):
        inspect(frame + b"extra", len(payload))
