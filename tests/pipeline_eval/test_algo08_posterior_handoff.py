import ctypes as ct

import numpy as np
import pytest

from leo.analysis.localization_v3.predictive_linear import predictive_residual
from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_posterior_handoff import (
    Capture,
    bind_export,
    build,
    predictive_factor,
    whiten,
)


@pytest.fixture(scope="module")
def native_export(tmp_path_factory):
    folder = tmp_path_factory.mktemp("posterior-handoff")
    library = folder / "handoff.so"
    build(library)
    return ct.CDLL(str(library)).nb_run_posterior, native_bound.build(folder / "stock")


@pytest.mark.parametrize("fitted_c", [False, True])
def test_native_factor_reuses_the_final_robust_posterior(native_export, fitted_c):
    exported, library = native_export
    bound = native_bound.NativeBound(library)
    rng = np.random.default_rng(402)
    groups = np.repeat(np.arange(3), 12)
    shared = 2 + fitted_c
    width = shared + 5
    design = np.zeros((len(groups), width))
    design[:, :shared] = rng.normal(0., 8., (len(groups), shared))
    for group, columns in enumerate(((shared,), (shared + 1, shared + 2), (shared + 3,))):
        design[np.ix_(groups == group, columns)] = rng.normal(0., 9., (12, len(columns)))
    scale = np.r_[np.ones(width - 3), np.full(3, .3)]
    latent = design * scale
    sigma = rng.uniform(2., 4., len(groups))
    raw = rng.normal(0., 5., len(groups))
    powers = np.array([.5, .8, 1.])
    prior = np.r_[0, np.full(width - 1, -1)]
    options = dict(powers=powers, prior_groups=prior, prior_nu=5)
    baseline = bound(raw, latent, sigma, groups, **options)
    capture = Capture(width)
    ordinary_run = bind_export(exported, bound)
    try:
        bound.run = lambda *args: capture.run(bound, exported, args)
        solution = bound(raw, latent, sigma, groups, **options)
        assert capture.valid()
        assert np.count_nonzero(capture.order != np.arange(width)) > 0
        for key in baseline:
            assert np.asarray(solution[key]).tobytes() == np.asarray(baseline[key]).tobytes(), key
        weights = powers[groups] * baseline["noise_precision"][groups] / sigma**2
        dense = np.diag(baseline["coefficient_prior_precision"]) + latent.T @ (latent * weights[:, None])
        np.testing.assert_allclose(capture.lower @ capture.lower.T,
                                   dense[np.ix_(capture.order, capture.order)], rtol=1e-13, atol=1e-13)
        predictive = rng.normal(0, 5, (11, width))
        expected = predictive * scale
        expected = np.linalg.solve(np.linalg.cholesky(dense), expected.T).T
        handed = whiten(predictive, capture.lower, capture.order, scale)
        np.testing.assert_allclose(handed @ handed.T, expected @ expected.T, rtol=1e-12, atol=1e-12)
        y = rng.normal(0, 18, 11)
        noise = rng.uniform(3, 5, len(y))
        new_groups = np.arange(len(y)) % 2
        stock = predictive_residual(y, predictive, dense / np.outer(scale, scale), noise, new_groups)
        candidate = predictive_factor(y, predictive, noise, new_groups, capture, 3)
        assert candidate["objective"] == pytest.approx(stock["objective"], abs=1e-10, rel=0.)
        assert not np.array_equal(candidate["residual"], stock["residual"])
    finally:
        bound.run = ordinary_run
        bound.clear()


def test_capture_rejects_native_fallback_and_invalid_order():
    class Owner:
        counts = dict(activated=6)

    capture = Capture(2)
    assert not capture.valid()
    capture.bound = Owner()
    capture.accepted = 6
    capture.exported.value = 1
    capture.lower[:] = np.eye(2)
    capture.order[:] = [0, 0]
    assert not capture.valid()
    capture.bound.counts["activated"] = 7
    assert not capture.valid()
    capture.order[:] = [1, 0]
    assert capture.valid()
