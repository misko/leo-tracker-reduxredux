import numpy as np
from numpy.testing import assert_allclose
import pytest

from leo.analysis.localization_v3.predictive_linear import predictive_residual
from tools.pipeline_eval.variants.algo08_grid_triangular import triangular_prediction


@pytest.mark.parametrize("width", (8, 9, 65, 66))
def test_triangular_prediction_preserves_predictive_likelihood(width):
    rng = np.random.default_rng(27)
    curved = rng.normal(size=(width + 10, width))
    gram = np.eye(width) + curved.T @ curved
    design = rng.normal(size=(12, width))
    raw = rng.normal(scale=400, size=len(design))
    sigma = np.linspace(20., 60., len(design))
    groups = np.arange(len(design)) // 4
    expected = predictive_residual(raw, design, gram, sigma, groups)
    trial = triangular_prediction(raw, design, gram, sigma, groups)
    assert set(trial) == set(expected)
    for key, value in expected.items():
        if isinstance(value, (np.ndarray, float)):
            assert_allclose(trial[key], value, rtol=2e-12, atol=1e-12, err_msg=key)
        else:
            assert trial[key] == value


def test_triangular_prediction_keeps_the_original_validation_and_spd_gate():
    args = (np.ones(4), np.ones((4, 3)), np.eye(3), np.full(4, 80.))
    with pytest.raises(ValueError, match="integer new-curve groups"):
        triangular_prediction(*args, np.arange(4, dtype=float))
    raw, design, gram, sigma = args
    with pytest.raises(np.linalg.LinAlgError, match="positive definite"):
        triangular_prediction(raw, design, -gram, sigma, np.arange(4))
