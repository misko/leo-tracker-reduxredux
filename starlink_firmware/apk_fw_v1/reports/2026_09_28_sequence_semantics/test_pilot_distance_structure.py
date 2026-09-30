import numpy as np
from pilot_distance_structure import soft_correlations


def test_shared_varying_symbols_exceed_independent_and_constants_are_undefined():
    rng = np.random.default_rng(32)
    phase = rng.uniform(-np.pi, np.pi, (1000, 4))
    a = np.exp(1j * phase)
    b = np.exp(1j * (phase + rng.normal(0, .1, phase.shape)))
    assert np.min(soft_correlations(a, b)) > .98
    assert np.max(abs(soft_correlations(a, rng.permutation(b)))) < .15
    assert np.isnan(soft_correlations(np.ones((10, 2)), np.ones((10, 2)))).all()


def test_amplitude_scaling_does_not_change_phase_metric():
    rng = np.random.default_rng(5)
    a = rng.normal(size=(50, 4)) + 1j * rng.normal(size=(50, 4))
    b = rng.normal(size=(50, 4)) + 1j * rng.normal(size=(50, 4))
    assert np.allclose(soft_correlations(a, b), soft_correlations(10 * a, .2 * b))
