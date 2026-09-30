import numpy as np
import pytest
from corpus_extension import align


def test_exact_observation_alignment_rejects_duplicates_and_missing_members():
    np.testing.assert_array_equal(align(["b", "a"], ["c", "a", "b"]), [2, 1])
    with pytest.raises(ValueError):
        align(["a"], ["a", "a"])
    with pytest.raises(KeyError):
        align(["missing"], ["a"])
