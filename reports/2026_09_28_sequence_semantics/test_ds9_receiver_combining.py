import numpy as np
from ds9_receiver_combining import design, fit


def test_independent_noise_combining_improves_held_signs():
    rng = np.random.default_rng(2026)
    y = rng.choice([-1, 1], size=(100, 30, 2))
    a = y + rng.normal(size=y.shape) + 1j * rng.normal(size=y.shape)
    b = y + rng.normal(size=y.shape) + 1j * rng.normal(size=y.shape)
    x = design(a, b)
    coefficients = fit(x[:50], y[:50])
    prediction = np.sum(x[50:] * coefficients[None, None], axis=-1)
    assert np.mean((prediction >= 0) != (y[50:] >= 0)) < np.mean(
        (a[50:].real >= 0) != (y[50:] >= 0)
    )
