from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants import algo08_robust_accel, algo08_robust_warm


class Model:
    def __init__(self, count):
        self.keep = np.ones(count, bool)


@pytest.mark.parametrize("fit_c", [False, True])
def test_native_warm_start_reaches_cold_solution_and_resets_on_model_changes(tmp_path, fit_c):
    stock = native_bound.build(tmp_path / "stock")
    candidate = tmp_path / "warm.so"
    algo08_robust_warm.build(candidate)
    port = SimpleNamespace(NativeBound=native_bound.NativeBound)
    rng = np.random.default_rng(7016)
    groups = np.repeat(np.arange(4), 18)
    rows, hardware = len(groups), 8 + int(fit_c)
    features = np.column_stack((rng.normal(size=(rows, hardware)), (groups[:, None] // 2 == [0, 1]),
                                np.eye(4)[groups]))
    sigma = np.linspace(75, 160, rows)
    raw = rng.normal(size=rows) * 180 + np.arange(4)[groups] * 170
    priors = np.full(features.shape[1], -1)
    priors[hardware:hardware + 2] = [0, 1]
    frozen = native_bound.NativeBound(stock)
    geom = object()
    model = Model(rows)
    expected = frozen(raw, features, sigma, groups, prior_groups=priors)
    with algo08_robust_warm.binding(port, candidate) as metrics:
        warmed = port.NativeBound(stock)
        warmed.note_model(model, geom)
        seed = warmed(raw, features, sigma, groups, prior_groups=priors)
        assert seed["precision_iterations"] == expected["precision_iterations"]
        np.testing.assert_array_equal(seed["residual"], expected["residual"])

        nearby = raw + rng.normal(size=rows) * 1e-4
        comparison = frozen(nearby, features, sigma, groups, prior_groups=priors)
        warmed.note_model(model, geom)
        actual = warmed(nearby, features, sigma, groups, prior_groups=priors)
        assert actual["precision_iterations"] < comparison["precision_iterations"]
        assert actual["final_log_precision_change"] < 1e-5
        np.testing.assert_allclose(actual["noise_precision"], comparison["noise_precision"],
                                   atol=1e-5, rtol=1e-5)
        np.testing.assert_allclose(actual["coefficient"], comparison["coefficient"],
                                   atol=3e-4, rtol=3e-5)
        assert abs(actual["negative_twice_elbo"] - comparison["negative_twice_elbo"]) < 1e-6

        # A distant numerical trial may exhaust the warm solver's budget.
        # The result then comes from the exact original cold call.
        farther = -10 * raw
        expected_retry = frozen(farther, features, sigma, groups, prior_groups=priors, iterations=1)
        warmed.note_model(model, geom)
        retried = warmed(farther, features, sigma, groups, prior_groups=priors, iterations=1)
        np.testing.assert_array_equal(expected_retry["residual"], retried["residual"])

        model.keep[0] = False
        warmed.note_model(model, geom)
        after_mask = warmed(raw, features, sigma, groups, prior_groups=priors)
        warmed.note_model(model, object())
        after_geometry = warmed(raw, features, sigma, groups, prior_groups=priors)
        warmed.note_model(Model(rows), geom)
        other_model = warmed(raw, features, sigma, groups, prior_groups=priors)
        for result in (after_mask, after_geometry, other_model):
            np.testing.assert_array_equal(expected["residual"], result["residual"])
    frozen.clear()
    assert metrics["warm_calls"] == 2
    assert metrics["warm_retries"] == 1
    assert metrics["kernel_calls"] == 6


def test_full_likelihood_acceleration_replays_without_call_history(tmp_path):
    stock = native_bound.build(tmp_path / "stock")
    library = tmp_path / "accel.so"
    algo08_robust_accel.build(library)
    port = SimpleNamespace(NativeBound=native_bound.NativeBound)
    rng = np.random.default_rng(44112)
    groups = np.repeat(np.arange(5), 29)
    raw = rng.normal(size=len(groups)) * 245
    raw[groups == 4] += 40 * rng.normal(size=int((groups == 4).sum()))
    features = np.column_stack((rng.normal(size=(len(raw), 10)), 1000 * np.eye(5)[groups]))
    sigma = rng.uniform(50, 200, size=len(raw))
    priors = [-1] * 8 + [0, 1] + [-1] * 5
    original = native_bound.NativeBound(stock)
    with algo08_robust_warm.binding(port, library, accelerate=True) as metrics:
        accelerated = port.NativeBound(stock)
        first = accelerated(raw, features, sigma, groups, prior_groups=priors)
        accelerated(-2 * raw, features, sigma, groups, prior_groups=priors)
        repeat = accelerated(raw, features, sigma, groups, prior_groups=priors)
        frozen = original(raw, features, sigma, groups, prior_groups=priors)
        for key in first:
            np.testing.assert_array_equal(repeat[key], first[key], err_msg=key)
        assert first["final_log_precision_change"] < 1e-5
        assert abs(first["negative_twice_elbo"] - frozen["negative_twice_elbo"]) < 1e-6
        np.testing.assert_allclose(first["conditional_residual_hz"],
                                   frozen["conditional_residual_hz"], atol=.005)
    original.clear()
    assert metrics["extrapolations"] > 0
