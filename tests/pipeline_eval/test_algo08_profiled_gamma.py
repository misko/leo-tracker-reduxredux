from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_profiled_gamma import build, profiled_gamma


@pytest.fixture(scope="module")
def libraries(tmp_path_factory):
    folder = tmp_path_factory.mktemp("profiled-gamma")
    candidate = folder / "profiled.so"
    build(candidate)
    return native_bound.build(folder / "stock"), candidate


@pytest.mark.parametrize("fit_c", [False, True])
def test_profiled_objective_converges_and_replays_its_own_result(libraries, fit_c):
    stock, candidate = libraries
    port = SimpleNamespace(NativeBound=native_bound.NativeBound)
    rng = np.random.default_rng(7016)
    groups = np.repeat(np.arange(4), 18)
    rows, hardware = len(groups), 8 + int(fit_c)
    design = np.column_stack((rng.normal(size=(rows, hardware)),
                              (groups[:, None] // 2 == [0, 1]), np.eye(4)[groups]))
    sigma = np.linspace(75, 160, rows)
    raw = rng.normal(size=rows) * 180 + np.arange(4)[groups] * 170
    priors = np.full(design.shape[1], -1)
    priors[hardware:hardware + 2] = [0, 1]
    args = (raw, design, sigma, groups)
    options = dict(prior_groups=priors, powers=[1., .5, .8, 1.], prior_nu=5., noise_nu=6.)
    frozen = native_bound.NativeBound(stock)
    try:
        reference = frozen(*args, **options)
        with profiled_gamma(port, candidate) as counts:
            faster = port.NativeBound(stock)
            solution = faster(*args, **options)
            faster(-5 * raw, *args[1:], **options)
            replay = faster(*args, **options)
        for key in solution:
            np.testing.assert_array_equal(solution[key], replay[key], err_msg=key)
        assert counts["accepted"] > 0
        assert solution["precision_iterations"] < reference["precision_iterations"]
        assert solution["final_log_precision_change"] < 1e-5
        assert solution["negative_twice_elbo"] == pytest.approx(reference["negative_twice_elbo"], abs=1e-7)
        np.testing.assert_allclose(solution["conditional_residual_hz"],
                                   reference["conditional_residual_hz"], atol=.005, rtol=0.)
        np.testing.assert_allclose(solution["noise_precision"], reference["noise_precision"],
                                   atol=1e-5, rtol=1e-5)
        assert solution["normalization_constant"] == reference["normalization_constant"]
    finally:
        frozen.clear()


def test_nonconvergence_replays_the_installed_native_call(libraries):
    stock, candidate = libraries
    port = SimpleNamespace(NativeBound=native_bound.NativeBound)
    rng = np.random.default_rng(34)
    raw = rng.normal(10., 20., 50)
    args = (raw, np.ones((len(raw), 1)), 1., np.repeat([0, 1], 25))
    frozen = native_bound.NativeBound(stock)
    try:
        reference = frozen(*args, iterations=1)
        with profiled_gamma(port, candidate) as counts:
            faster = port.NativeBound(stock)
            replay = faster(*args, iterations=1)
        assert counts["activated"] == 1
        assert counts["evaluations"] == 1
        assert counts["stock_replays"] == 1
        for key in reference:
            np.testing.assert_array_equal(reference[key], replay[key], err_msg=key)
    finally:
        frozen.clear()
