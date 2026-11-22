import ctypes as ct

import numpy as np
import pytest

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants import algo08_column_norms as column_norms
from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff


@pytest.fixture(scope="module")
def libraries(tmp_path_factory):
    root = tmp_path_factory.mktemp("column-norms")
    stock = native_bound.build(root / "stock")
    experiment = root / "experiment"
    column_norms.build(experiment)
    return stock, experiment


def synthetic(shared, private):
    rng = np.random.default_rng(18)
    groups = np.repeat([7, 9, 2, 4], [17, 25, 8, 19])
    u = np.zeros((len(groups), shared + 4 * private + 1))
    u[:, :shared] = rng.normal(size=(len(groups), shared))
    for index, label in enumerate(np.unique(groups)):
        use = groups == label
        start = shared + index * private
        u[use, start:start + private] = rng.normal(size=(use.sum(), private))
    y = rng.normal(size=len(groups))
    sigma = rng.uniform(.5, 1.5, size=len(groups))
    options = dict(powers=np.linspace(.25, 1., 4), iterations=32,
                   prior_groups=np.arange(u.shape[1]) % 3 - 1)
    return (y, u, sigma, groups), options


def assert_binary64_equal(left, right):
    assert left.keys() == right.keys()
    for key, values in left.items():
        assert np.asarray(values).tobytes() == np.asarray(right[key]).tobytes(), key


@pytest.mark.parametrize("shared,private,min_rcond", [(0, 0, 1e-12), (0, 2, 1e-12),
    (7, 0, 1e-12), (11, 2, 1e-12), (7, 3, 1e-12), (9, 1, .9)])
def test_native_bound_preserves_posteriors_and_fallback(libraries, shared, private, min_rcond):
    stock_binary, trial = libraries
    args, options = synthetic(shared, private)
    stock = native_bound.NativeBound(stock_binary, min_rcond=min_rcond)
    try:
        expected = stock(*args, **options)
        with column_norms.column_norms(
            trial / "column-norms-bound.so", trial / "column-norms-grid.so",
        ):
            candidate = native_bound.NativeBound(stock_binary, min_rcond=min_rcond)
            try:
                assert_binary64_equal(expected, candidate(*args, **options))
                assert stock.counts == candidate.counts
            finally:
                candidate.clear()
    finally:
        stock.clear()


def test_native_grid_preserves_exported_factor(libraries):
    stock, build = libraries
    args, options = synthetic(11, 2)
    results = []
    for binary in (build / "reference-grid.so", build / "column-norms-grid.so"):
        owner = native_bound.NativeBound(stock)
        capture = handoff.Capture(args[1].shape[1])
        operation = ct.CDLL(str(binary)).nb_run_posterior
        handoff.bind_export(operation, owner)
        owner.run = lambda *params, c=capture, o=owner, f=operation: c.run(o, f, params)
        try:
            result = owner(*args, **options)
            assert capture.valid()
            results.append(dict(result, lower=capture.lower, order=capture.order))
        finally:
            owner.clear()
    assert_binary64_equal(*results)
