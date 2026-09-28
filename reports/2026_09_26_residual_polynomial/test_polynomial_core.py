import numpy as np
import pytest
from polynomial_core import fit_residual


@pytest.mark.parametrize('degree', range(4))
def test_exact_polynomial(degree):
    t = np.linspace(40, 80, 40)
    mask = np.arange(40) % 3 != 0
    y = sum((t-60)**k * .1**k for k in range(degree+1))
    result = fit_residual(t, y, mask, degree)
    assert result['evaluation_rms_hz'] < 1e-10


def test_evaluation_values_do_not_change_fit():
    t = np.arange(20.)
    mask = np.arange(20) % 2 == 0
    y = np.sin(t)
    original = fit_residual(t, y, mask, 3)
    y[~mask] += 10000
    changed = fit_residual(t, y, mask, 3)
    assert original['coefficients_scaled_hz'] == changed['coefficients_scaled_hz']
    assert original['training_rms_hz'] == changed['training_rms_hz']
    assert changed['evaluation_rms_hz'] > 9000


def test_invalid_partitions():
    with pytest.raises(ValueError):
        fit_residual(np.arange(5.), np.zeros(5), np.ones(5, bool), 1)
    with pytest.raises(ValueError):
        fit_residual(np.ones(8), np.zeros(8), np.arange(8) < 5, 3)
    with pytest.raises(ValueError):
        fit_residual(np.arange(6.), np.zeros(6), np.arange(6) < 3, 2)
