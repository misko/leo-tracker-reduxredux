import runpy
from pathlib import Path

import numpy as np
import pytest
from objective import convert, timestamp_prediction
from pair_likelihood import paired_likelihood

from leo.analysis.hard60_satellite_correction import SatelliteCorrection

FIXTURE = runpy.run_path(
    str(Path(__file__).parents[1] / "2026_10_10_position_error_iter130/test_objective.py")
)


def model_and_provider(geometry):
    model, vector, clock = FIXTURE["fixture"]()
    if geometry == "timestamp":
        control = object.__new__(SatelliteCorrection)
        control.__dict__.update(model.__dict__)
        return control, vector, clock, timestamp_prediction
    return model, vector, clock, FIXTURE["api"]["predict"]


@pytest.mark.parametrize("geometry", ["timestamp", "phase"])
@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_all_parameter_gradients_and_unchanged_control(geometry, arm):
    model, vector, clock, provider = model_and_provider(geometry)
    if arm == "zero-c":
        vector[6], clock[-2:] = 0, 0
    originals = vector.copy(), clock.copy(), model.precision.copy()
    before = model.evaluate_joint(vector, clock)
    candidate = convert(
        model,
        [[0, 1], [2, 3]],
        0.25,
        prediction_provider=provider,
        emission_provider=paired_likelihood,
    )
    value, gradient, nuisance, _ = candidate.evaluate_joint(vector, clock)
    assert np.isfinite(value)
    for values, derivatives, isclock in ((vector, gradient, False), (clock, nuisance, True)):
        for i in range(len(values)):
            if arm == "zero-c" and ((not isclock and i == 6) or (isclock and i >= len(clock) - 2)):
                continue
            step = 1e-4 if i < 2 and not isclock else 1e-5
            plus, minus = values.copy(), values.copy()
            plus[i] += step
            minus[i] -= step
            args = ((vector, plus), (vector, minus)) if isclock else ((plus, clock), (minus, clock))
            finite = (
                candidate.evaluate_joint(*args[0])[0] - candidate.evaluate_joint(*args[1])[0]
            ) / (2 * step)
            np.testing.assert_allclose(derivatives[i], finite, atol=3e-5, rtol=2e-4)
    for actual, expected in zip((vector, clock, model.precision), originals, strict=True):
        np.testing.assert_array_equal(actual, expected)
    after = model.evaluate_joint(vector, clock)
    assert after[0] == before[0]
    np.testing.assert_array_equal(after[1], before[1])
    np.testing.assert_array_equal(after[2], before[2])


@pytest.mark.parametrize("geometry", ["timestamp", "phase"])
def test_zero_rho_delegates_exactly_without_emission_or_prediction(geometry):
    model, vector, clock, _ = model_and_provider(geometry)

    def unused(*args, **kwargs):
        pytest.fail("rho0 must call unchanged control directly")

    candidate = convert(model, [[0, 1]], 0, prediction_provider=unused, emission_provider=unused)
    expected, actual = model.evaluate_joint(vector, clock), candidate.evaluate_joint(vector, clock)
    assert expected[0] == actual[0]
    for a, b in zip(expected[1:3], actual[1:3], strict=True):
        np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(expected[3].responsibilities, actual[3].responsibilities)


def test_fixed_scope_and_pair_validation():
    model, _, _, provider = model_and_provider("timestamp")
    for pairs, rho in (([[0, 1], [1, 2]], 0.25), ([[0, 4]], 0.25), ([[0, 1]], 0.5)):
        with pytest.raises(ValueError):
            convert(
                model, pairs, rho, prediction_provider=provider, emission_provider=paired_likelihood
            )
