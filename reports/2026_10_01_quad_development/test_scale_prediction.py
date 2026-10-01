import numpy as np
from scale_prediction import conditional, log_density


def test_conditional_equals_joint_minus_training():
    for d, q, dt, qt in ((7, 2., 14, 9.), (3, 40., 2, .1), (6, .001, 28, 120.)):
        expected = log_density(d+dt, q+qt, 3.+5.)-log_density(dt, qt, 5.)
        np.testing.assert_allclose(conditional(d, q, 3., dt, qt), expected, atol=1e-12)


def test_singleton_is_independent_control():
    assert conditional(7, 3., 2., 0, 0.) == log_density(7, 3., 2.)


def test_incompatible_training_energy_can_hurt():
    assert conditional(7, 1., 0., 70, 7000.) < log_density(7, 1., 0.)
