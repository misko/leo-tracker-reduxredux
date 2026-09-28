import numpy as np
from header_common_phase import correct


def test_targets_cannot_change_reference_phase_estimate():
    rng = np.random.default_rng(82)
    bins = np.arange(496, 508)
    phase = np.linspace(-1, 1, 100)
    z = np.exp(1j * phase[:, None]) * np.ones((100, len(bins)))
    z[:, bins == 498] *= rng.choice([-1, 1], size=(100, 1))
    z[:, bins == 503] *= rng.choice([-1, 1], size=(100, 1))
    corrected, vector, refs = correct(z, bins, np.arange(50))
    assert not np.isin(refs, [498, 503]).any()
    changed = z.copy()
    changed[:, np.isin(bins, [498, 503])] *= 1j
    _, other, _ = correct(changed, bins, np.arange(50))
    np.testing.assert_allclose(vector, other)
    # Rotation is anchored to discovery reference mean, not absolute truth.
    expected = np.angle(np.exp(1j * phase[:50]).mean())
    np.testing.assert_allclose(abs((corrected * np.exp(-1j * expected)).imag), 0, atol=1e-12)
