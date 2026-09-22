import numpy as np

from leo.analysis.research.paired_receiver_geometry import (
    PairedDopplerFactor,
    differential_doppler_upper_bound_hz,
    score_paired_doppler_factor,
    score_paired_states,
)


def _factor(receiver, visit, training, observed):
    return PairedDopplerFactor(
        observed_hz=np.asarray(observed, dtype=float),
        receiver_id=np.asarray(receiver),
        visit_id=np.asarray(visit),
        training=np.asarray(training, dtype=bool),
        pairing_authority="fixture-exact-pair-membership",
    )


def test_receiver_constant_offsets_cancel_without_touching_heldout_selection():
    factor = _factor(
        [0, 1, 0, 1, 0, 1, 0, 1],
        [0, 0, 1, 1, 2, 2, 3, 3],
        [1, 1, 1, 1, 1, 1, 0, 0],
        [110, -85, 120, -75, 130, -65, 140, -55],
    )
    prediction = np.asarray(
        [
            [10, 10, 20, 20, 30, 30, 40, 40],
            [0, 0, 30, 30, 10, 10, 80, 80],
        ],
        dtype=float,
    )
    result = score_paired_doppler_factor(factor, prediction, sigma_hz=5.0)

    assert result["training_selected_candidate"] == 0
    np.testing.assert_allclose(result["receiver_offset_hz"][0], [100, -95])
    np.testing.assert_allclose(result["visit_weight"], 0.5)


def test_simultaneous_copy_does_not_double_position_information():
    single = _factor(
        [0, 0, 0, 0],
        [0, 1, 2, 3],
        [1, 1, 1, 0],
        [0, 0, 0, 0],
    )
    paired = _factor(
        [0, 1, 0, 1, 0, 1, 0, 1],
        [0, 0, 1, 1, 2, 2, 3, 3],
        [1, 1, 1, 1, 1, 1, 0, 0],
        np.zeros(8),
    )
    single_jacobian = np.asarray([[[0.0], [1.0], [3.0], [6.0]]])
    paired_jacobian = np.repeat(single_jacobian, 2, axis=1)
    one = score_paired_doppler_factor(
        single, np.zeros((1, 4)), sigma_hz=1.0, position_jacobian_hz_km=single_jacobian
    )
    two = score_paired_doppler_factor(
        paired, np.zeros((1, 8)), sigma_hz=1.0, position_jacobian_hz_km=paired_jacobian
    )

    np.testing.assert_allclose(
        one["nuisance_projected_position_information"],
        two["nuisance_projected_position_information"],
    )


def test_receiver_label_swap_leaves_candidate_scores_unchanged():
    left = _factor(
        [0, 1, 0, 1, 0, 1],
        [0, 0, 1, 1, 2, 2],
        [1, 1, 1, 1, 0, 0],
        [10, 110, 20, 120, 30, 130],
    )
    right = _factor(
        [1, 0, 1, 0, 1, 0],
        [0, 0, 1, 1, 2, 2],
        [1, 1, 1, 1, 0, 0],
        [10, 110, 20, 120, 30, 130],
    )
    prediction = np.asarray([[0, 0, 10, 10, 20, 20]], dtype=float)
    a = score_paired_doppler_factor(left, prediction, sigma_hz=2.0)
    b = score_paired_doppler_factor(right, prediction, sigma_hz=2.0)
    np.testing.assert_allclose(a["training_log_likelihood"], b["training_log_likelihood"])
    np.testing.assert_allclose(a["heldout_log_likelihood"], b["heldout_log_likelihood"])


def test_nonoverlapping_receiver_visits_add_temporal_shape_information():
    factor = _factor(
        [0, 0, 0, 1, 1, 1, 0, 1],
        np.arange(8),
        [1, 1, 1, 1, 1, 1, 0, 0],
        np.zeros(8),
    )
    jacobian = np.asarray(
        [
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [2.0, 0.0],
                [0.0, 0.0],
                [0.0, 1.0],
                [0.0, 2.0],
                [3.0, 0.0],
                [0.0, 3.0],
            ]
        ]
    )
    result = score_paired_doppler_factor(
        factor, np.zeros((1, 8)), sigma_hz=1.0, position_jacobian_hz_km=jacobian
    )
    eigenvalues = result["nuisance_projected_information_eigenvalues"][0]

    assert np.all(eigenvalues > 0)


def test_visit_cannot_cross_train_heldout_boundary():
    try:
        _factor([0, 1, 0, 1], [0, 0, 1, 1], [1, 0, 1, 0], np.zeros(4))
    except ValueError as error:
        assert "training boundary" in str(error)
    else:
        raise AssertionError("leaking paired visit was accepted")


def test_conflicting_receiver_identities_are_visible_in_independent_ablation():
    factor = _factor(
        [0, 0, 1, 1, 0, 1],
        [0, 1, 2, 3, 4, 5],
        [1, 1, 1, 1, 0, 0],
        [0, 10, 100, 130, 20, 150],
    )
    predictions = np.asarray(
        [
            [0, 10, 0, 10, 20, 20],
            [100, 130, 100, 130, 150, 150],
        ]
    )
    result = score_paired_doppler_factor(factor, predictions, sigma_hz=1.0)

    np.testing.assert_array_equal(result["independent_receiver_selected_candidate"], [0, 1])
    assert result["shared_minus_independent_training_log_score"] < 0


def test_lt3d001a_nominal_mechanical_baseline_has_sub_hertz_doppler_scale():
    bound = differential_doppler_upper_bound_hz(11.2e9, 0.080, 8_000.0, 500_000.0)
    assert np.isclose(bound, 0.0475, rtol=0.01)


def test_list_inputs_are_canonicalized_before_numerical_use():
    factor = PairedDopplerFactor(
        observed_hz=[0.0, 1.0, 2.0, 3.0],
        receiver_id=[0, 0, 0, 0],
        visit_id=[0, 1, 2, 3],
        training=[True, True, False, False],
        pairing_authority="fixture",
    )
    result = score_paired_doppler_factor(factor, np.zeros((1, 4)), sigma_hz=1.0)
    assert result["training_selected_candidate"] == 0


def test_state_projection_matches_direct_visit_factor_mixture():
    factor = _factor(
        [0, 1, 0, 1, 0, 1],
        [0, 0, 1, 1, 2, 2],
        [1, 1, 1, 1, 0, 0],
        np.zeros(6),
    )
    position = np.asarray([[[7000.0 + index, 100.0, 200.0] for index in range(6)]])
    velocity = np.asarray([[[0.0, 7.0, 0.1] for _ in range(6)]])

    class Grid:
        ecef_km = np.asarray([[6378.0, 0.0, 0.0]])
        up = np.asarray([[1.0, 0.0, 0.0]])

    delta = position[0] - Grid.ecef_km[0]
    prediction = (
        -11_200_000_000.0
        / 299_792.458
        * np.sum(delta * velocity[0], axis=1)
        / np.linalg.norm(delta, axis=1)
    )
    direct = score_paired_doppler_factor(
        factor, prediction[None, :], sigma_hz=250.0, effective_count=6.0
    )
    null = score_paired_doppler_factor(
        factor, np.zeros((1, 6)), sigma_hz=30_000.0, effective_count=6.0
    )
    candidate = direct["training_log_likelihood"][0] + np.log(0.5 / 1)
    null_value = null["training_log_likelihood"][0] + np.log(0.5)
    expected = np.logaddexp(candidate, null_value) - null_value
    projected = score_paired_states(factor, position, velocity, Grid(), 1)

    np.testing.assert_allclose(projected["train_logbf"], [expected])
