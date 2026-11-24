import struct

import pytest

from reports.ALGO08.v3.zstd_wide_huffman import WIDTHS, table_extent
from reports.ALGO08.v3.zstd_wide_huffman_trial import Block, build, decode, load


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    return load(build(tmp_path_factory.mktemp("wide-huffman")))


def two_symbols():
    # One explicit weight=1, one inferred weight=1, so the codewords are 0 and 1.
    header = bytes((128, 0x10))
    decoded = [bytes(int((i * (j + 1) % 11) % 2) for i in range(count))
               for j, count in enumerate((201, 201, 201, 200))]

    def bits(symbols):
        value = 1
        for symbol in symbols:
            value = value * 2 + symbol
        return value.to_bytes((8 + len(symbols)) // 8, "little")

    streams = list(map(bits, decoded))
    compressed = header + struct.pack("<HHH", *(len(stream) for stream in streams[:3])) + b"".join(streams)
    return compressed, b"".join(decoded)


def test_both_weight_forms_and_incomplete_descriptor():
    assert table_extent(b"\x80\x10x") == 2
    assert table_extent(b"\x82\x11\x10x") == 3
    assert table_extent(b"\x02\x01\x00x") == 3
    for data in (b"", b"\x00x", b"\x80", b"\x80\x10", b"\x02\x01"):
        with pytest.raises(ValueError):
            table_extent(data)


def test_exact_hot_kernel_tail_and_reused_huffman_table(native):
    compressed, wanted = two_symbols()
    payload = compressed + compressed[2:]
    blocks = (Block * 2)(Block(0, len(compressed), len(wanted), 1),
                          Block(len(compressed), len(compressed)-2, len(wanted), 0))
    output = bytearray(2 * len(wanted))
    for width in (0, *WIDTHS):
        assert decode(native, payload, blocks, width, output)["builds"] == 1
        assert output == wanted + wanted


def test_invalid_bounded_extents_and_termination(native):
    compressed, wanted = two_symbols()
    original = bytearray(len(wanted))
    wrong_size = (Block * 1)(Block(len(compressed), 1, len(wanted), 1))
    for width in (0, *WIDTHS):
        decode(native, compressed, wrong_size, width, original, expected_error=True)
    for malformed in (compressed[:2] + b"\xff\xff" + compressed[4:], compressed[:-1] + b"\0",
                      compressed[:-2], compressed + b"\x01"):
        block = (Block * 1)(Block(0, len(malformed), len(wanted), 1))
        for width in WIDTHS:
            decode(native, malformed, block, width, original, expected_error=True)
