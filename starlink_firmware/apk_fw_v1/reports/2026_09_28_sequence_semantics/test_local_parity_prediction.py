import numpy as np
from local_parity_prediction import codewords, predict


def test_parity_can_fix_weak_error_and_target_is_omitted():
    words = codewords(3, [([0, 1, 2], 0)])
    soft = np.array([[1.0, 1.0, 0.1]])
    assert np.array_equal(predict(soft, words) > 0, [[True, True, False]])
    before = predict(soft, words, True)[:, 2]
    soft[:, 2] = -100
    np.testing.assert_array_equal(predict(soft, words, True)[:, 2], before)


def test_unconstrained_omitted_bit_is_unresolved():
    words = codewords(3, [([0, 1], 0)])
    assert predict(np.array([[0.8, 0.7, 0.6]]), words, True)[0, 2] == 0
