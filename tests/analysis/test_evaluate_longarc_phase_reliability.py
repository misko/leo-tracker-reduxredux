import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).parents[2] / "tools/research/evaluate_longarc_phase_reliability.py"
SPEC = importlib.util.spec_from_file_location("phase_reliability", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_normalized_likelihood_penalizes_unneeded_scale():
    residual = np.zeros(10)
    assert MODULE.normalized_nll(residual, 250) < MODULE.normalized_nll(residual, 1000)


def test_random_folds_mix_each_temporal_stratum():
    strata = np.repeat(np.arange(3), 6)
    eligible = np.ones(18, dtype=bool)
    folds = MODULE.stratified_random_folds(strata, eligible)
    for stratum in range(3):
        assert set(folds[strata == stratum]) == {0, 1, 2}
    assert not np.array_equal(folds, np.tile(np.arange(3), 6))


def test_outer_held_measurements_cannot_change_uncertainty_configuration():
    residuals = [np.asarray([100.0 + index * 10]) for index in range(8)]
    features = np.linspace(0.1, 0.9, 8)
    folds = np.asarray([0, -1, 1, -1, 2, -1, 0, -1])
    first = MODULE.select_config(residuals, features, folds, (0.3, 0.8))
    for index in np.flatnonzero(folds < 0):
        residuals[index] = np.asarray([1e12])
        features[index] = -1e12
    assert MODULE.select_config(residuals, features, folds, (0.3, 0.8)) == first


def test_feature_model_contains_large_uniform_scale_null():
    residuals = [np.asarray([1000.0]) for _ in range(6)]
    features = np.asarray([0.1, 0.9] * 3)
    folds = np.asarray([0, 0, 1, 1, 2, 2])
    result = MODULE.select_config(residuals, features, folds, (0.5,))
    assert result["good_sigma_hz"] == result["bad_sigma_hz"] == 1000.0
