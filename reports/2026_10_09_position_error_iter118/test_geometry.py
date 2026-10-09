import runpy
from pathlib import Path

import numpy as np
import pytest

api = runpy.run_path(str(Path(__file__).with_name("geometry.py")))


def test_geometry_chain_rule_with_rotating_normal():
    r = np.array([6378.0, 0, 0])
    u = np.array([1.0, 0, 0])
    dr = np.array([[0, 1.0, 0], [0, 0, 1.0]])
    du = dr / 6378
    p = np.array([[7000.0, 2000.0, 400.0], [6300.0, 700.0, 200.0]])
    rate = np.array([[1.0, 2.0, 3.0], [2.0, -1.0, 4.0]])
    margin, spatial, timing = api["horizon_margin"](p, rate, r, u, dr, du)

    def at(q, t):
        normal = u + q @ du
        normal /= np.linalg.norm(normal)
        d = p + t * rate - (r + q @ dr)
        return d @ normal / np.linalg.norm(d, axis=-1)

    h = 1e-3
    for i in range(2):
        q = np.eye(2)[i] * h
        np.testing.assert_allclose(
            spatial[:, i], (at(q, 0) - at(-q, 0)) / (2 * h), atol=1e-10, rtol=0
        )
    np.testing.assert_allclose(
        timing, (at(np.zeros(2), h) - at(np.zeros(2), -h)) / (2 * h), atol=1e-10, rtol=0
    )
    np.testing.assert_allclose(margin, at(np.zeros(2), 0), atol=1e-15)


def test_gate_support_and_derivative():
    m = np.array([-0.1, 0, 0.03, 0.1, 0.2])
    v, derivative = api["positive_horizon_gate"](m, 0.1)
    assert v[0] == v[1] == 0
    assert v[3] == v[4] == 1
    h = 1e-7
    finite = (
        api["positive_horizon_gate"](m + h, 0.1)[0] - api["positive_horizon_gate"](m - h, 0.1)[0]
    ) / (2 * h)
    np.testing.assert_allclose(derivative, finite, atol=2e-5, rtol=0)
    with pytest.raises(ValueError):
        api["positive_horizon_gate"](m, 0)
