import numpy as np
import pytest
from bundle import _COMMON
from fast_geometry import ZeroShiftGeometry, usable


class CountingArray(np.ndarray):
    def __new__(cls, values):
        result = np.asarray(values).view(cls)
        result.read_count = 0
        return result

    def __array_finalize__(self, source):
        self.read_count = getattr(source, "read_count", 0)

    def __getitem__(self, key):
        self.read_count += 1
        return super().__getitem__(key)


def synthetic_data():
    rng = np.random.default_rng(20261002)
    data = object.__new__(_COMMON.Data)
    data.times = np.array([-2.3, 0.0, 2.75, 8.4, 19.9])
    data.rf = np.array([10.7e9, 10.95e9, 11.2e9, 11.45e9, 11.7e9])
    data.receiver = np.array([0, 1, 0, 1, 0])
    data.nodes = np.arange(-11.0, 31.25, 0.25)
    base_position = rng.normal(size=(64, len(data.nodes), 3)) * 500
    base_position[..., 0] += 6800
    base_velocity = rng.normal(size=base_position.shape) * 4
    data.position = CountingArray(base_position)
    data.velocity = CountingArray(base_velocity)
    data.numbers = np.arange(64)
    data.initial = np.zeros(70)
    return data


@pytest.mark.parametrize("point", ([0.0, 0.0], [120.0, -75.0], [-800.0, 430.0]))
def test_zero_shift_geometry_matches_common_predict(point):
    data = synthetic_data()
    geometry = ZeroShiftGeometry(data)
    parameters = np.zeros(70)
    parameters[:2] = point
    expected_prediction, expected_visible = data.predict(parameters)
    prediction, visible = geometry.predict(point)
    np.testing.assert_allclose(prediction, expected_prediction, rtol=0.0, atol=1e-8)
    np.testing.assert_array_equal(visible, expected_visible)


def test_orbit_interpolation_occurs_once_for_repeated_queries():
    data = synthetic_data()
    geometry = ZeroShiftGeometry(data)
    reads_after_initialization = data.position.read_count + data.velocity.read_count
    assert reads_after_initialization > 0
    for index in range(10):
        geometry.predict([float(index), float(-index)])
    assert data.position.read_count + data.velocity.read_count == reads_after_initialization
    assert geometry.preinterpolation_count == 1


def test_usable_rejects_nonuniform_or_wrong_candidate_geometry():
    data = synthetic_data()
    assert usable(data)
    data.nodes = data.nodes.copy()
    data.nodes[2] += 0.01
    assert not usable(data)
    with pytest.raises(ValueError, match="incompatible"):
        ZeroShiftGeometry(data)
