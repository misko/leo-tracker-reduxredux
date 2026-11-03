import numpy as np
import pytest
from finite_set_group_mixture import GroupMixtureLikelihoodAdapter
from finite_set_likelihood import DEFAULT_ALIAS_HZ, prepare_finite_set_likelihood


def fixture(weight=0.8):
    measured = np.array([10.0, 260.0, 10.0 + DEFAULT_ALIAS_HZ, -370.0])
    prepared = prepare_finite_set_likelihood(measured, np.array([4, 4, 4, 8]))
    adapter = GroupMixtureLikelihoodAdapter(prepared, 0.25, narrow_weight=weight)
    predicted = np.array([[0.0, 300.0]] * 3 + [[0.0, -700.0]])
    options = dict(sigma_hz=200.0, satellite_weights=np.ones(2), background_mass=0.2)
    return adapter, predicted, np.ones_like(predicted, dtype=bool), options


@pytest.mark.parametrize("weight,width", [(0.0, 400.0), (1.0, 100.0)])
def test_component_endpoints_reproduce_finite_set(weight, width):
    adapter, predicted, visible, options = fixture(weight)
    actual = adapter.evaluate(
        predicted, visible, **options, return_gradient=True, return_precision=True,
    )
    expected = adapter.prepared.evaluate(
        predicted, visible, sigma_hz=width, detection_probability=0.25,
        clutter_rate=2.0, implementation="batched", return_gradient=True, return_precision=True,
    )
    for name in (
        "log_likelihood", "row_association_probability", "association_probability",
        "prediction_gradient", "prediction_precision", "satellite_support",
        "satellite_miss_probability", "expected_clutter_count",
    ):
        np.testing.assert_allclose(actual[name], expected[name], rtol=1e-14, atol=1e-14)


def test_group_mixture_density_gradient_and_precision():
    adapter, predicted, visible, options = fixture()
    result = adapter.evaluate(
        predicted, visible, **options, return_gradient=True, return_precision=True,
    )
    component = [adapter.prepared.evaluate(
        predicted, visible, sigma_hz=width, detection_probability=0.25,
        clutter_rate=2.0, implementation="batched",
    ) for width in (100.0, 400.0)]
    expected = np.logaddexp(
        np.log(0.8) + component[0]["log_likelihood"],
        np.log(0.2) + component[1]["log_likelihood"],
    )
    np.testing.assert_allclose(result["log_likelihood"], expected)
    assert np.all(result["prediction_precision"] >= 0)
    for rows in (np.array([0, 1, 2]), np.array([3])):
        for satellite in range(2):
            plus, minus = predicted.copy(), predicted.copy()
            plus[rows, satellite] += 0.01
            minus[rows, satellite] -= 0.01
            numerical = (
                adapter.evaluate(plus, visible, **options)["total_log_likelihood"]
                - adapter.evaluate(minus, visible, **options)["total_log_likelihood"]
            ) / 0.02
            assert numerical == pytest.approx(
                result["prediction_gradient"][rows, satellite].sum(), rel=1e-5, abs=1e-9,
            )
    np.testing.assert_allclose(
        result["association_probability"].sum(axis=1) + result["clutter_probability"], 1,
    )
    np.testing.assert_allclose(
        result["satellite_detection_probability"] + result["satellite_miss_probability"], 1,
    )


def test_equal_widths_reduce_to_single_component():
    adapter, predicted, visible, options = fixture()
    adapter.broad_sigma_hz = adapter.narrow_sigma_hz
    actual = adapter.evaluate(predicted, visible, **options)
    expected = adapter.prepared.evaluate(
        predicted, visible, sigma_hz=100, detection_probability=0.25,
        clutter_rate=2, implementation="batched",
    )
    np.testing.assert_allclose(actual["log_likelihood"], expected["log_likelihood"])
    np.testing.assert_allclose(actual["group_narrow_posterior"], 0.8)


def test_one_peak_density_integrates_to_conditional_cardinality_probability():
    count = 8192
    spacing = DEFAULT_ALIAS_HZ / count
    measured = (np.arange(count) + 0.5) * spacing - DEFAULT_ALIAS_HZ / 2
    prepared = prepare_finite_set_likelihood(measured, np.arange(count))
    adapter = GroupMixtureLikelihoodAdapter(prepared, 0.25, clutter_rate=2.0)
    predicted = np.zeros((count, 1))
    result = adapter.evaluate(
        predicted, np.ones_like(predicted, dtype=bool), sigma_hz=200,
        satellite_weights=np.ones(1), background_mass=0.2,
    )
    integral = spacing * np.exp(result["log_likelihood"]).sum()
    expected = np.exp(-2) * (0.75 * 2 + 0.25) / (1 - 0.75 * np.exp(-2))
    assert integral == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("kwargs", [
    {"narrow_weight": -0.1}, {"narrow_weight": np.nan},
    {"narrow_sigma_hz": 0}, {"broad_sigma_hz": 50}, {"broad_sigma_hz": np.inf},
])
def test_invalid_mixture_configuration(kwargs):
    with pytest.raises(ValueError):
        GroupMixtureLikelihoodAdapter(None, 0.25, **kwargs)
