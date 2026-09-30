import numpy as np
from header_rank_relations import audit, dependencies


def test_basis_distinguishes_copy_and_three_bit_parity():
    assert dependencies([1, 2, 1, 3]) == [5, 11]
    rng = np.random.default_rng(58)
    base = rng.integers(0, 2, size=(78, 2)).astype(bool)
    bits = np.column_stack([base, base[:, 0], base[:, 0] ^ base[:, 1]])
    result = audit(bits)
    assert result["unique_combined_columns"] == 3
    assert [(r["weight"], r["evaluation_errors"]) for r in result["relations"]] == [(2, 0), (3, 0)]
    bits[50, 3] ^= True
    assert audit(bits)["relations"][1]["evaluation_errors"] == 1
