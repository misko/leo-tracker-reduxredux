"""Dense old-kernel oracle for grouped sufficient-statistic evaluation."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def kernels():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield (
            importlib.import_module("dsx01_robust_joint"),
            importlib.import_module("dsx01_grouped_student"),
        )
    finally:
        sys.path.pop(0)


@pytest.mark.parametrize("sparse", [False, True])
def test_grouped_and_observation_space_bounds_agree_with_unequal_noise(kernels, sparse):
    old, new = kernels
    rng = np.random.default_rng(61)
    y, u = rng.normal(0, 10, 83), rng.normal(0, 3, (83, 12))
    groups = rng.integers(0, 5, len(y))
    if sparse:
        u[rng.random(u.shape) < 0.7] = 0
    sigma = rng.uniform(1, 4, len(y))
    a, b = (
        old.student_joint_bound(y, u, sigma, groups),
        new.student_joint_bound(y, u, sigma, groups),
    )
    for key in ("coefficient", "conditional_residual_hz", "noise_precision", "residual"):
        np.testing.assert_allclose(a[key], b[key], rtol=1e-10, atol=1e-10)


def test_large_offset_columns_preserve_objective_and_native_prediction(kernels):
    old, new = kernels
    rng = np.random.default_rng(77)
    n, k = 240, 24
    g = np.repeat(np.arange(8), 30)
    u = rng.normal(0, 100, (n, k))
    u[:, :4] = 0
    u[np.arange(n), g % 4] = 65000
    y = u @ rng.normal(0, 0.2, k) + rng.normal(0, 100, n)
    sigma = rng.uniform(50, 200, n)
    a, b = old.student_joint_bound(y, u, sigma, g), new.student_joint_bound(y, u, sigma, g)
    np.testing.assert_allclose(
        a["residual"] @ a["residual"], b["residual"] @ b["residual"], atol=1e-7
    )
    np.testing.assert_allclose(
        a["conditional_residual_hz"], b["conditional_residual_hz"], atol=1e-6
    )


def test_more_precision_iterations_do_not_increase_the_variational_bound(kernels):
    _, new = kernels
    rng = np.random.default_rng(51)
    y, u = rng.normal(0, 5, 100), rng.normal(0, 2, (100, 12))
    groups = np.repeat(np.arange(10), 10)
    costs = []
    for iterations in (1, 2, 8, 64):
        a = new.student_joint_bound(y, u, 1, groups, iterations=iterations)
        costs.append(a["residual"] @ a["residual"])
    assert np.all(np.diff(costs) <= 1e-10)
