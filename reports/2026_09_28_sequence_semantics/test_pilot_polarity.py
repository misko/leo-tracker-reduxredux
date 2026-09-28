import numpy as np
from header_structure import lag_correlation
from pilot_polarity import pilot_reference


def test_pilots_preserve_polarity_through_full_phase_wraps():
    rng = np.random.default_rng(78)
    bits = rng.choice([-1, 1], (40, 60))
    phases = np.exp(1j * np.linspace(-5, 5, 40))
    signal = bits * phases[:, None] * np.exp(-0.25j * np.pi)
    pilots = np.broadcast_to(phases[:, None], (40, 16)).copy()
    corrected, coherence, _ = pilot_reference(signal, pilots)
    np.testing.assert_allclose(corrected.real, np.broadcast_to(bits, (2, 40, 60)), atol=1e-12)
    np.testing.assert_allclose(abs(coherence), 1)
    # A wrong polarity at one pilot edge must stay visible as a disagreement.
    pilots[:, 8:] *= -1
    corrected, _, _ = pilot_reference(signal, pilots)
    assert np.all(np.sign(corrected[0].real) != np.sign(corrected[1].real))


def test_lag_correlation_uses_valid_pairs_and_rejects_constant_sequences():
    x = np.tile([1, -1], 100)
    valid = np.ones(200, bool)
    assert np.isclose(lag_correlation(x, valid, 2), 1)
    assert np.isclose(lag_correlation(x, valid, 1), -1)
    assert lag_correlation(np.ones(200), valid, 2) == 0
    valid[:] = False
    assert lag_correlation(x, valid, 2) == 0
