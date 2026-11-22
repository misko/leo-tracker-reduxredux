"""Bench-only bounded whole-frame decoding into caller-controlled storage."""

from ctypes import CDLL, Structure, byref, c_int, c_size_t, c_uint, c_uint64, c_void_p

import numpy as np

_CONTENT_SIZE_UNKNOWN = 2**64 - 1
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_MAX_BYTES = 128 * 1024**2


class _Buffer(Structure):
    _fields_ = [("data", c_void_p), ("size", c_size_t), ("pos", c_size_t)]


def runtime(path):
    library = CDLL(str(path))
    signatures = {
        "versionNumber": (c_uint,),
        "createDCtx": (c_void_p,),
        "freeDCtx": (c_size_t, c_void_p),
        "getFrameContentSize": (c_uint64, c_void_p, c_size_t),
        "findFrameCompressedSize": (c_size_t, c_void_p, c_size_t),
        "decompressDCtx": (c_size_t, c_void_p, c_void_p, c_size_t, c_void_p, c_size_t),
        "DCtx_reset": (c_size_t, c_void_p, c_int),
        "DCtx_setParameter": (c_size_t, c_void_p, c_int, c_int),
        "decompressStream": (c_size_t, c_void_p, c_void_p, c_void_p),
    }
    for name, (result, *arguments) in signatures.items():
        function = getattr(library, f"ZSTD_{name}")
        function.argtypes = arguments
        function.restype = result
    return library


class DecodeArena:
    """Expose success only for one complete Zstandard frame of the declared size.

    The caller owns every output buffer and must stop using it before passing
    it back. The benchmark consumes all bytes before reusing its buffer.
    """

    def __init__(self, library, *, stable=False):
        self.library = library
        self.stable = stable
        # This experimental enum is ZSTD_d_stableOutBuffer in the 1.5.7 header.
        if stable and library.ZSTD_versionNumber() != 10507:
            raise ValueError("Stable output was qualified with libzstd 1.5.7")
        self.context = library.ZSTD_createDCtx()
        if not self.context:
            raise MemoryError("Could not initialize the Zstandard decoder")
        if stable and library.ZSTD_DCtx_setParameter(self.context, 1001, 1) != 0:
            self.close()
            raise ValueError("The Zstandard runtime lacks stable output support")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.context:
            self.library.ZSTD_freeDCtx(self.context)
            self.context = None

    def decode(self, compressed, output, size):
        if (
            not self.context
            or not 0 < size <= _MAX_BYTES
            or not output.flags.writeable
            or not output.flags.c_contiguous
            or output.dtype != np.uint8
            or output.nbytes < size
            or compressed[:4] != _ZSTD_MAGIC
        ):
            return False
        source = np.frombuffer(compressed, dtype=np.uint8)
        lib = self.library
        address, length = source.ctypes.data, source.size
        if lib.ZSTD_getFrameContentSize(address, length) not in (_CONTENT_SIZE_UNKNOWN, size):
            return False
        if lib.ZSTD_findFrameCompressedSize(address, length) != length:
            return False
        destination = output.ctypes.data
        if not self.stable:
            return lib.ZSTD_decompressDCtx(self.context, destination, size, address, length) == size

        # A complete compressed frame and its entire output fit these two
        # stable views. Require both cursors to end at the sealed boundaries.
        if lib.ZSTD_DCtx_reset(self.context, 1) != 0:  # ZSTD_reset_session_only
            return False
        incoming = _Buffer(address, length, 0)
        outgoing = _Buffer(destination, size, 0)
        result = lib.ZSTD_decompressStream(self.context, byref(outgoing), byref(incoming))
        return result == 0 and incoming.pos == length and outgoing.pos == size
