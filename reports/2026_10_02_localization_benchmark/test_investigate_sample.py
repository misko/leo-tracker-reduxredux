import numpy as np
from investigate_sample import local_displacement


def test_local_displacement_zero_at_reference():
    np.testing.assert_allclose(local_displacement([0, 0], [38.5816, -121.4944]), 0, atol=1e-9)


def test_local_displacement_preserves_east_and_north_signs():
    assert local_displacement([1, 0], [38.5816, -121.4944])[0] > 0.99
    assert local_displacement([0, 1], [38.5816, -121.4944])[1] > 0.99
