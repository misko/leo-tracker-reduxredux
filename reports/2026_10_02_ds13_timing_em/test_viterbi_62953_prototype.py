import numpy as np

from viterbi_62953_prototype import huber, viterbi_peak_path


def test_huber_is_quadratic_near_zero_and_linear_in_the_tail():
    np.testing.assert_allclose(huber([0.0, 0.5, 1.0, 2.0]), [0.0, 0.125, 0.5, 1.5])


def test_zero_continuity_weight_matches_independent_conditional_map():
    posterior = np.array(
        [
            [0.50, 0.01],
            [0.45, 0.01],
            [0.35, 0.01],
            [0.60, 0.01],
        ]
    )
    path = viterbi_peak_path(
        [np.array([0, 1]), np.array([2, 3])],
        posterior,
        residual_hz=np.array([-30.0, 80.0, -25.0, 85.0]),
        column=0,
        group_support=np.array([0.95, 0.95]),
        continuity_weight=0.0,
    )
    np.testing.assert_array_equal(path, [0, 3])


def test_continuity_can_prefer_coherent_path_over_second_local_map():
    posterior = np.array(
        [
            [0.50, 0.01],
            [0.45, 0.01],
            [0.35, 0.01],
            [0.60, 0.01],
        ]
    )
    path = viterbi_peak_path(
        [np.array([0, 1]), np.array([2, 3])],
        posterior,
        residual_hz=np.array([-30.0, 80.0, -25.0, 85.0]),
        column=0,
        group_support=np.array([0.95, 0.95]),
        continuity_weight=2.0,
        transition_scale_hz=50.0,
    )
    np.testing.assert_array_equal(path, [1, 3])
