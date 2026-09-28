import numpy as np
from ds9_cross_power import cross_powers


def test_shared_quadrature_survives_while_independent_noise_averages_down():
    rng = np.random.default_rng(71)
    common = rng.choice([-1, 1], size=(4, 20000))
    x = common + 1j * (0.5 * common + rng.normal(size=common.shape))
    y = common + 1j * (0.5 * common + rng.normal(size=common.shape))
    real, imag = cross_powers(x, y)
    np.testing.assert_allclose(np.diag(real), 1)
    np.testing.assert_allclose(np.diag(imag), 0.25, atol=0.03)
    assert abs(imag[~np.eye(4, dtype=bool)]).max() < 0.03
