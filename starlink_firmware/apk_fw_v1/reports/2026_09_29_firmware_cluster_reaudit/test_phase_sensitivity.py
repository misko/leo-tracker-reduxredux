import numpy as np
from phase_sensitivity import invariants


def test_within_symbol_products_cancel_independent_symbol_rotations():
    rng = np.random.default_rng(42)
    z = rng.normal(size=(2, 6, 4)) + 1j * rng.normal(size=(2, 6, 4))
    rotations = np.exp(1j * rng.normal(size=(2, 6, 1)))
    np.testing.assert_allclose(invariants(z)["within_symbol"],
                               invariants(z * rotations)["within_symbol"], atol=1e-12)
    np.testing.assert_allclose(invariants(z)["between_symbols"],
                               invariants(z * np.exp(.7j))["between_symbols"], atol=1e-12)
