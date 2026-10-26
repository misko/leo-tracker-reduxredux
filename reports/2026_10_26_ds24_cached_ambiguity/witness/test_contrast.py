import numpy as np
import inventory
from contrast import compare_backgrounds, adequacy


def test_missing_feasible_lists_do_not_invent_a_witness():
    row = dict(component='other', observation_ids=['w'], archived_own_label_evidence=[])
    result = inventory.classify(row, ['d'], {'c0': [], 'fitted_c': []})
    assert not result['eligible_potential_separate_owner']
    assert result['missing_feasibility_list_is_not_negative_evidence']
    assert not result['complete_alternative_feasibility_list_available']


def test_whole_owner_overlap_and_discovery_are_excluded_symmetrically():
    row = dict(component='other', observation_ids=['w'],
               archived_own_label_evidence=[dict(norad=68904)])
    assert inventory.classify(row, ['d'], {'c0': [], 'fitted_c': []})['eligible_potential_separate_owner']
    assert not inventory.classify(row, ['d'], {'c0': [], 'fitted_c': ['w']})['eligible_potential_separate_owner']
    assert not inventory.classify(dict(row, component=inventory.D), ['d'], {'c0': [], 'fitted_c': []})['eligible_potential_separate_owner']


def test_shared_lowrank_mode_mean_matches_joint_gaussian():
    covariance = np.array([[3., .5, .1], [.5, 2., .4], [.1, .4, 4.]])
    modes = np.array([[1., .2], [.1, -.8], [.4, .5]])
    raw = np.array([2., -1., .5])
    expected = modes.T @ np.linalg.solve(covariance + modes @ modes.T, raw)
    assert np.allclose(adequacy.mode_mean(raw, covariance, modes), expected, atol=1e-14)


def test_radio_mean_difference_sign_and_covariance_change():
    full = dict(raw=np.array([2., 3.]), covariance=np.eye(2), q=np.ones(2))
    cavity = dict(raw=np.array([5., 1.]), covariance=2 * np.eye(2), q=np.ones(2))
    result = compare_backgrounds(full, cavity)
    assert np.array_equal(result['full_minus_cavity_radio_mean_Hz'], [3., -2.])
    assert np.isclose(result['covariance_relative_Frobenius_change'], .5)
