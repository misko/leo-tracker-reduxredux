import numpy as np
from state_residuals import assess, expand, fit_gain


def test_late_fit_ignores_early_signal_and_transfers():
    rng = np.random.default_rng(52)
    p = rng.choice([-1, 1], size=(20, 300, 6))
    z = (2 + 0.3j) * p
    z[:, :32] += rng.normal(size=(20, 32, 6))
    g = fit_gain(z, p)
    assert np.allclose(g, 2 + 0.3j)
    assert np.allclose(z[:, 256:288] - g[:, None, None] * p[:, 256:288], 0)


def test_control_exposes_artificial_shared_subtraction():
    rng = np.random.default_rng(12)
    p = rng.choice([-1, 1], size=(80, 300, 6))
    a = rng.normal(size=p.shape).astype(complex)
    b = rng.normal(size=p.shape).astype(complex)
    a[:, 224:256] = p[:, 224:256]
    b[:, 224:256] = p[:, 224:256]
    r = assess(a, b, p, fit_gain(a, p), fit_gain(b, p), 0, 32)
    assert abs(r["raw_shared"]) < 0.04
    assert r["residual_shared"] > 0.45
    assert r["residual_control_mean"] > 0.45
    assert abs(r["residual_shared"] - r["residual_control_mean"]) < 0.04


def test_per_carrier_fit_transfers_without_using_validation_symbols():
    rng = np.random.default_rng(15)
    p = rng.choice([-1, 1], size=(12, 300, 6))
    gains = rng.normal(size=(12, 6)) + 1j * rng.normal(size=(12, 6))
    z = expand(gains) * p
    fitted = fit_gain(z, p, per_carrier=True)
    assert np.allclose(fitted, gains)
    assert np.allclose(z[:, 256:288] - expand(fitted) * p[:, 256:288], 0)
