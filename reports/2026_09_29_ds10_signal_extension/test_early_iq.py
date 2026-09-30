import numpy as np
from early_iq import compare, remove_offset_and_leakage


def test_training_fit_removes_fixed_offset_and_linear_leakage():
    x = np.arange(20).reshape(10, 2).astype(float)
    z = x + 1j * (3 * x + 8)
    _, _, residual, _, slope = remove_offset_and_leakage(z[:6], z[6:])
    assert np.allclose(slope, 3)
    assert np.allclose(residual, 0)


def test_independent_quadrature_survives_real_leakage_removal():
    rng = np.random.default_rng(5)
    x, q = rng.normal(size=(2, 200, 5))
    z = x + 1j * (2 * x + q)
    _, _, residual, _, _ = remove_offset_and_leakage(z[:100], z[100:])
    assert compare(residual, q[100:])["centered_correlation"] > .95
