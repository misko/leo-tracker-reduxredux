import numpy as np

from tools.pipeline_eval.variants import differential_gate


def test_common_cfo_rotation_preserves_phase_score_at_all_epochs():
    rng = np.random.default_rng(5107)
    template = rng.normal(size=44) + 1j * rng.normal(size=44)
    iq = rng.normal(size=180) + 1j * rng.normal(size=180)
    iq[23:67] += 8 * template
    geometry = (np.array([0]), np.array([0]), 44, 120)
    base = differential_gate.lag_products(iq, template, *geometry)
    shifted = iq * np.exp(2j * np.pi * 0.073 * np.arange(len(iq)))
    other = differential_gate.lag_products(shifted, template, *geometry)
    np.testing.assert_allclose(
        differential_gate.phase_score(base), differential_gate.phase_score(other), atol=0.006
    )
    assert differential_gate.proposals(differential_gate.phase_score(base))[0] == 23


def test_odd_lag_zero_has_no_surrogate_bound_for_a_coherent_half_aperture():
    template = np.ones(44)
    values = template.copy()
    values[1::2] = 0
    score = np.vdot(template, values) / (np.linalg.norm(template) * np.linalg.norm(values))
    assert score > 0.70
    lagged = differential_gate.lag_products(values, template, np.array([0]), np.array([0]), 44, 1)
    assert differential_gate.phase_score(lagged).item() == 0


def test_proposal_exclusion_is_circular_and_off_lattice_starts_are_tested():
    scores = np.zeros(60)
    scores[[0, 59, 17, 31]] = [8, 7, 6, 5]
    assert differential_gate.proposals(scores).tolist() == [0, 17, 31]
