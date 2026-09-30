import numpy as np
import pytest
from pair_family import orbit, partitions


def test_shared_coordinates_and_complete_cyclic_reference():
    bits = np.array([[0, 0, 0], [1, 1, 1], [0, 0, 0], [1, 1, 1]], dtype=bool)
    scores, colors = orbit(bits, [(0, 1), (0, 2)], [0, 0])
    assert colors[1] == colors[2] != colors[0]
    np.testing.assert_array_equal(scores, [[1, 0, 1, 0], [1, 0, 1, 0]])
    with pytest.raises(ValueError, match="bipartite"):
        partitions([(0, 1), (1, 2), (2, 0)])
