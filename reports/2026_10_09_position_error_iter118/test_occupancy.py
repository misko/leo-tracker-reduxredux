import runpy
from pathlib import Path

import numpy as np
import pytest

integrate = runpy.run_path(str(Path(__file__).with_name("occupancy.py")))["integrate"]


def test_crossing_gradient_and_sparse_gap():
    intervals = np.array([[0.0, 0.4], [0.6, 1.0]])
    nodes = np.array([0.0, 0.3, 0.7, 1.0])
    h = nodes - 0.2
    j = np.ones((4, 1))
    out = integrate(intervals, nodes, h, j)
    assert out["fraction"] == pytest.approx(0.75)
    assert out["gradient"][0] == pytest.approx(1 / 0.8)
    step = 1e-6
    fd = (
        integrate(intervals, nodes, h + step, j)["fraction"]
        - integrate(intervals, nodes, h - step, j)["fraction"]
    ) / (2 * step)
    assert out["gradient"][0] == pytest.approx(fd, abs=1e-10)
    gap = integrate(intervals, nodes, nodes - 0.5, j)
    assert gap["fraction"] == pytest.approx(0.5)
    assert gap["gradient"][0] == 0


def test_piecewise_nodes_and_descending_crossing():
    out = integrate([[0, 2]], [0, 1, 2], [-1, 1, -3], np.ones((3, 1)))
    assert out["fraction"] == pytest.approx(0.375)
    assert out["gradient"][0] == pytest.approx(0.375)
    assert out["pieces"] == 2


def test_contacts_do_not_claim_derivative():
    out = integrate([[0, 2]], [0, 1, 2], [-1, 0, -1], np.ones((3, 1)))
    assert out["fraction"] == 0
    assert out["gradient"] is None
    assert len(out["events"]) == 2
    flat = integrate([[0, 1]], [0, 1], [0, 0], np.ones((2, 1)))
    assert flat["fraction"] == 1
    assert flat["gradient"] is None


def test_invalid_support_rejected():
    with pytest.raises(ValueError):
        integrate([[0, 0.7], [0.6, 1]], [0, 1], [-1, 1], np.ones((2, 1)))


def test_orbit_shift_uses_segment_local_secants_and_moving_knots():
    nodes = np.array([0.0, 1.0, 2.0])
    h = np.array([-1.0, 1.0, -3.0])
    slopes = np.diff(h) / np.diff(nodes)
    jac = np.repeat(slopes[:, None, None], 2, axis=1)
    result = integrate([[0.1, 1.9]], nodes, h, jac)
    step = 1e-6
    fd = (
        integrate([[0.1, 1.9]], nodes - step, h, jac)["fraction"]
        - integrate([[0.1, 1.9]], nodes + step, h, jac)["fraction"]
    ) / (2 * step)
    assert result["gradient"][0] == pytest.approx(fd, abs=1e-10)
