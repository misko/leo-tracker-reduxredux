"""Pair factors preserve information and remove source-common frequency bias."""

import numpy as np
import pytest
from prototype_dsx01_pair_difference import orthogonal_parts


def test_pairs_replace_original_values_preserving_energy_and_noise_covariance():
    rng = np.random.default_rng(7)
    raw = rng.normal(size=11)
    common, difference, constant = orthogonal_parts(raw, [0, 2, 3], [4, 7, 9])
    assert len(common) + len(difference) == len(raw)
    assert common @ common + difference @ difference == pytest.approx(raw @ raw)
    matrix = np.column_stack(
        [np.r_[*orthogonal_parts(np.eye(11)[i], [0, 2, 3], [4, 7, 9])[:2]] for i in range(11)]
    )
    np.testing.assert_allclose(matrix @ matrix.T, np.eye(11), atol=1e-15)
    np.testing.assert_allclose(matrix @ np.ones(11), np.r_[constant, np.zeros(3)])


def test_reusing_a_point_in_two_pairs_fails_closed():
    with pytest.raises(ValueError, match="disjoint"):
        orthogonal_parts(np.ones(4), [0, 0], [1, 2])
    with pytest.raises(ValueError, match="outside"):
        orthogonal_parts(np.ones(4), [0], [4])
