"""Exact optimized likelihood regression against the frozen external oracle."""

import ast
import hashlib
import importlib.util
import inspect
import runpy
import sys
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.localization_v3.hierarchical import hierarchical_bound


@pytest.fixture(scope="module")
def oracle():
    path = Path(__file__).resolve().parents[2] / "tools/algo07v3_hierarchical_oracle.py"
    spec = importlib.util.spec_from_file_location("frozen_hierarchical_oracle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = inspect.getsource(module.hierarchical_bound)
    assert hashlib.sha256(source.encode()).hexdigest() == (
        "225f81aca6f496c18ee176f37f109dfb282eadcfbc362030be2b4de7b44d6982"
    )
    return module


def test_owned_kernel_is_the_full_scan_qualified_prototype(oracle, monkeypatch):
    import algo07v3_presolver_hierarchical_oracle as presolver

    monkeypatch.setitem(sys.modules, "algo07v3_hierarchical_oracle", oracle)
    path = (
        Path(__file__).resolve().parents[2] / "reports/2026_11_05_algo07v3_pair/probe_assembly.py"
    )
    _, _, expected = runpy.run_path(str(path))["candidate_function"]()
    assert hashlib.sha256(expected.encode()).hexdigest() == (
        "4c17f814642726de73e9ca2497af943c6b05e33b9dfa19a70e836e3fabc08042"
    )
    assert ast.dump(ast.parse(inspect.getsource(presolver.hierarchical_bound))) == ast.dump(
        ast.parse(expected)
    )


def test_prevariance_solver_is_the_full_scan_qualified_upper_root_prototype():
    import algo07v3_prevariance_hierarchical_oracle as prevariance
    from probe_algo07v3_upper_root import candidate_function

    _, _, expected = candidate_function()
    assert hashlib.sha256(expected.encode()).hexdigest() == (
        "a5546d39b4b3484f358794881649e161e81addfeb7eab97de866d31dde17d944"
    )
    expected = expected.replace("solve_factor(", "_solve_factor(")
    assert ast.dump(ast.parse(inspect.getsource(prevariance.hierarchical_bound))) == ast.dump(
        ast.parse(expected)
    )


def test_preindex_solver_is_the_two_scan_qualified_variance_prototype():
    import algo07v3_preindex_hierarchical_oracle as preindex
    from probe_algo07v3_variance_groups import candidate_function

    assert hashlib.sha256(Path(preindex.__file__).read_bytes()).hexdigest() == (
        "3b02974c822ef2504422dcdb85f10d16198ec8df2ef35936119e42a97877dab2"
    )
    _, _, expected = candidate_function()
    assert hashlib.sha256(expected.encode()).hexdigest() == (
        "7bab33ce76fda0bc07895b2d2cbfdfd7c2cf028ef078b9baf2d19f5e2b6dc439"
    )
    assert ast.dump(ast.parse(inspect.getsource(preindex.hierarchical_bound))) == ast.dump(
        ast.parse(expected)
    )


def test_owned_solver_is_the_native_qualified_covariance_index_prototype():
    from probe_algo07v3_variance_indices import candidate_function

    _, _, expected = candidate_function()
    assert hashlib.sha256(expected.encode()).hexdigest() == (
        "65128c40051a36fbe1132117da90df4df7bd6af547b1ebb68b1fba396d1e12ef"
    )
    assert ast.dump(ast.parse(inspect.getsource(hierarchical_bound))) == ast.dump(
        ast.parse(expected)
    )


@pytest.mark.parametrize("width", [0, 1, 16, 190])
@pytest.mark.parametrize("layout", ["C", "F"])
@pytest.mark.parametrize("density", [0.0, 0.2, 1.0])
def test_full_likelihood_exact_with_shared_indices_and_sparse_groups(
    oracle, width, layout, density
):
    rng = np.random.default_rng(2391)
    features = rng.normal(size=(96, width))
    features[rng.random(features.shape) >= density] = 0
    features = np.array(features, order=layout)
    raw = rng.normal(size=96) * 100
    sigma = rng.uniform(3, 40, size=96)
    groups = np.arange(96) % 5 * 3
    kwargs = dict(
        prior_groups=np.arange(width) // 5 - 1,
        powers=np.linspace(0.1, 1.0, 5),
        iterations=16,
    )
    before = [a.copy() for a in (raw, features, sigma, groups)]
    expected = oracle.hierarchical_bound(raw, features, sigma, groups, **kwargs)
    actual = hierarchical_bound(raw, features, sigma, groups, **kwargs)
    assert actual.keys() == expected.keys()
    for key in actual:
        a, b = np.asarray(actual[key]), np.asarray(expected[key])
        assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), key
    for original, current in zip(before, (raw, features, sigma, groups), strict=True):
        assert np.array_equal(original, current)
