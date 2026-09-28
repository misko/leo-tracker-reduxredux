import numpy as np
from ds9_symbol_phase_probe import coherence, correction


def test_common_slow_phase_prediction_improves_other_pilots():
    phase = 0.6 * np.sin(np.arange(300) / 30)
    known = np.exp(1j * phase[:, None]) * np.ones((300, 4))
    corrected = known[:, 2:] * correction(known[:, :2])[:, None]
    assert coherence(corrected) > 0.999
    assert coherence(corrected) > coherence(known[:, 2:])
