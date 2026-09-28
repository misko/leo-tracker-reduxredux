import numpy as np
from rectangle_sequence_test import fit_predict


def test_prediction_does_not_fit_held_positions():
    rng = np.random.default_rng(60)
    book = rng.choice([-1, 1], size=(60, 114)).astype(np.int16)
    observed = book[[5, 17]].copy()
    observed[1] *= -1
    predicted, phases, polarity = fit_predict(observed, book, 28)
    np.testing.assert_array_equal(predicted, observed)
    np.testing.assert_array_equal(phases, [5, 17])
    observed[:, 28:] *= -1
    other, _, _ = fit_predict(observed, book, 28)
    np.testing.assert_array_equal(other, predicted)
