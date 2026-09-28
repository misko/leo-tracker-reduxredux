import numpy as np
from soft_tail_boundary import power_boundary


def test_power_boundary_invariant_to_amplitude_and_signs():
    rng = np.random.default_rng(53)
    values = np.r_[np.full(2500, 1 + 1j), np.ones(3500)].astype(complex)
    expected = power_boundary(values)
    transformed = values.real * rng.choice([-1, 1], len(values)) + 1j * values.imag * rng.choice(
        [-1, 1], len(values)
    )
    transformed *= rng.uniform(0.1, 3, len(values))
    actual = power_boundary(transformed)
    assert expected["offset"] == actual["offset"] == 2500
    assert abs(expected["before_mean"] - actual["before_mean"]) < 1e-12
