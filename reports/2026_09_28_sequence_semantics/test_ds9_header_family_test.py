import numpy as np
from ds9_header_family_test import WORDS, predict


def test_unused_slots_cannot_change_fitted_phase_or_polarity():
    slots = np.arange(60).reshape(6, 10)
    values = WORDS[[7, 19]][:, slots].astype(complex)
    values[1] *= -1
    prediction, phase, polarity = predict(values, slots, WORDS)
    assert np.array_equal(prediction, values.real)
    changed = values.copy()
    changed[:, slots >= 30] *= -100
    _, phase2, polarity2 = predict(changed, slots, WORDS)
    assert np.array_equal(phase, phase2)
    assert np.array_equal(polarity, polarity2)
