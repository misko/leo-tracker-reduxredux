import numpy as np
from joint_inputs import _coordinates
from oracle_position_diagnostic import FixedLocationJacobian, reference_coordinates


def test_inverse_geographic_frame_round_trip():
    for point in ([0., 0.], [-85., -80.], [199., -195.]):
        reconstructed = reference_coordinates(*_coordinates(np.asarray(point)))
        np.testing.assert_allclose(reconstructed, point, atol=1e-9)


def test_fixed_location_removes_only_position_derivatives():
    class Jacobian:
        def transpose_multiply(self, weights):
            return np.arange(1., 8.) * weights

        def normal_matrix(self, weights):
            return np.ones((7, 7)) * weights

    fixed = FixedLocationJacobian(Jacobian())
    np.testing.assert_array_equal(fixed.transpose_multiply(2), [0, 0, 6, 8, 10, 12, 14])
    actual = fixed.normal_matrix(2)
    np.testing.assert_array_equal(actual[:2], 0)
    np.testing.assert_array_equal(actual[:, :2], 0)
    np.testing.assert_array_equal(actual[2:, 2:], 2)
