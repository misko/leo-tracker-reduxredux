import numpy as np
import pytest

from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence
from leo.analysis.wrapped_glrt_likelihood import (
    PILOT_ALIAS_HZ,
    WrappedConfig,
    fit_wrapped,
    nuisance_design,
    smooth_visibility,
    wrapped_ratios,
)


def evidence(y, group=None, times=None):
    y = np.asarray(y, float).reshape(-1, 1)
    n = len(y)
    return FrequencyEvidence(
        tuple(map(str, range(n))),
        y,
        np.ones_like(y),
        np.full(n, 0.95),
        np.zeros(n, dtype=int) if group is None else group,
        np.arange(float(n)) if times is None else times,
    )


def test_alias_density_normalizes_and_does_not_count_aliases_twice():
    n = 200000
    data = evidence((np.arange(n) + 0.5) * PILOT_ALIAS_HZ / n - PILOT_ALIAS_HZ / 2)
    config = WrappedConfig(scale_hz=125.0)
    prediction = np.full((n, 1), 47000.0)
    design = np.ones((n, 1))
    a = wrapped_ratios(data, prediction, np.ones_like(prediction), design, [20000.0], config)
    assert a.mean() == pytest.approx(1.0, abs=1e-8)
    shifted = evidence(data.frequency_hz[:, 0] + 3 * PILOT_ALIAS_HZ)
    b = wrapped_ratios(shifted, prediction, np.ones_like(prediction), design, [20000.0], config)
    np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-10)


def test_alias_offset_gradient_matches_independent_finite_difference():
    data = evidence([100.0, 3000.0, -10000.0])
    config = WrappedConfig()
    prediction = np.array([[0.0, 1000.0], [500.0, 600.0], [-3000.0, 25000.0]])
    opportunity = np.ones_like(prediction)
    design = np.ones((3, 1))
    _, gradient, _ = wrapped_ratios(data, prediction, opportunity, design, [100.0], config, True)
    numerical = (
        wrapped_ratios(data, prediction, opportunity, design, [100.01], config)
        - wrapped_ratios(data, prediction, opportunity, design, [99.99], config)
    ) / 0.02
    np.testing.assert_allclose(gradient, numerical, rtol=1e-7, atol=1e-10)


def test_horizon_opportunity_is_continuous_and_has_zero_slope_at_endpoints():
    values = smooth_visibility(np.array([-1.0, 0.0, 1e-6, 5.0 - 1e-6, 5.0, 6.0]))
    assert values[0] == values[1] == 0
    assert values[-1] == values[-2] == 1
    assert values[2] / 1e-6 < 1e-6
    assert (1 - values[3]) / 1e-6 < 1e-6


@pytest.mark.parametrize("solver", ["irls", "lbfgs"])
def test_joint_band_drift_and_rf_coefficient_recovery_with_matched_zero_c(solver):
    n = 400
    time = np.linspace(0.0, 300.0, n)
    group = np.arange(n) % 4
    channel = (group % 2) * 4 + (np.arange(n) // 4) % 4 + 1
    rf = 10.45e9 + channel * 0.25e9
    data0 = evidence(np.zeros(n), group, time)
    design, labels, span = nuisance_design(data0, rf, coefficient=True)
    truth = np.array([-80000.0, -104000.0, -54000.0, -16000.0, 2.0 * span, 1.5 * span, -600.0])
    prediction = np.column_stack(
        (20000 * np.sin(time / 70), -35000 * np.cos(time / 50), 70000 + 2000 * np.sin(time / 30))
    )
    identity = (np.arange(n) // 20) % 2
    data = evidence(prediction[np.arange(n), identity] + design @ truth, group, time)
    config = WrappedConfig(
        scale_hz=125.0,
        satellite_penalty=8.0,
        maximum_satellites=3,
        iterations=15,
        nuisance_iterations=60,
        em_iterations=80,
        nuisance_solver=solver,
    )
    seed = truth[:4] + 40
    fitted = fit_wrapped(
        data, prediction, np.ones_like(prediction), rf, [seed], coefficient=True, config=config
    )
    zero = fit_wrapped(data, prediction, np.ones_like(prediction), rf, [seed], config=config)
    assert set(fitted["active"]) == {0, 1}
    np.testing.assert_allclose(fitted["offsets_hz"], truth[:4], atol=2.0)
    np.testing.assert_allclose(fitted["drift_hz_s"], [2.0, 1.5], atol=0.02)
    assert fitted["coefficient_hz_ghz"] == pytest.approx(-600.0, abs=3.0)
    assert fitted["score"] > zero["score"] + 20
    assert labels[-1] == "coefficient-hz-per-ghz"


def test_rf_term_requires_within_band_identification():
    group = np.arange(40) % 4
    data = evidence(np.zeros(40), group)
    with pytest.raises(ValueError, match="unidentifiable"):
        nuisance_design(data, np.full(40, 11e9), coefficient=True)
