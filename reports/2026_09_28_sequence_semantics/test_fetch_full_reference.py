import zlib

import numpy as np
import pytest
from fetch_full_reference import decode_chunk


def test_decode_chunk_checks_layout_and_length():
    dtype = np.dtype([("real", "<f8"), ("imag", "<f8")])
    original = np.zeros((3, 4), dtype=dtype)
    original["real"] = np.arange(12).reshape(3, 4)
    original["imag"] = -original["real"]
    compressed = zlib.compress(original.tobytes())
    np.testing.assert_array_equal(decode_chunk(compressed, dtype, (3, 4)), original)
    with pytest.raises(ValueError):
        decode_chunk(compressed, dtype, (4, 4))
