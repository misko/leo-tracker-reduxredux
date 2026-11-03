import numpy as np
import pytest
from common import Data, circular, coordinates, ecef


def synthetic_data():
    data = Data.__new__(Data)
    data.times = np.array([0.1, 0.7, 1.3])
    data.receiver = np.array([0, 1, 0])
    data.rf = np.full(3, 11.2e9)
    data.nodes = np.arange(-11, 12, 0.25)
    data.numbers = np.array([1, 2])
    data.position = np.zeros((2, len(data.nodes), 3))
    data.velocity = np.zeros_like(data.position)
    data.position[:, :, 0] = -5000
    data.position[:, :, 1] = -6000 + 7 * data.nodes
    data.position[:, :, 2] = 5000
    data.velocity[:, :, 1] = 7
    return data


def test_paired_prediction_matches_full_matrix():
    data = synthetic_data()
    parameters = np.array([0, 0, -8000, -7, -23000, -8, 0.7, -0.2])
    full, visible = data.predict(parameters)
    rows, satellites = np.array([0, 1, 2]), np.array([1, 0, 1])
    paired, selected_visible = data.predict(parameters, rows, satellites)
    np.testing.assert_allclose(paired, full[rows, satellites])
    np.testing.assert_array_equal(selected_visible, visible[rows, satellites])


def test_rx_line_uses_receive_time_not_shifted_time():
    data = synthetic_data()
    parameters = np.array([0, 0, 0, 0, 0, 0, 2, -2], dtype=float)
    original, _ = data.predict(parameters)
    parameters[2:6] = [100, 2, 200, 3]
    corrected, _ = data.predict(parameters)
    expected = np.where(
        data.receiver == 0, 100 + 2 * (data.times - 150), 200 + 3 * (data.times - 150)
    )
    np.testing.assert_allclose(corrected - original, np.broadcast_to(expected[:, None], (3, 2)))


def test_coordinate_origin_and_wrap():
    np.testing.assert_allclose(coordinates([0, 0]), [38.5816, -121.4944])
    assert np.linalg.norm(ecef(0, 0)) == pytest.approx(6378.137)
    assert circular(1 / 4.4e-6 + 17) == pytest.approx(17)


def test_invalid_shift_fails():
    data = synthetic_data()
    with pytest.raises(ValueError):
        data.predict(np.array([0, 0, 0, 0, 0, 0, 50, 0]))
