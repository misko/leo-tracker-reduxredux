import numpy as np
import pytest
from phase_lfsr import extend


def test_lfsr_extension_obeys_recurrence_and_preserves_seed():
    seed = np.random.default_rng(14).integers(0, 2, (3, 15), dtype=np.uint8)
    bits = extend(seed, 100)
    np.testing.assert_array_equal(bits[:, :15], seed)
    np.testing.assert_array_equal(bits[:, 15:] ^ bits[:, 1:-14] ^ bits[:, :-15], 0)
    with pytest.raises(ValueError):
        extend([1, 0], 100)
