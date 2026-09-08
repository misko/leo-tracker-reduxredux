import numpy as np
import pytest

from leo.analysis.research.tone_nuisance import remove_stationary_tone


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("frequency", [-1198123, -234567, 173123, 1198999])
@pytest.mark.parametrize("amplitude", [0.5, 2, 6])
def test_stationary_tone_is_removed_without_modifying_input(rate, frequency, amplitude):
    rng = np.random.default_rng(572)
    noise = rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50)
    values = noise + amplitude * np.exp(2j * np.pi * frequency * np.arange(len(noise)) / rate)
    original = values.copy()
    residual, fit = remove_stationary_tone(values, rate)
    np.testing.assert_array_equal(values, original)
    assert fit.applied
    assert abs(fit.frequency_hz - frequency) < 10
    assert np.mean(np.abs(residual - noise) ** 2) < 0.01 * amplitude**2
    assert np.vdot(residual, residual).real <= np.vdot(values, values).real


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_noise_and_zero_are_unchanged(rate):
    rng = np.random.default_rng(59)
    for values in (
        np.zeros(rate // 50),
        rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50),
    ):
        residual, fit = remove_stationary_tone(values, rate)
        assert not fit.applied
        np.testing.assert_array_equal(residual, values)


def test_rejects_invalid_geometry():
    with pytest.raises(ValueError):
        remove_stationary_tone(np.zeros(10), 5000000)
