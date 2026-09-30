import numpy as np
from header_state_transfer import predict


def test_ridge_prediction_transfers_known_mapping():
    rng = np.random.default_rng(91)
    x, target = rng.normal(size=(100, 4)), rng.normal(size=(20, 4))
    weights = rng.normal(size=(4, 12))
    y = x @ weights + 3
    predicted = predict(x, y, target)
    assert np.mean(abs(predicted - (target @ weights + 3))) < 0.08


def test_constant_targets_retain_training_intercept():
    rng = np.random.default_rng(81)
    x, target = rng.normal(size=(12, 6)), rng.normal(size=(20, 6))
    assert np.allclose(predict(x, np.full((12, 3), -2.0), target), -2)
