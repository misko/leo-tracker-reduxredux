import numpy as np
from tail_header_phase_transfer import fit_phase


def test_phase_fit_recovers_drift_independently_of_modulated_signs():
    index = np.arange(50, 150)
    signs = np.random.default_rng(65).choice([-1, 1], len(index))
    values = 0.7 * signs * np.exp(1j * (-0.002 * index + 0.9))
    np.testing.assert_allclose(fit_phase(index, values, signs), [-0.002, 0.9], atol=1e-12)
