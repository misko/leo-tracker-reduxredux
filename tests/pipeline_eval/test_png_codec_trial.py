from ctypes import addressof, create_string_buffer
from importlib import import_module
from pathlib import Path
from struct import pack
import zlib

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("png_codec_trial")


def test_run_length_deflate_roundtrip_honors_output_bound(trial):
    compressor = trial.ZlibRle()
    filtered = b"\x02" + b"\0" * 700 + bytes(range(256)) * 12
    source = create_string_buffer(filtered)
    destination = create_string_buffer(compressor.libdeflate_zlib_compress_bound(None, len(filtered)))
    size = compressor.libdeflate_zlib_compress(compressor.libdeflate_alloc_compressor(3),
                                               addressof(source), len(filtered), addressof(destination), len(destination))
    assert size > 0
    assert zlib.decompress(destination.raw[:size]) == filtered
    small = create_string_buffer(b"sentinel")
    assert not compressor.libdeflate_zlib_compress(compressor.libdeflate_alloc_compressor(3),
                                                   addressof(source), len(filtered), addressof(small), len(small))
    assert small.value == b"sentinel"


def test_non_idat_binding_validates_all_crcs(trial):
    def chunk(name, data):
        return pack(">I", len(data)) + name + data + pack(">I", zlib.crc32(name + data))

    def png(image, text):
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
                + chunk(b"tEXt", b"Key\0" + text) + chunk(b"IDAT", image) + chunk(b"IEND", b""))

    original = png(b"first", b"original")
    assert trial.file_chunks(original) == trial.file_chunks(png(b"changed", b"original"))
    assert trial.file_chunks(original) != trial.file_chunks(png(b"first", b"new metadata"))
    with pytest.raises(ValueError, match="chunk CRC"):
        trial.file_chunks(original.replace(b"first", b"wrong"))
