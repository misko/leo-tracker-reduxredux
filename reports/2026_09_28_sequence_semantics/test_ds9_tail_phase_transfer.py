import numpy as np
from ds9_tail_phase_transfer import phase_gain


def test_known_sign_gain_removes_phase_without_altering_amplitude():
    rng = np.random.default_rng(242)
    signs = rng.choice([-1, 1], size=(3, 30, 4))
    phase = rng.uniform(-2, 2, size=(3, 4))
    values = 2 * signs * np.exp(1j * phase[:, None, :])
    correction = phase_gain(values, signs)
    np.testing.assert_allclose(values * correction[:, None, :], 2 * signs, atol=1e-12)
    np.testing.assert_allclose(abs(correction), 1)
