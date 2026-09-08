"""Explicit LGO1 opt-in; the wrapped published provider request stays opaque.

Runtime artifact paths are trusted daemon configuration, never remote input.
This transport request enables evidence delivery, not a classification policy.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

HEADER_BYTES = 96
MAX_REQUEST_BYTES = 4096
_HEADER = struct.Struct("<4sHHIIQII32s32s")


@dataclass(frozen=True)
class ScannerGlrtRequestV1:
    generation: int
    algorithm_sha256: str
    configuration_sha256: str
    legacy_request: bytes
    rx: int = 1

    def __post_init__(self) -> None:
        if type(self.generation) is not int or not 0 < self.generation < 2**64:
            raise ValueError("GLRT generation must be a nonzero uint64")
        if type(self.rx) is not int or self.rx != 1:
            raise ValueError("the current scanner detector supports only RX1")
        for digest in (self.algorithm_sha256, self.configuration_sha256):
            if (
                not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or digest == "0" * 64
            ):
                raise ValueError("GLRT identities must be nonzero lowercase SHA-256 digests")
        if (
            not isinstance(self.legacy_request, bytes)
            or not 0 < len(self.legacy_request) <= MAX_REQUEST_BYTES - HEADER_BYTES
        ):
            raise ValueError("GLRT requires a bounded, immutable legacy request")


def encode_request(request: ScannerGlrtRequestV1) -> bytes:
    if not isinstance(request, ScannerGlrtRequestV1):
        raise TypeError("expected a ScannerGlrtRequestV1")
    return (
        _HEADER.pack(
            b"LGO1",
            1,
            HEADER_BYTES,
            HEADER_BYTES + len(request.legacy_request),
            len(request.legacy_request),
            request.generation,
            request.rx,
            0,
            bytes.fromhex(request.algorithm_sha256),
            bytes.fromhex(request.configuration_sha256),
        )
        + request.legacy_request
    )


def decode_request(packet: bytes) -> ScannerGlrtRequestV1:
    if not isinstance(packet, bytes) or not HEADER_BYTES < len(packet) <= MAX_REQUEST_BYTES:
        raise ValueError("invalid GLRT request size")
    magic, version, header, total, legacy, generation, rx, flags, algorithm, config = (
        _HEADER.unpack_from(packet)
    )
    if (
        magic != b"LGO1"
        or version != 1
        or header != HEADER_BYTES
        or flags
        or total != len(packet)
        or legacy != len(packet) - HEADER_BYTES
    ):
        raise ValueError("invalid GLRT request framing")
    return ScannerGlrtRequestV1(
        generation, algorithm.hex(), config.hex(), packet[HEADER_BYTES:], rx
    )
