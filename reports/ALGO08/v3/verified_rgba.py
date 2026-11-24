"""Independent RGBA check for the installed lossless encoder's PNG subset."""

import ctypes as ct
from hashlib import sha256
from struct import Struct
from zlib import crc32

from empty_bootstrap import PAYLOAD, checked


DEFLATE = PAYLOAD / "png-deflate.so"
DEFLATE_PIN = "0e33bbae9bd7f62fd4172ac04d9088736defa499491aacae723732ce4e905f94"
SIGNATURE = b"\x89PNG\r\n\x1a\n"
RGBA = b"\x08\x06\x00\x00\x00"
CHUNK = Struct(">I4s")
UNSIGNED = Struct(">I")
SIZE = Struct(">II")
LIMIT = 128 << 20


def layout(data):
    """Return width, height and the single CRC-verified compressed extent."""
    if not data.startswith(SIGNATURE):
        return None
    view = memoryview(data)
    offset = len(SIGNATURE)
    extent = None
    width = height = 0
    ancillary = set()
    while len(data) - offset >= 12:
        length, name = CHUNK.unpack_from(data, offset)
        start = offset + CHUNK.size
        end = start + length
        if len(data) - end < UNSIGNED.size or crc32(view[offset+4:end]) != UNSIGNED.unpack_from(data, end)[0]:
            return None
        if offset == len(SIGNATURE):
            if name != b"IHDR" or length != 13 or data[start+8:end] != RGBA:
                return None
            width, height = SIZE.unpack_from(data, start)
            if width == 0 or height == 0 or (width*4 + 1)*height > LIMIT:
                return None
        elif name == b"IDAT" and extent is None and length:
            extent = start, length
        elif name == b"IEND" and length == 0 and extent is not None and end + 4 == len(data):
            return width, height, extent
        else:
            if extent is not None or name in ancillary:
                return None
            if name == b"pHYs":
                if length != 9 or data[end-1] not in (0, 1):
                    return None
            elif name == b"tEXt":
                if length > 4096:
                    return None
                key, _, value = data[start:end].partition(b"\0")
                if key != b"Software" or not value or b"\0" in value or not value.isascii():
                    return None
            else:
                return None
            ancillary.add(name)
        offset = end + 4
    return None


def symbol(handle, name, restype, *argtypes):
    function = getattr(handle, name)
    function.restype = restype
    function.argtypes = argtypes
    return function


class RgbaEvidence:
    def __init__(self, library, pin, original, audit):
        self.original, self.audit = original, audit
        audit.update(native=0, fallback=0, rgba_bytes=0, library_sha256=pin)
        self.ready = False
        try:
            checked(library, pin)
            checked(DEFLATE, DEFLATE_PIN)
            decoder = ct.CDLL(str(DEFLATE))
            rows = ct.CDLL(str(library))
            self._alloc = symbol(decoder, "libdeflate_alloc_decompressor", ct.c_void_p)
            self._free = symbol(decoder, "libdeflate_free_decompressor", None, ct.c_void_p)
            self._decode = symbol(decoder, "libdeflate_zlib_decompress_ex", ct.c_int,
                                  ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p, ct.c_size_t,
                                  ct.POINTER(ct.c_size_t), ct.POINTER(ct.c_size_t))
            self._unfilter = symbol(rows, "leo_verified_rgba_rows", ct.c_int, ct.c_void_p,
                                    ct.c_size_t, ct.c_size_t, ct.c_size_t)
        except (AttributeError, OSError, ValueError) as error:
            audit["unavailable"] = str(error)
            return
        self.buffer = None
        self.ready = True

    def pixels(self, data):
        info = layout(data)
        if info is None:
            return None
        width, height, (offset, extent) = info
        length = height*(width*4 + 1)
        if self.buffer is None or len(self.buffer) < length:
            # Uninitialized arena. Only the verified full inflate exposes bytes.
            from numpy import empty

            self.buffer = empty(length, dtype="uint8")
        address = self.buffer.ctypes.data
        source = ct.cast(ct.c_char_p(data), ct.c_void_p).value
        decoder = self._alloc()
        if not decoder:
            return None
        consumed, inflated = ct.c_size_t(), ct.c_size_t()
        try:
            status = self._decode(decoder, source+offset, extent, address, length,
                                  ct.byref(consumed), ct.byref(inflated))
        finally:
            self._free(decoder)
        if status or (consumed.value, inflated.value) != (extent, length):
            return None
        if not self._unfilter(address, length, width, height):
            return None
        rgba = memoryview(self.buffer)[:width*height*4]
        self.audit["native"] += 1
        self.audit["rgba_bytes"] += len(rgba)
        return (width, height), sha256(rgba).hexdigest()

    def __call__(self, data, digest):
        # The ordinary verified artifact read already independently checked the file SHA.
        result = self.pixels(data) if self.ready else None
        if result is None:
            self.audit["fallback"] += 1
            return self.original(data, digest)
        size, rgba = result
        return dict(size=size, sha256=digest, rgba_sha256=rgba)
