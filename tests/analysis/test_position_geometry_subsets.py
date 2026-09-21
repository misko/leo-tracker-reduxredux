import numpy as np
import pytest

from leo.analysis.research.position_geometry_subsets import geometry_packet_order


def _inputs():
    n = 12
    ids = np.asarray([f"o{i}" for i in range(n)])
    training = np.asarray([True] * 10 + [False] * 2)
    track = np.asarray([0] * 5 + [1] * 5 + [2] * 2)
    time = np.tile(np.arange(5), 3)[:n].astype(float)
    angle = np.linspace(0.1, 2.4, n)
    p = np.column_stack((7000 * np.cos(angle), 7000 * np.sin(angle), np.full(n, 800.0)))
    v = np.column_stack((-7 * np.sin(angle), 7 * np.cos(angle), np.full(n, 0.2)))
    return ids, training, track, time, np.ones(n), p, v, p - v, v, p + v, v


def test_geometry_order_is_complete_deterministic_and_truth_blind():
    args = _inputs()
    grid = np.asarray([[6371.0, 0, 0], [6000.0, 1500.0, 1000.0]])
    result = geometry_packet_order(*args, grid, seed=2)
    assert result == geometry_packet_order(*args, grid, seed=2)
    assert len(result) == len(set(result)) == 10
    assert set(result) == {f"o{i}" for i in range(10)}


def test_geometry_order_rejects_bad_contracts():
    args = _inputs()
    grid = np.asarray([[6371.0, 0, 0]])
    with pytest.raises(ValueError, match="duplicate"):
        geometry_packet_order(np.asarray(["x"] * 12), *args[1:], grid)
    with pytest.raises(ValueError, match="packet_size"):
        geometry_packet_order(*args, grid, packet_size=2)
