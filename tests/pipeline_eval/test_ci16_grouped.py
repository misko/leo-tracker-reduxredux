import ctypes as ct
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3.ci16_grouped_trial import GROUPED, LEGACY, GroupedPacking
from reports.ALGO08.v3.ci16_packing import Packing


@pytest.fixture(scope="module", params=[(), pytest.param(("-mssse3",), marks=pytest.mark.hardware)])
def codecs(request, tmp_path_factory):
    root = tmp_path_factory.mktemp("ci16-grouped")
    for name, source in (("legacy", LEGACY), ("grouped", GROUPED)):
        subprocess.run(["cc", "-std=c11", "-O3", "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror",
                        *request.param, str(source), "-o", str(root/(name+".so"))], check=True)
    return Packing(root/"legacy.so"), GroupedPacking(root/"grouped.so")


@pytest.mark.parametrize("width", range(1, 17))
def test_every_wire_width_signed_shift_and_alignment(codecs, width):
    original, candidate = codecs
    random = np.random.default_rng(width*517)
    bound = 1 << (width-1)
    for shift in range(17-width):
        scale = 1 << shift
        for size in (1, 2, 7, 8, 9, 15, 16, 17, 23, 24, 25, 37):
            words = random.integers(-bound, bound, size).tolist()
            words[0] = -bound
            if size > 1:
                words[1] = bound-1
            raw = (np.asarray(words)*scale).astype("<i2").tobytes()
            for offset in (0, 1, 2, 3, 7, 15):
                aligned = memoryview(bytearray(b"x"*offset+raw))[offset:]
                encoded = candidate.compress(aligned)
                assert bytes(encoded) == bytes(original.compress(aligned))
                code = memoryview(bytearray(b"y"*offset+encoded))[offset:]
                assert candidate.decode(code, len(raw)) == raw
            if encoded[0] != 16:
                bits, zeros = encoded[:2]
                values = (word*scale >> zeros for word in words)
                reservoir = sum((value & ((1 << bits)-1)) << (i*bits) for i, value in enumerate(values))
                assert bytes(encoded[2:]) == reservoir.to_bytes((bits*size+7)//8, "little")


@pytest.mark.parametrize("width", [1, 4, 9, 11, 12, 13, 14, 15, 16])
def test_native_extents_and_padding_are_checked_before_writes(codecs, width):
    old, new = codecs
    bound = 1 << (width-1)
    raw = np.resize(np.asarray([-bound, bound-1, 0, -1], dtype="<i2"), 19)
    size = (len(raw)*width+7)//8
    expected = bytes(old.compress(raw.tobytes()))[2:]
    for alignment in range(16):
        out = (ct.c_uint8*(alignment+size+1))(*([123]*(alignment+size+1)))
        payload = ct.addressof(out)+alignment
        pack = new.library.ci16_pack
        unpack = new.library.ci16_unpack
        assert pack(raw.ctypes.data, len(raw), width, 0, payload, size-1) == -1
        assert all(byte == 123 for byte in out)
        assert pack(raw.ctypes.data, len(raw), width, 0, payload, size) == 0
        assert bytes(out[alignment:-1]) == expected and out[-1] == 123
        decoded = np.full(len(raw)+2, 123, dtype="<i2")
        address = decoded.ctypes.data+2
        if (len(raw)*width) % 8:
            unpadded = out[-2]
            out[-2] = unpadded | 128
            assert unpack(payload, size, width, 0, address, len(raw)) == -1
            assert np.all(decoded == 123)
            out[-2] = unpadded
        assert unpack(payload, size, width, 0, address, len(raw)) == 0
        assert np.array_equal(decoded[1:-1], raw) and decoded[0] == decoded[-1] == 123
