import numpy as np
from header_change_groups import discover, residuals


def test_copy_traces_collapse_and_noisy_noncontiguous_pair_is_found():
    rng = np.random.default_rng(71)
    data = rng.integers(0, 2, (400, 30), dtype=np.uint8)
    data[:, 25] = data[:, 2]
    data[:10, 25] ^= 1
    data[:, 29] = data[:, 2]
    representatives, edges, _ = discover(data)
    assert len(representatives) == 29
    physical = {tuple(sorted((representatives[i], representatives[j]))) for i, j in edges}
    assert (2, 25) in physical
    assert all(29 not in pair for pair in physical)


def test_common_mode_projection_removes_exact_shared_factor():
    common = np.arange(20, dtype=float)
    data = np.column_stack([common + 3, 2 * common - 7])
    assert np.allclose(residuals(data, common), 0)
