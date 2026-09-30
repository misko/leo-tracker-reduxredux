import numpy as np
import pytest
from lookup import distance_row
from scipy.spatial.distance import pdist, squareform


def test_reads_each_exact_pair_from_scipy_condensed_format():
    points = np.random.default_rng(888).normal(size=(7, 4))
    distances = pdist(points)
    expected = squareform(distances)
    for i in range(len(points)):
        assert np.allclose(distance_row(distances, len(points), i), expected[i])
    with pytest.raises(ValueError):
        distance_row(distances, 8, 0)
