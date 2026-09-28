import numpy as np
from region_phase_audit import WORDS, fit_halves


def test_evaluation_half_does_not_choose_phase_or_polarity():
    symbol = 11
    signs = -WORDS[17, (np.arange(1004) - 16 * symbol) % 60]
    valid = np.ones(1004, dtype=bool)
    baseline = fit_halves(signs, valid, symbol)
    assert baseline["phase"] == 17 and baseline["polarity"] == -1
    assert baseline["errors"] == [0, 0]
    signs[502:] *= -1
    changed = fit_halves(signs, valid, symbol)
    assert changed["phase"] == 17 and changed["polarity"] == -1
    assert changed["errors"] == [0, 502]
