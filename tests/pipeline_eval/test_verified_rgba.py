"""Check the independent publication readback against the original PNG decode."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import struct
import subprocess
import sys
import zlib

from PIL import Image
import pytest


REPORT = Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"
sys.path.insert(0, str(REPORT))
from verified_rgba import DEFLATE, RgbaEvidence, SIGNATURE, layout


def chunk(tag, payload):
    data = tag + payload
    return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data))


def png(width, height, deflate, header=b"\x08\x06\x00\x00\x00", ancillary=b""):
    return (SIGNATURE + chunk(b"IHDR", struct.pack(">II", width, height)+header)
            + ancillary + chunk(b"IDAT", deflate) + chunk(b"IEND", b""))


@pytest.fixture(scope="module")
def unfilter(tmp_path_factory):
    if not DEFLATE.is_file():
        pytest.fail(f"Requires the repository's installed ALGO08v3 libdeflate asset at {DEFLATE}")
    library = tmp_path_factory.mktemp("rgba-unfilter")/"unfilter.so"
    subprocess.run(["cc", "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    REPORT/"verified_rgba_rows.c", "-o", library], check=True)
    return library, sha256(library.read_bytes()).hexdigest()


def original(data, digest):
    with Image.open(BytesIO(data)) as image:
        rgba = image.convert("RGBA")
        return dict(size=image.size, sha256=digest, rgba_sha256=sha256(rgba.tobytes()).hexdigest())


@pytest.mark.parametrize("width", (1, 3, 4, 7, 64, 321))
def test_all_reviewed_scanline_filters_match_original_rgba(width, unfilter):
    height, stride = 8, width*4
    original_rgba = [bytes((173*x + 19*y + 37*x*y) % 256 for x in range(stride)) for y in range(height)]
    transformed = []
    for y, (kind, row) in enumerate(zip((2, 1, 2, 0, 1, 2, 1, 0), original_rgba, strict=True)):
        reference = bytes(stride)
        if kind == 2 and y:
            reference = original_rgba[y-1]
        if kind == 1:
            reference = b"\x00"*4 + row[:-4]
        transformed.append(bytes((kind,)) + bytes((a-b) % 256 for a,b in zip(row, reference, strict=True)))
    data = png(width, height, zlib.compress(b"".join(transformed)),
               ancillary=chunk(b"pHYs", struct.pack(">IIB", 4921, 4921, 1)))
    audit = {}
    read = RgbaEvidence(*unfilter, original, audit)
    digest = "sha256:"+sha256(data).hexdigest()
    assert read(data, digest) == original(data, digest)
    assert audit["native"] == 1 and audit["fallback"] == 0
    assert audit["rgba_bytes"] == width*height*4


def test_native_verification_rejects_extra_zlib_data_or_unsupported_png(unfilter):
    completed = zlib.compress(b"\x00\x11\x22\x33\xff")
    data = png(1, 1, completed)
    assert layout(data) is not None
    junk = [
        data[:-1], data+b"x", png(0, 1, completed), png(65536, 1024, completed), png(2, 1, completed),
        png(1, 1, completed+b"x"), png(1, 1, completed[:-1]+bytes((completed[-1]^1,))),
        png(1, 1, zlib.compress(b"\x05\x11\x22\x33\xff")),
        png(1, 1, completed, ancillary=chunk(b"gAMA", b"\0\0\0\x01")),
        data[:30]+bytes((data[30]^1,))+data[31:],
    ]
    expected = {"original": "fallback"}
    audit = {}
    read = RgbaEvidence(*unfilter, lambda *args: expected, audit)
    for image in junk:
        assert read(image, "unqualified-image") == expected
    assert audit["native"] == 0 and audit["fallback"] == len(junk)


def test_bad_binary_pin_retains_the_original_verifier(unfilter):
    audit = {}
    result = object()
    read = RgbaEvidence(unfilter[0], "bad-pin", lambda data, digest: result, audit)
    assert read(b"anything", "sha256:original") is result
    assert audit["unavailable"] and audit["fallback"] == 1


def test_native_recognizes_only_well_formed_publisher_ancillary_chunks(unfilter):
    compressed = zlib.compress(b"\x00\x11\x22\x33\xff")
    marker = chunk(b"tEXt", b"Software\0ALGO08")
    density = chunk(b"pHYs", struct.pack(">IIB", 4921, 4921, 1))
    admitted = png(1, 1, compressed, ancillary=marker+density)
    audit = {}
    reader = RgbaEvidence(*unfilter, original, audit)
    assert reader(admitted, "encoded") == original(admitted, "encoded")

    for unusual in (marker+marker, density+density, chunk(b"pHYs", b"x"), chunk(b"tEXt", b"Description\0text"),
                    chunk(b"tEXt", b"Software-no-separator"), chunk(b"tEXt", b"Software\0x\0y")):
        assert layout(png(1, 1, compressed, ancillary=unusual)) is None

    truncated = png(8, 8, b"unreadable-zlib-data")[:-24]
    with pytest.raises(OSError):
        reader(truncated, "encoded")
    assert audit["native"] == 1 and audit["fallback"] == 1
