import numpy as np
from plot_all_glrt_orbit_residuals import observation_mask, residual_limits


def test_all_in_window_observations_included_without_association_input():
    actual = observation_mask([-1, 0, 100, 300, 301, 200], [0, 0, 0, 0, 0, 1], 0)
    np.testing.assert_array_equal(actual, [False, True, True, True, False, False])


def test_fixed_residual_axis_limits():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots()
    axis.scatter([10, 20], [-10000, 10000])
    residual_limits(axis)
    assert axis.get_ylim() == (-300, 300)
    assert axis.get_xlim() == (0, 300)
    plt.close(figure)
