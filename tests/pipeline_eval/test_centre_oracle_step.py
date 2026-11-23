import numpy as np
from scipy.optimize import lsq_linear

from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.continuous_curve_fit import phase_frequency_from_states
from reports.ALGO08.v3 import centre_oracle_step as trial


def test_radial_gradient_matches_projection_in_offered_coordinates():
    region = SearchRegion((37.9, -122.5))
    observer, jacobian = trial.observer_geometry(region)
    satellite = observer + np.array([[400., 600., 700.], [500., -400., 600.]])
    velocity = np.array([[7.1, 1., -.6], [-3.1, 5., -.3]])
    tangent = trial.frequency_jacobian(satellite, velocity, observer, jacobian)
    delta = .001
    columns = []
    for axis in np.eye(2) * delta:
        ahead = phase_frequency_from_states(satellite, velocity, *region.latlon(axis))[0]
        behind = phase_frequency_from_states(satellite, velocity, *region.latlon(-axis))[0]
        columns.append((ahead - behind) / (2 * delta))
    np.testing.assert_allclose(tangent, np.column_stack(columns), atol=1e-6)


def test_schur_step_matches_joint_fit_on_the_box_face():
    gradient = np.array([[3., 1.], [1., -2.], [2., 3.], [-1., 2.]])
    terms = np.array([[12., -2.], [1., 8.], [-4., 1.], [2., -2.]])
    raw = gradient @ np.array([7., 2.5]) + terms @ np.array([1.5, -2.])
    step, _, nuisance, values = trial.fit_once(raw, terms, gradient, 2.)

    design = np.vstack((np.column_stack((gradient, terms)),
                        np.column_stack((np.zeros((2, 2)), np.eye(2)))))
    closed = lsq_linear(design, np.r_[raw, 0., 0.],
                        bounds=([-2., -2., -np.inf, -np.inf], [2., 2., np.inf, np.inf]))
    np.testing.assert_allclose(np.r_[step, nuisance], closed.x, atol=1e-9)
    assert np.all(values > 0)
    assert np.max(np.abs(step)) == 2.


def test_held_rows_take_last_fifth_and_keep_singletons_in_training():
    groups = np.repeat([0, 2, 3, 5], [1, 2, 5, 6])
    np.testing.assert_array_equal(np.flatnonzero(trial.train_test(groups)), [2, 7, 12, 13])
