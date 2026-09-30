import numpy as np
from ds9_t_quadrature import predict, reductions, signs


def test_fixed_state_sign_period_and_prediction_generalization():
    np.testing.assert_array_equal(signs([0], [516, 540], [2, 17]), np.ones((1, 2, 2)))
    np.testing.assert_array_equal(signs([17], [516, 540], [2]),
                                  signs([17], [516, 540], [17]))
    rng = np.random.default_rng(44)
    train = rng.choice([-1., 1.], (22, 2, 4))
    held = rng.choice([-1., 1.], (23, 2, 4))
    prediction, baseline = predict(train, 3 + 2 * train, held)
    np.testing.assert_allclose(prediction, 3 + 2 * held)
    scores = reductions(3 + 2 * held, prediction, baseline)
    assert scores[0] == 1 and scores[1:].max() < 1
    constant = np.ones_like(train)
    p, b = predict(constant, train, held)
    np.testing.assert_allclose(p, np.broadcast_to(b, held.shape))
