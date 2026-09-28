import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ds789_frequency_mixture import fit, predict  # noqa: E402


def test_prediction_matches_dense_complex_gaussian():
    rng = np.random.default_rng(17)
    training = rng.normal(size=(13, 2)) + 1j * rng.normal(size=(13, 2))
    held = rng.normal(size=(11, 2)) + 1j * rng.normal(size=(11, 2))
    tt, th = np.arange(13) * 0.001, np.arange(11) * 0.001 + 0.0005
    frequency = 23.0
    model = fit(training, tt, [frequency])
    train_a = np.exp(2j * np.pi * frequency * tt)
    dense_bf = 0.0
    for tone in range(2):
        covariance = model["variance"][tone] * (np.eye(len(tt)) + np.outer(train_a, train_a.conj()))
        _, logdet = np.linalg.slogdet(covariance)
        y = training[:, tone]
        dense_bf += -logdet - np.vdot(y, np.linalg.solve(covariance, y)).real
        dense_bf += (
            len(tt) * np.log(model["variance"][tone]) + np.vdot(y, y).real / model["variance"][tone]
        )
    assert model["log_bf"][0] == pytest.approx(dense_bf, abs=1e-10)
    a = np.exp(2j * np.pi * frequency * th)
    total = 0.0
    for tone in range(2):
        covariance = model["variance"][tone] * (
            np.eye(len(th)) + model["posterior_ratio"] * np.outer(a, a.conj())
        )
        residual = held[:, tone] - a * model["mean"][0, tone]
        sign, logdet = np.linalg.slogdet(covariance)
        assert sign == pytest.approx(1)
        total += (
            -len(th) * np.log(np.pi)
            - logdet
            - np.vdot(residual, np.linalg.solve(covariance, residual)).real
        )
    assert predict(model, held, th, include_null=False)["log_density"] == pytest.approx(
        total, abs=1e-10
    )


def test_translated_domain_invariance_and_posterior_normalization():
    rng = np.random.default_rng(51)
    times = np.arange(150) * 8.8e-6
    values = np.exp(2j * np.pi * 331.4 * times[:, None]) * np.ones((1, 8))
    values += 0.5 * (rng.normal(size=values.shape) + 1j * rng.normal(size=values.shape))
    grid = np.arange(-2000, 2001, 10)
    model = fit(values[::2], times[::2], grid)
    shifted = values * np.exp(2j * np.pi * 253.1 * times[:, None])
    moved = fit(shifted[::2], times[::2], grid + 253.1)
    np.testing.assert_allclose(model["weights"], moved["weights"], atol=1e-12)
    assert model["weights"].sum() == pytest.approx(1)
    assert np.exp(model["log_signal_probability"]) + np.exp(
        model["log_null_probability"]
    ) == pytest.approx(1)
    assert np.exp(model["log_signal_probability"]) > 0.99
    mean = np.sum(grid * model["weights"])
    assert abs(mean - 331.4) < 50
    for null in (False, True):
        a = predict(model, values[1::2], times[1::2], include_null=null)
        b = predict(moved, shifted[1::2], times[1::2], include_null=null)
        assert a["log_density"] == pytest.approx(b["log_density"], abs=1e-9)


def test_zero_power_rejected_and_noise_can_retain_null():
    times = np.arange(75) * 17.6e-6
    with pytest.raises(ValueError, match="positive training power"):
        fit(np.zeros((75, 8)), times, [0])
    rng = np.random.default_rng(22)
    noise = rng.normal(size=(75, 8)) + 1j * rng.normal(size=(75, 8))
    model = fit(noise, times, np.arange(-2000, 2001, 10))
    assert np.exp(model["log_null_probability"]) > 0.99
