import runpy
from pathlib import Path

import numpy as np
import pytest

curvature = runpy.run_path(str(Path(__file__).with_name("mixture_curvature.py")))["curvature"]


def test_exact_affine_mixture_hessian_finite_difference():
    rng = np.random.default_rng(11)
    jac = rng.normal(size=(3, 2, 2))
    residual = rng.normal(size=(3, 2))
    sigma = 1.3
    prior = np.array([0.3, 0.4])
    signal = prior * np.exp(-0.5 * (residual / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
    total = 0.08 + signal.sum(axis=1)
    probability = signal / total[:, None]

    def gradient(x):
        r = residual - np.einsum("nkp,p->nk", jac, x)
        s = prior * np.exp(-0.5 * (r / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
        w = s / (0.08 + s.sum(axis=1))[:, None]
        return -np.einsum("nk,nkp->p", w * r / sigma**2, jac)

    step = 1e-5
    finite = np.column_stack(
        [
            (gradient(step * np.eye(2)[i]) - gradient(-step * np.eye(2)[i])) / (2 * step)
            for i in range(2)
        ]
    )
    actual = curvature(jac, residual, probability, sigma)
    np.testing.assert_allclose(actual["observed_local"], finite, atol=1e-9)


def test_separated_labels_clutter_and_ambiguous_negative_curvature():
    jac = np.ones((1, 2, 1))
    separated = curvature(jac, [[2, -2]], [[1, 0]], 1)
    assert separated["missing_information"][0, 0] == 0
    assert separated["observed_local"][0, 0] == 1
    clutter = curvature(jac, [[2, -2]], [[0, 0]], 1)
    assert all(np.all(v == 0) for v in clutter.values())
    ambiguous = curvature(jac, [[2, -2]], [[0.5, 0.5]], 1)
    assert ambiguous["complete"][0, 0] == 1
    assert ambiguous["missing_information"][0, 0] == 4
    assert ambiguous["observed_local"][0, 0] == -3


def test_satellite_and_row_permutation():
    rng = np.random.default_rng(2)
    jac = rng.normal(size=(3, 4, 2))
    residual = rng.normal(size=(3, 4))
    probability = np.full((3, 4), 0.1)
    a = curvature(jac, residual, probability, 2)
    b = curvature(jac[::-1, ::-1], residual[::-1, ::-1], probability[::-1, ::-1], 2)
    for key in a:
        np.testing.assert_allclose(a[key], b[key], atol=1e-14)


def test_probability_normalization_roundoff_used_unchanged():
    mass = np.array([[0.23530123166758055, 0.8022026837784835]])
    probability = mass / mass.sum()
    assert probability.sum() > 1
    actual = curvature(np.ones((1, 2, 1)), [[0, 0]], probability, 1)
    assert actual["complete"][0, 0] == probability.sum()
    with pytest.raises(ValueError):
        curvature(np.ones((1, 2, 1)), [[0, 0]], [[0.5, 0.50000000001]], 1)


@pytest.mark.parametrize(
    "probability,sigma", [([[0.6, 0.6]], 1), ([[-0.1, 0.5]], 1), ([[np.nan, 0]], 1), ([[0, 0]], 0)]
)
def test_invalid_inputs(probability, sigma):
    with pytest.raises(ValueError):
        curvature(np.ones((1, 2, 1)), [[0, 0]], probability, sigma)
