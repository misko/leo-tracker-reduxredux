import numpy as np
from header_repetition_grid import transition_counts


def test_repeated_bits_have_changes_only_at_grid_boundaries():
    rng = np.random.default_rng(802)
    repeated = np.repeat(rng.integers(0, 2, (6, 100), dtype=np.uint8), 4, axis=1)
    changes, support = transition_counts(repeated, np.ones_like(repeated, dtype=bool), 4)
    assert changes[0] > 0 and changes[1:].sum() == 0
    assert support.min() > 0
