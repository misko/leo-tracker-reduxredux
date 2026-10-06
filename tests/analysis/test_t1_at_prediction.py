from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.t1_at_prediction import T1AtPredictor
from leo.contracts.t1_at_prediction import T1AtDiscoveryData, T1AtDiscoveryManifestV1
from tests.analysis.test_t1_at import DIGEST, candidates, source


def bank():
    points = candidates(20)
    nodes = np.arange(-21.0, 28.0, 0.25)
    position = np.zeros((1, len(nodes), 3))
    position[0, :, 0] = 7378.137
    position[0, :, 1] = 7 * nodes
    position[0, :, 2] = 300
    velocity = np.zeros_like(position)
    velocity[:, :, 1] = 7
    n = len(points)
    return T1AtDiscoveryData(
        manifest=T1AtDiscoveryManifestV1(evidence=source(points, ()), bank_sha256=DIGEST),
        candidate_ids=np.arange(n),
        numbers=np.array([123]),
        nodes_s=nodes,
        position_km=position,
        velocity_km_s=velocity,
        rf_hz=np.linspace(10.9e9, 11.2e9, n),
        observer_km=np.tile([6378.137, 0, 0], (2, n, 1)),
        up=np.tile([1.0, 0, 0], (2, n, 1)),
        calibration_hz=np.array([np.arange(n) * 2.0, np.arange(n) * 3.0]),
    )


def test_timing_derivative_keeps_receive_time_calibration_fixed():
    data = bank()
    predict = T1AtPredictor(data)
    offset = 0.031
    p, visible, rate = predict("fitted-c", np.array([0]), offset)
    h = 1e-4
    derivative = (
        predict("fitted-c", np.array([0]), offset + h)[0]
        - predict("fitted-c", np.array([0]), offset - h)[0]
    ) / (2 * h)
    np.testing.assert_allclose(rate, derivative, atol=1e-5, rtol=1e-6)
    assert visible.all()
    q = predict("zero-c", np.array([0]), offset)[0]
    np.testing.assert_allclose((q - p)[:, 0], np.arange(20), atol=1e-9)


def test_wrong_bank_rows_and_insufficient_timing_span_are_rejected():
    data = bank()
    with pytest.raises(ValueError, match="top refined"):
        T1AtPredictor(replace(data, candidate_ids=np.zeros(20, int)))
    with pytest.raises(ValueError, match="uniformly"):
        T1AtPredictor(replace(data, nodes_s=np.zeros_like(data.nodes_s)))
    with pytest.raises(ValueError, match="full"):
        T1AtPredictor(replace(data, nodes_s=data.nodes_s + 2))
