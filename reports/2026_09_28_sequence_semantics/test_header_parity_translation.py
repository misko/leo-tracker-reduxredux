import numpy as np
from header_parity_translation import parity_check


def test_frozen_parity_detects_later_error_and_excludes_unqualified_frame():
    rng = np.random.default_rng(78)
    bits = rng.integers(0, 2, size=(78, 9), dtype=np.uint8)
    bits[:, -1] = np.bitwise_xor.reduce(bits[:, :-1], axis=1) ^ 1
    valid = np.ones_like(bits, dtype=bool)
    assert parity_check(bits, valid)["evaluation_errors"] == 0
    bits[40, 0] ^= 1
    assert parity_check(bits, valid)["evaluation_errors"] == 1
    valid[40, 0] = False
    result = parity_check(bits, valid)
    assert result["evaluation_count"] == 38 and result["evaluation_errors"] == 0
