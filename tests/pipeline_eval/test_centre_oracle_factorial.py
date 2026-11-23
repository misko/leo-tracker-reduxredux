from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def weights(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    from centre_oracle_factorial import effective_precision

    return effective_precision


def test_kept_dimensionless_precision_expands_over_original_hz_scales(weights):
    kept = np.array([0, 0, 2])
    precision = weights([.5, .2, .4], [2., 0., .25], kept)
    std_hz = np.array([80., 100., 140.])
    np.testing.assert_array_equal(precision, [1., 0., .1])
    reweighted_std = std_hz / np.sqrt(precision[kept])
    np.testing.assert_allclose(1 / reweighted_std**2, [1/80**2, 1/100**2, .1/140**2])


@pytest.mark.parametrize("tau", ([1., 0., 0.], [1., 1., 1.], [1., 0., np.inf]))
def test_fake_precisions_cannot_bind_to_a_different_support(weights, tau):
    with pytest.raises(ValueError, match="group precision"):
        weights([1., .5, 1.], tau, [0, 2])
