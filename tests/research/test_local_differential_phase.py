import numpy as np

from tools.research.replay_local_differential_phase import circular_fit, circular_score


def test_affine_circular_phase_predicts_random_held_groups():
    t = np.arange(20, dtype=float) * 0.001
    phase = np.angle(np.exp(1j * (2.8 + 19.0 * t)))
    train = np.random.default_rng(20260929).permutation(20)[:10]
    fit = circular_fit(t[train], phase[train])
    score = circular_score(t, phase, fit)
    assert score["rms_rad"] < 1e-12
    assert score["resultant"] > 1 - 1e-12


def test_circular_score_wraps_residuals():
    score = circular_score(np.array([0.0]), np.array([-np.pi + 0.1]), (np.pi, 0.0))
    assert np.isclose(score["rms_rad"], 0.1)
