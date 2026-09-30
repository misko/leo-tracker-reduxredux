import numpy as np
from phase_histogram_audit import histogram, reordered


def test_within_region_order_is_irrecoverable_from_histogram():
    rng = np.random.default_rng(7)
    z = np.exp(1j * rng.uniform(-np.pi, np.pi, (2, 300, 8)))
    altered = reordered(z)
    assert np.mean(z != altered) > .95
    np.testing.assert_array_equal(histogram(z), histogram(altered))
