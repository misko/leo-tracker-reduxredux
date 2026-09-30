import numpy as np
from ds9_leakage_transfer import load_correction


def test_discovery_fit_removes_linear_leakage_but_preserves_independent_q():
    correct = load_correction()
    rng = np.random.default_rng(53)
    train_i = rng.normal(size=(40, 2, 3))
    held_i = rng.normal(size=(23, 2, 3))
    offset = np.arange(6).reshape(2, 3) + 2j
    slope = np.arange(6).reshape(2, 3) / 5
    independent_q = rng.normal(size=held_i.shape)
    train = offset + train_i * (1 + 1j * slope)
    held = offset + held_i * (1 + 1j * slope) + 1j * independent_q
    result = correct(train, held)
    np.testing.assert_allclose(result[4], slope, atol=1e-14)
    np.testing.assert_allclose(result[2], independent_q, atol=1e-14)
    changed = correct(train, held * 10)
    np.testing.assert_array_equal(changed[3], result[3])
    np.testing.assert_array_equal(changed[4], result[4])
