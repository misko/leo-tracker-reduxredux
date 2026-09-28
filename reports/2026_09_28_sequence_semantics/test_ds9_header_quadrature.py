import numpy as np
from ds9_header_quadrature import correlation


def test_stationary_offsets_do_not_create_shared_variation():
    rng = np.random.default_rng(19)
    x = rng.normal(size=(2000, 3, 4))
    y = rng.normal(size=x.shape)
    offset = np.arange(12).reshape(1, 3, 4) * 100
    assert abs(correlation(x + offset, y + offset)) < 0.03
    assert np.isclose(correlation(x + offset, 2 * x - offset), 1)
    assert correlation(np.ones((10, 2)), np.ones((10, 2))) is None
