"""Public Python/C negotiation parity, including unaligned and hostile input."""

import ctypes as ct
import errno
import struct
from dataclasses import replace

import pytest

from leo.contracts.scanner_glrt_request import ScannerGlrtRequestV1, decode_request, encode_request
from tests.scanner.test_scanner_glrt_port import port as port


class Request(ct.Structure):
    _fields_ = [
        ("generation", ct.c_uint64),
        ("rx", ct.c_uint32),
        ("algorithm_sha256", ct.c_uint8 * 32),
        ("configuration_sha256", ct.c_uint8 * 32),
        ("legacy_request", ct.c_void_p),
        ("legacy_bytes", ct.c_size_t),
    ]


@pytest.fixture
def codec(port):
    port.leo_scanner_glrt_request_decode.argtypes = [ct.POINTER(Request), ct.c_void_p, ct.c_size_t]
    port.leo_scanner_glrt_request_encode.argtypes = [ct.POINTER(Request), ct.c_void_p, ct.c_size_t]
    port.leo_scanner_glrt_request_encode.restype = ct.c_ssize_t
    return port


def request(legacy=b"\0opaque-tandem-HOPR\xff"):
    return ScannerGlrtRequestV1(2**64 - 1, "12" * 32, "34" * 32, legacy)


@pytest.mark.parametrize("size", [1, 504, 4000])
def test_python_c_round_trip_borrowed_bytes_and_capacity(codec, size):
    value = request(bytes(i % 256 for i in range(size)))
    packet = encode_request(value)
    assert decode_request(packet) == value
    buffer = ct.create_string_buffer(b"x" + packet)
    decoded = Request()
    assert (
        codec.leo_scanner_glrt_request_decode(ct.byref(decoded), ct.byref(buffer, 1), len(packet))
        == 0
    )
    assert decoded.legacy_request == ct.addressof(buffer) + 1 + 96
    assert decoded.generation == value.generation and decoded.rx == 1
    assert ct.string_at(decoded.legacy_request, decoded.legacy_bytes) == value.legacy_request
    output = ct.create_string_buffer(b"z" * len(packet), len(packet))
    assert (
        codec.leo_scanner_glrt_request_encode(ct.byref(decoded), output, len(packet) - 1)
        == -errno.ENOSPC
    )
    assert output.raw == b"z" * len(packet)
    assert codec.leo_scanner_glrt_request_encode(ct.byref(decoded), output, len(packet)) == len(
        packet
    )
    assert output.raw == packet


@pytest.mark.parametrize(
    "mutation",
    [
        "magic",
        "version",
        "header",
        "total",
        "legacy",
        "flags",
        "rx",
        "generation",
        "algorithm",
        "configuration",
        "truncated",
        "trailing",
        "empty",
        "oversized",
    ],
)
def test_c_and_python_reject_the_same_bad_envelopes(codec, mutation):
    packet = bytearray(encode_request(request()))
    fields = {
        "magic": (0, "I", 0),
        "version": (4, "H", 2),
        "header": (6, "H", 95),
        "total": (8, "I", 2**32 - 1),
        "legacy": (12, "I", 0),
        "flags": (28, "I", 1),
        "rx": (24, "I", 0),
        "generation": (16, "Q", 0),
    }
    if mutation in fields:
        offset, fmt, value = fields[mutation]
        struct.pack_into("<" + fmt, packet, offset, value)
    elif mutation in ("algorithm", "configuration"):
        offset = 32 if mutation == "algorithm" else 64
        packet[offset : offset + 32] = bytes(32)
    elif mutation == "truncated":
        packet = packet[:-1]
    elif mutation == "trailing":
        packet += b"x"
    elif mutation == "empty":
        packet = packet[:96]
    else:
        packet += bytes(4097)
    packet = bytes(packet)
    with pytest.raises(ValueError):
        decode_request(packet)
    decoded = Request(generation=91)
    assert (
        codec.leo_scanner_glrt_request_decode(ct.byref(decoded), packet, len(packet))
        == -errno.EINVAL
    )
    assert decoded.generation == 91


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", True),
        ("generation", -1),
        ("generation", 2**64),
        ("generation", 1.0),
        ("rx", True),
        ("rx", 0),
        ("algorithm_sha256", "0" * 64),
        ("configuration_sha256", "AB" * 32),
        ("legacy_request", b""),
        ("legacy_request", bytearray(b"mutable")),
        ("legacy_request", bytes(4001)),
    ],
)
def test_request_is_strict_and_has_no_remote_artifact_path(field, value):
    with pytest.raises(ValueError):
        replace(request(), **{field: value})
