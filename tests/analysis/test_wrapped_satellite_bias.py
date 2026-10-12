import numpy as np
import pytest

from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence
from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, fit_wrapped, nuisance_design
from leo.analysis.wrapped_glrt_refinement import joint_value_gradient


@pytest.mark.parametrize("solver", ["irls", "lbfgs"])
@pytest.mark.parametrize("fit_phase", [True, False])
def test_joint_satellite_bias_and_phase_recovery_charges_both_priors(solver, fit_phase):
    n = 1200
    time = np.linspace(0, 300, n)
    group = np.arange(n) % 4
    channel = (group % 2) * 4 + (np.arange(n) // 4) % 4 + 1
    rf = 10.45e9 + channel * 0.25e9
    data0 = FrequencyEvidence(
        tuple(map(str, range(n))), np.zeros((n, 1)), np.ones((n, 1)), np.ones(n), group, time
    )
    design, _, span = nuisance_design(data0, rf, coefficient=True)
    beta = np.array([-80000.0, -104000.0, -54000.0, -16000.0, 2 * span, 1.5 * span, -600.0])
    rf_scale = rf / 11.5846875e9
    base = np.column_stack((10000 * np.sin(time / 41), 30000 - 20000 * np.cos(time / 53)))
    timing = (
        np.column_stack((-900 * np.sin(time / 35), 700 * np.cos(time / 43))) * rf_scale[:, None]
    )
    phase, bias = np.array([1.5, -1.5]), np.array([1600.0, -1600.0])
    if not fit_phase:
        phase[:] = 0
    identity = (np.arange(n) // 20) % 2
    y = (base + timing * phase + bias[None, :])[np.arange(n), identity] + design @ beta
    data = FrequencyEvidence(
        data0.ids, y[:, None], data0.candidate_weight, data0.signal_probability, group, time
    )

    class Provider:
        def predict(self, value, indices=None):
            indices = np.arange(2) if indices is None else np.asarray(indices)
            pred = base[:, indices] + timing[:, indices] * np.asarray(value)
            return pred, np.ones_like(pred), timing[:, indices], np.zeros_like(pred)

    cfg = WrappedConfig(
        scale_hz=125,
        satellite_penalty=8,
        maximum_satellites=2,
        iterations=15,
        nuisance_iterations=100,
        em_iterations=80,
        relative_phase_sigma_s=1 if fit_phase else None,
        satellite_bias_sigma_hz=2000,
        nuisance_solver=solver,
    )
    fit = fit_wrapped(
        data,
        base,
        np.ones_like(base),
        rf,
        [dict(beta=beta.tolist(), active=[0, 1], weights=[0.001, 0.4995, 0.4995])],
        coefficient=True,
        config=cfg,
        orbit_provider=Provider() if fit_phase else None,
    )
    if fit_phase:
        total_phase = fit["phase_s"] + np.asarray(fit["satellite_phase_s"])
        np.testing.assert_allclose(total_phase, phase, atol=0.03)
    fitted_bias = np.asarray(fit["satellite_bias_hz"])
    # A common additive bias is interchangeable with receiver offsets.
    # Verify identifiable contrasts rather than that shared offset gauge.
    np.testing.assert_allclose(fitted_bias - fitted_bias.mean(), bias, atol=1)
    assert fit["coefficient_hz_ghz"] == pytest.approx(-600, abs=1)
    expected_bias_cost = 0.5 * np.sum((np.asarray(fit["satellite_bias_hz"]) / 2000) ** 2)
    assert fit["satellite_bias_prior_cost"] == pytest.approx(expected_bias_cost)
    expected_cost = (
        8 * len(fit["active"])
        + expected_bias_cost
        + fit["relative_phase_prior_cost"]
        + 0.5 * (fit["phase_s"] / 3) ** 2
        + 0.5 * np.sum((np.array(fit["drift_hz_s"]) / 10) ** 2)
        + 0.5 * (fit["coefficient_hz_ghz"] / 2000) ** 2
    )
    assert fit["log_ratio"] - fit["score"] == pytest.approx(expected_cost, abs=1e-7)
    zero = fit_wrapped(
        data,
        base,
        np.ones_like(base),
        rf,
        [dict(beta=beta[:-1].tolist(), active=[0, 1], weights=[0.001, 0.4995, 0.4995])],
        coefficient=False,
        config=cfg,
        orbit_provider=Provider() if fit_phase else None,
    )
    assert fit["score"] > zero["score"]


def test_satellite_bias_joint_gradient_matches_independent_differences():
    n = 40
    time = np.linspace(0, 3, n)
    data = FrequencyEvidence(
        tuple(map(str, range(n))),
        np.linspace(-100, 300, n)[:, None],
        np.ones((n, 1)),
        np.full(n, 0.9),
        np.zeros(n, int),
        time,
    )
    pred = np.column_stack((time * 20, 100 - time * 30))
    opp = np.ones_like(pred)
    design, precision = np.ones((n, 1)), np.array([0.0001])
    cfg = WrappedConfig(relative_phase_sigma_s=1, satellite_bias_sigma_hz=2000)

    class Provider:
        def predict(self, value, indices=None):
            indices = np.arange(2) if indices is None else np.asarray(indices)
            derivative = np.broadcast_to([20.0, -30.0], pred.shape)[:, indices]
            result = pred[:, indices] + derivative * np.asarray(value)
            return result, opp[:, indices], derivative, np.zeros_like(result)

    # beta, common phase, two local phases, two biases, two activity logits.
    scales = np.array([250.0, 0.1, 0.1, 0.1, 250.0, 250.0])
    vector = np.array([0.1, 0.2, 0.3, -0.2, 0.8, -0.4, -1.0, -0.7])
    args = (
        data,
        pred,
        opp,
        design,
        precision,
        cfg,
        [0, 1],
        Provider(),
        scales,
    )
    _, grad = joint_value_gradient(vector, *args)
    numerical = []
    for i in range(len(vector)):
        delta = np.zeros_like(vector)
        delta[i] = 1e-6
        numerical.append(
            (
                joint_value_gradient(vector + delta, *args)[0]
                - joint_value_gradient(vector - delta, *args)[0]
            )
            / 2e-6
        )
    np.testing.assert_allclose(grad, numerical, rtol=2e-6, atol=1e-6)


@pytest.mark.parametrize("solver", ["irls", "lbfgs"])
def test_unobservable_satellite_does_not_pay_for_a_seeded_carrier_bias(solver):
    n = 20
    data = FrequencyEvidence(
        tuple(map(str, range(n))),
        np.zeros((n, 1)),
        np.ones((n, 1)),
        np.ones(n),
        np.arange(n) % 2,
        np.arange(n, dtype=float),
    )
    cfg = WrappedConfig(satellite_bias_sigma_hz=2000, nuisance_solver=solver)
    fit = fit_wrapped(
        data,
        np.zeros((n, 1)),
        np.zeros((n, 1)),
        np.full(n, 11e9),
        [dict(beta=[0, 0, 0], active=[0], satellite_bias_hz=[1000])],
        config=cfg,
    )
    assert fit["score"] == 0
    assert fit["active"] == []
    assert fit["satellite_bias_hz"] == [0]
    with pytest.raises(ValueError, match="bias seed dimension"):
        fit_wrapped(
            data,
            np.zeros((n, 2)),
            np.zeros((n, 2)),
            np.full(n, 11e9),
            [dict(beta=[0, 0, 0], satellite_bias_hz=[1000])],
            config=cfg,
        )
