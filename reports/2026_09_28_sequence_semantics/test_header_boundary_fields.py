import numpy as np
from header_boundary_fields import probe


def test_fixed_mask_recovery_and_evaluation_independence():
    rng = np.random.default_rng(401)
    bits = rng.integers(0, 2, (13, 300)).astype(bool)
    labels = rng.integers(0, 2, (13, 18)).astype(bool)
    mask = rng.integers(0, 2, 18).astype(bool)
    bits[:, 100:118] = labels ^ mask
    valid = np.ones_like(bits)
    result = probe(bits, valid, labels)
    assert result["exact_full_evaluation_starts"] == [100]
    bits[6:, 100:118] ^= True
    changed = probe(bits, valid, labels)
    assert changed["selected_start"] == result["selected_start"] == 100
    assert changed["fixed_xor_mask"] == result["fixed_xor_mask"]
    assert changed["exact_full_evaluation_starts"] == []
