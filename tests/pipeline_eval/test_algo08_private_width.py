import numpy as np
import pytest

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants import algo08_private_width as wider


@pytest.fixture(scope="module")
def libraries(tmp_path_factory):
    root = tmp_path_factory.mktemp("private-width")
    return native_bound.build(root / "stock"), wider.build(root / "wide")


@pytest.mark.parametrize("private", [2, 3, 5, 8, 9])
def test_only_extends_unsupported_layout_and_preserves_reference_moments(libraries, private):
    released, expanded = libraries
    rng = np.random.default_rng(private)
    groups = np.repeat([0, 1, 2], [24, 31, 29])
    rows = len(groups)
    shared = rng.normal(0., 7., (rows, 3))
    local = np.zeros((rows, private + 1))
    local[groups == 0, :private] = rng.normal(0., 4., (24, private))
    local[groups == 1, private] = rng.normal(0., 3., 31)
    features = np.column_stack((shared, local))
    values, sigma = rng.normal(0., 25., rows), rng.uniform(4., 12., rows)
    stock = native_bound.NativeBound(released)
    try:
        options = dict(powers=np.array([1., .6, .5]), prior_groups=np.r_[0, np.full(private+3, -1)])
        expected = stock(values, features, sigma, groups, **options)
        with wider.expand_unsupported_layout(expanded) as counts:
            candidate = stock(values, features, sigma, groups, **options)
        assert counts["calls"] == int(private > 2)
        assert counts["activated"] == int(2 < private <= 8)
        assert expected["precision_iterations"] == candidate["precision_iterations"]
        assert expected.keys() == candidate.keys()
        for key in expected:
            if 2 < private <= 8:
                np.testing.assert_allclose(candidate[key], expected[key], rtol=2e-11, atol=2e-9)
            else:
                assert np.asarray(candidate[key]).tobytes() == np.asarray(expected[key]).tobytes()
    finally:
        stock.clear()


def test_leaves_the_stock_numerical_fallback_alone(libraries):
    released, expanded = libraries
    rng = np.random.default_rng(2)
    groups = np.repeat([0, 1, 2], 40)
    correlated = rng.normal(0., 200., len(groups))
    features = np.column_stack((correlated, correlated))
    values = rng.normal(0., 20., len(groups))
    stock = native_bound.NativeBound(released, min_rcond=1e-2)
    try:
        expected = stock(values, features, 10., groups)
        assert stock.counts["fallback_ill_conditioned"] == 1
        with wider.expand_unsupported_layout(expanded) as counts:
            candidate = stock(values, features, 10., groups)
        assert counts["calls"] == 0
        assert stock.counts["fallback_ill_conditioned"] == 2
        for key in expected:
            assert np.asarray(candidate[key]).tobytes() == np.asarray(expected[key]).tobytes()
    finally:
        stock.clear()
