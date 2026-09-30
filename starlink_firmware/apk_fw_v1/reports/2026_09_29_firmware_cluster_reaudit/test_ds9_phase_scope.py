import numpy as np
from ds9_phase_scope import phase_correction


def test_tail_phase_recovers_fixed_per_frame_carrier_rotation():
    rng = np.random.default_rng(8)
    signs = rng.choice([-1, 1], (5, 30, 4))
    phase = rng.uniform(-np.pi, np.pi, (5, 4))
    values = signs * np.exp(1j * phase[:, None])
    correction = phase_correction(values, signs)
    np.testing.assert_allclose(values * correction[:, None], signs, atol=1e-14)
    np.testing.assert_allclose(abs(correction), 1, atol=1e-14)
