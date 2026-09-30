import numpy as np
from neighbor_prediction import predict


def test_predict_heldout_relationship_beats_mean_and_wrong_pairing():
    rng = np.random.default_rng(301)
    x = rng.normal(size=(100, 4))
    y = x[:, 0] * 3 - x[:, 1] + 7
    p = predict(x[:60], y[:60], x[60:])
    wrong = predict(x[:60], y[:60], x[60:], shift=13)
    assert np.mean((y[60:] - p) ** 2) < np.mean((y[60:] - wrong) ** 2)
    assert np.mean((y[60:] - p) ** 2) < np.mean((y[60:] - y[:60].mean()) ** 2)


def test_constant_features_produce_training_mean():
    x = np.ones((20, 4))
    y = np.arange(20.)
    assert np.allclose(predict(x, y, x[:3]), y.mean())
