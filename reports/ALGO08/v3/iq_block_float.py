"""Reconstruct CI16 from an explicitly lossy, per-stereo-visit encoding."""

import ctypes as ct
from pathlib import Path

import numpy as np


SOURCE = Path(__file__).with_suffix(".c")
COMPILE = ("cc", "-std=c11", "-O3", "-mavx2", "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror")


class Codec:
    def __init__(self, binary):
        library = ct.CDLL(str(binary))
        address, count, width = ct.c_void_p, ct.c_size_t, ct.c_uint
        self.pack, self.unpack = library.encode_visit, library.decode_visit
        self.pack.argtypes = [address, count, width, address, count, ct.POINTER(count)]
        self.unpack.argtypes = [address, count, width, address, count]
        self.pack.restype = self.unpack.restype = ct.c_int

    def encode(self, samples, width):
        if (width not in (8, 10) or samples.dtype != np.dtype("<i2") or not samples.flags.c_contiguous
                or not samples.size or samples.shape[-2:] != (2, 2)):
            raise ValueError("Require complete contiguous signed stereo CI16 samples and a known width")
        encoded = np.empty(1 + samples.size * width // 8, dtype="u1")
        clips = ct.c_size_t()
        if self.pack(samples.ctypes.data, samples.size, width, encoded.ctypes.data, encoded.size, ct.byref(clips)):
            raise ValueError("Cannot encode this stereo extent")
        return encoded, clips.value

    def decode(self, encoded, width, output):
        if (output.dtype != np.dtype("<i2") or not output.flags.c_contiguous or not output.flags.writeable
                or encoded.dtype != np.dtype("u1") or not encoded.flags.c_contiguous):
            raise ValueError("Require contiguous packed input and writable CI16 output")
        if self.unpack(encoded.ctypes.data, encoded.size, width, output.ctypes.data, output.size):
            raise ValueError("Invalid stored block-floating header or payload extent")
