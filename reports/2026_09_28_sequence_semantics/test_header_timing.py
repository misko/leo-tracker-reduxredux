import numpy as np
from header_timing import counter_models, fit_positions


def test_binary_counter_uses_actual_ticks_with_gaps():
    ticks = np.arange(1000) * 3
    models, descriptions = counter_models(ticks, max_bit=4)
    idx = descriptions.index(dict(bit=3, offset=5))
    expected = 2 * (((ticks + 5) >> 3) & 1) - 1
    np.testing.assert_array_equal(models[:, idx], expected)
    rows = fit_positions(expected[:, None], np.ones((1000, 1), bool), ticks)
    assert rows[0]["test_accuracy"] == 1
    assert rows[0]["validation_accuracy"] == 1


def test_counter_fit_does_not_learn_test_polarity():
    ticks = np.arange(1000)
    bits = (2 * ((ticks >> 2) & 1) - 1)[:, None]
    bits[800:] *= -1
    rows = fit_positions(bits, np.ones_like(bits, bool), ticks)
    assert rows[0]["validation_accuracy"] == 1
    assert rows[0]["test_accuracy"] == 0
