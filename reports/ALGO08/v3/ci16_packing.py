"""Private measured-width CI16 payload for the aperture capture experiment."""

from collections import Counter
import ctypes as ct
from hashlib import sha256
from pathlib import Path
import sys

import numpy as np


SCHEMA = "private-algo08-stereo-12ms-prefix-8ms-tail-packed-ci16-v1"
SOURCE = Path(__file__).with_suffix(".c")


class Packing:
    schema = SCHEMA
    part_files = ("prefix.ci16p", "tail.ci16p")

    def __init__(self, binary):
        if sys.byteorder != "little":
            raise ValueError("The measured native CI16 codec uses little-endian words")
        library = ct.CDLL(str(binary))
        library.ci16_occupied_bits.argtypes = [ct.c_void_p, ct.c_size_t, ct.POINTER(ct.c_uint), ct.POINTER(ct.c_uint)]
        library.ci16_occupied_bits.restype = None
        signature = [ct.c_void_p, ct.c_size_t, ct.c_uint, ct.c_uint, ct.c_void_p, ct.c_size_t]
        for function in (library.ci16_pack, library.ci16_unpack):
            function.argtypes = signature
            function.restype = ct.c_int
        self.library = library
        self.binary = Path(binary)
        self.blocks = Counter()

    def compress(self, raw):
        if not len(raw) or len(raw) % 2:
            raise ValueError("CI16 blocks must have a nonempty whole-word extent")
        samples = np.frombuffer(raw, dtype="<i2")
        if not samples.flags.aligned:
            samples = samples.copy()
        width, shift = ct.c_uint(), ct.c_uint()
        self.library.ci16_occupied_bits(samples.ctypes.data, samples.size, ct.byref(width), ct.byref(shift))
        bits, zeros = width.value, shift.value
        size = (samples.size * bits + 7) // 8
        # Use raw words whenever a packed body cannot reduce its extent.
        if size >= samples.nbytes:
            bits, zeros, size = 16, 0, samples.nbytes
        recorded = np.empty(size + 2, dtype=np.uint8)
        recorded[0], recorded[1] = bits, zeros
        if self.library.ci16_pack(samples.ctypes.data, samples.size, bits, zeros, recorded.ctypes.data + 2, size):
            raise ValueError("Native CI16 packing rejected the measured block")
        self.blocks[bits, zeros] += 1
        return memoryview(recorded).toreadonly()

    def decode(self, encoded, expected_bytes):
        if expected_bytes <= 0 or expected_bytes % 2 or len(encoded) < 3:
            raise ValueError("Invalid packed CI16 block extent")
        bits, zeros = encoded[0], encoded[1]
        words = expected_bytes // 2
        if not 1 <= bits <= 16 or not 0 <= zeros <= 15 or bits + zeros > 16:
            raise ValueError("Invalid signed CI16 width or shift")
        size = (words * bits + 7) // 8
        if len(encoded) != size + 2 or bits < 16 and size >= expected_bytes:
            raise ValueError("Packed CI16 block does not match its committed extent")
        if bits == 16:
            return memoryview(encoded)[2:].toreadonly()
        payload = np.frombuffer(encoded, dtype=np.uint8, offset=2)
        decoded = np.empty(words, dtype="<i2")
        if self.library.ci16_unpack(payload.ctypes.data, size, bits, zeros, decoded.ctypes.data, words):
            raise ValueError("Native CI16 unpacking rejected the committed block")
        return memoryview(decoded).cast("B").toreadonly()

    def programme(self):
        return dict(schema=self.schema, source_sha256=sha256(SOURCE.read_bytes()).hexdigest(),
                    binary_sha256=sha256(self.binary.read_bytes()).hexdigest())

    def counts(self):
        return [dict(width=width, shift=shift, blocks=count) for (width, shift), count in sorted(self.blocks.items())]
