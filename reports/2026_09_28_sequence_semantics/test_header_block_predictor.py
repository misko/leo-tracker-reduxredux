import numpy as np
from header_block_predictor import evaluate, fit


def test_affine_predictor_transfers_and_exposes_new_independent_output():
    rng = np.random.default_rng(90)
    x = rng.integers(0, 2, size=(78, 3), dtype=np.uint8)
    bits = np.column_stack(
        [x, x[:, 0] ^ x[:, 1] ^ 1, x[:, 1] ^ x[:, 2], np.ones(78, dtype=np.uint8)]
    )
    basis, rules = fit(bits[:39])
    assert basis == [0, 1, 2]
    valid = np.ones_like(bits[39:], dtype=bool)
    assert all(r["errors"] == 0 for r in evaluate(bits[39:], valid, rules))
    bits[40, 3] ^= 1
    result = evaluate(bits[39:], valid, rules)
    assert result[0]["errors"] == 1
