import numpy as np
import pytest
from grouped_likelihood import DEFAULT_ALIAS_HZ, prepare_grouped_likelihood
from track_likelihood import prepare_track_grouped_likelihood


def test_complete_data_precision_conserves_posterior_signal_mass():
    measured = np.array([3.0, 5.0, 10.0, 15.0])
    predicted = np.array([[2.0, 8.0], [4.0, 9.0], [7.0, 11.0], [20.0, 12.0]])
    visible = np.ones((4, 2), dtype=bool)
    visible[1, 0] = False
    prepared = prepare_track_grouped_likelihood(
        measured, [9, 2, 9, 4], row_weights=[1, 1, 3, 1], anchors=[np.array([9, 4])]
    )
    options = {
        "sigma_hz": 20.0,
        "raw_satellite_mass": np.array([0.4, 0.4]),
        "raw_background_mass": 0.2,
        "anchor_satellite_mass": np.array([[0.4, 0.4]]),
        "anchor_unknown_mass": np.array([0.2]),
    }
    result = prepared.evaluate(
        predicted, visible, **options, return_gradient=True, return_precision=True
    )
    precision = result["prediction_precision"]
    assert precision.shape == predicted.shape
    assert np.all(precision >= 0)
    assert precision[1, 0] == 0
    np.testing.assert_allclose(precision.sum(axis=0) * 20**2, result["satellite_support"])
    np.testing.assert_allclose(
        result["prediction_gradient"], precision * (measured[:, None] - predicted)
    )
    precision_only = prepared.evaluate(predicted, visible, **options, return_precision=True)
    np.testing.assert_array_equal(precision_only["prediction_precision"], precision)
    assert "prediction_gradient" not in precision_only


def test_per_column_sigma_matches_scalar_and_scales_precision_by_column():
    measured = np.array([3.0, 5.0, 10.0, 15.0])
    predicted = np.array([[2.0, 8.0], [4.0, 9.0], [7.0, 11.0], [20.0, 12.0]])
    visible = np.ones((4, 2), dtype=bool)
    prepared = prepare_track_grouped_likelihood(
        measured, [9, 2, 9, 4], row_weights=[1, 1, 3, 1], anchors=[np.array([9, 4])]
    )
    options = {
        "raw_satellite_mass": np.array([0.4, 0.4]),
        "raw_background_mass": 0.2,
        "anchor_satellite_mass": np.array([[0.4, 0.4]]),
        "anchor_unknown_mass": np.array([0.2]),
    }
    scalar = prepared.evaluate(
        predicted, visible, sigma_hz=80.0, return_gradient=True, return_precision=True, **options
    )
    vector = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=np.array([80.0, 80.0]),
        return_gradient=True,
        return_precision=True,
        **options,
    )
    assert vector["total_log_likelihood"] == pytest.approx(
        scalar["total_log_likelihood"], abs=2e-14
    )
    np.testing.assert_allclose(vector["prediction_gradient"], scalar["prediction_gradient"])
    np.testing.assert_allclose(vector["prediction_precision"], scalar["prediction_precision"])

    sigmas = np.array([40.0, 160.0])
    varied = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=sigmas,
        return_gradient=True,
        return_precision=True,
        **options,
    )
    expected = finite_difference(
        prepared, predicted, visible, {"sigma_hz": sigmas, **options}
    )
    np.testing.assert_allclose(varied["prediction_gradient"], expected, rtol=2e-6, atol=2e-10)
    np.testing.assert_allclose(
        varied["prediction_precision"].sum(axis=0) * sigmas**2,
        varied["satellite_support"],
    )


def finite_difference(prepared, predicted, visible, options, step=1e-3):
    gradient = np.empty_like(predicted)
    for row, satellite in np.ndindex(predicted.shape):
        lower = predicted.copy()
        upper = predicted.copy()
        lower[row, satellite] -= step
        upper[row, satellite] += step
        lower_value = prepared.evaluate(lower, visible, **options)["total_log_likelihood"]
        upper_value = prepared.evaluate(upper, visible, **options)["total_log_likelihood"]
        gradient[row, satellite] = (upper_value - lower_value) / (2 * step)
    return gradient


def test_track_likelihood_gradient_matches_finite_difference_in_original_order():
    measured = np.array([100.0, -250.0, 40.0, 800.0, -500.0, 20.0])
    group = np.array([9, 2, 9, 7, 5, 2])
    row_weights = np.array([1.0, 0.5, 2.0, 1.5, 1.0, 3.0])
    predicted = np.array(
        [
            [90.0, 400.0, -200.0],
            [-300.0, -100.0, 500.0],
            [10.0, 50.0, 30.0],
            [750.0, 1000.0, -600.0],
            [-450.0, 20.0, -800.0],
            [80.0, -10.0, 250.0],
        ]
    )
    visible = np.array(
        [
            [True, True, False],
            [True, False, True],
            [True, True, True],
            [False, True, True],
            [True, True, False],
            [True, True, True],
        ]
    )
    prepared = prepare_track_grouped_likelihood(
        measured,
        group,
        row_weights=row_weights,
        anchors=[np.array([9, 5]), np.array([2])],
    )
    options = {
        "sigma_hz": 220.0,
        "raw_satellite_mass": np.array([0.45, 0.0, 0.35]),
        "raw_background_mass": 0.2,
        "anchor_satellite_mass": np.array([[0.5, 0.2, 0.1], [0.1, 0.35, 0.35]]),
        "anchor_unknown_mass": np.array([0.2, 0.2]),
        "track_contamination": np.array([0.15, 0.3]),
    }
    result = prepared.evaluate(predicted, visible, return_gradient=True, **options)
    expected = finite_difference(prepared, predicted, visible, options)
    np.testing.assert_allclose(result["prediction_gradient"], expected, rtol=3e-6, atol=3e-10)
    np.testing.assert_array_equal(result["prediction_gradient"][~visible], 0.0)
    assert "prediction_gradient" not in prepared.evaluate(predicted, visible, **options)
    assert np.sum(result["satellite_support"]) + result["null_support"] == pytest.approx(
        len(np.unique(group))
    )
    assert result["baseline_log_likelihood"] + np.sum(
        result["raw_group_log_bayes_factor"]
    ) + np.sum(result["track_log_bayes_factor"]) == pytest.approx(result["total_log_likelihood"])


def test_no_anchor_matches_existing_raw_group_likelihood_and_gradient():
    measured = np.array([10.0, 30.0, -20.0, 90.0])
    group = np.array([4, 1, 4, 8])
    row_weights = np.array([1.0, 2.0, 0.5, 1.0])
    predicted = np.array([[0.0, 100.0], [20.0, -100.0], [-10.0, 40.0], [120.0, 80.0]])
    visible = np.array([[True, True], [True, False], [False, True], [True, True]])
    background_mass = 0.2
    satellite_weights = np.array([0.3, 0.7])
    existing = prepare_grouped_likelihood(measured, group, row_weights=row_weights).evaluate(
        predicted,
        visible,
        sigma_hz=180.0,
        satellite_weights=satellite_weights,
        background_mass=background_mass,
        return_gradient=True,
    )
    track = prepare_track_grouped_likelihood(
        measured, group, row_weights=row_weights, anchors=[]
    ).evaluate(
        predicted,
        visible,
        sigma_hz=180.0,
        raw_satellite_mass=(1 - background_mass) * satellite_weights,
        raw_background_mass=background_mass,
        anchor_satellite_mass=np.empty((0, 2)),
        anchor_unknown_mass=np.empty(0),
        return_gradient=True,
    )
    np.testing.assert_array_equal(track["group_values"], existing["group_values"])
    assert track["total_log_likelihood"] == pytest.approx(
        existing["total_log_likelihood"], abs=2e-14
    )
    np.testing.assert_allclose(track["satellite_support"], existing["satellite_support"])
    assert track["null_support"] == pytest.approx(existing["null_support"])
    np.testing.assert_allclose(
        track["prediction_gradient"], existing["prediction_gradient"], rtol=0, atol=2e-14
    )


@pytest.mark.parametrize(
    ("anchors", "message"),
    [
        ([np.array([2, 2])], "duplicate"),
        ([np.array([2, 5]), np.array([5])], "multiple anchors"),
        ([np.array([99])], "unknown"),
    ],
)
def test_anchor_partition_rejects_duplicate_or_unknown_groups(anchors, message):
    with pytest.raises(ValueError, match=message):
        prepare_track_grouped_likelihood(
            [0.0, 1.0, 2.0],
            [2, 5, 8],
            row_weights=[1.0, 1.0, 1.0],
            anchors=anchors,
        )


def test_whole_track_identity_cannot_switch_satellite_between_groups():
    measured = np.array([0.0, 4000.0])
    predicted = np.array([[0.0, 4000.0], [0.0, 4000.0]])
    visible = np.ones_like(predicted, dtype=bool)
    raw = prepare_track_grouped_likelihood(
        measured, [10, 20], row_weights=[1.0, 1.0], anchors=[]
    ).evaluate(
        predicted,
        visible,
        sigma_hz=100.0,
        raw_satellite_mass=np.array([0.49, 0.49]),
        raw_background_mass=0.02,
        anchor_satellite_mass=np.empty((0, 2)),
        anchor_unknown_mass=np.empty(0),
    )
    anchored = prepare_track_grouped_likelihood(
        measured,
        [10, 20],
        row_weights=[1.0, 1.0],
        anchors=[np.array([10, 20])],
    ).evaluate(
        predicted,
        visible,
        sigma_hz=100.0,
        raw_satellite_mass=np.array([0.49, 0.49]),
        raw_background_mass=0.02,
        anchor_satellite_mass=np.array([[0.49, 0.49]]),
        anchor_unknown_mass=np.array([0.02]),
        track_contamination=0.01,
    )
    assert anchored["total_log_likelihood"] < raw["total_log_likelihood"]
    np.testing.assert_allclose(
        np.sum(anchored["track_identity_responsibility"], axis=1)
        + anchored["track_unknown_responsibility"],
        1.0,
    )
    assert anchored["track_identity_responsibility"][0, 0] == pytest.approx(
        anchored["track_identity_responsibility"][0, 1]
    )


def test_invisible_anchor_groups_use_contamination_null_and_have_zero_gradient():
    measured = np.array([0.0, 20.0, -30.0])
    predicted = np.full((3, 2), np.nan)
    visible = np.zeros((3, 2), dtype=bool)
    contamination = 0.25
    prepared = prepare_track_grouped_likelihood(
        measured,
        [4, 7, 9],
        row_weights=[1.0, 1.0, 1.0],
        anchors=[np.array([4, 7, 9])],
    )
    result = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=200.0,
        raw_satellite_mass=np.array([0.4, 0.4]),
        raw_background_mass=0.2,
        anchor_satellite_mass=np.array([[1.0, 0.0]]),
        anchor_unknown_mass=np.array([0.0]),
        track_contamination=contamination,
        return_gradient=True,
    )
    expected = 3 * (np.log(contamination) - np.log(DEFAULT_ALIAS_HZ))
    assert result["total_log_likelihood"] == pytest.approx(expected)
    np.testing.assert_array_equal(result["satellite_support"], 0.0)
    assert result["null_support"] == pytest.approx(3.0)
    np.testing.assert_array_equal(result["group_null_responsibility"], 1.0)
    np.testing.assert_array_equal(result["prediction_gradient"], 0.0)
