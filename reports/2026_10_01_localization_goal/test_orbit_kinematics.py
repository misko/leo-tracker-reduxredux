import numpy as np
import pytest
from diagnose_orbit_kinematics import position_derivative


@pytest.mark.parametrize('width', [5, 7])
def test_polynomial_derivative_and_translation(width):
    times = np.arange(-10., 11.)
    positions = np.column_stack([times**4, times**3+2*times, times**2])
    query = .37
    expected = [4*query**3, 3*query**2+2, 2*query]
    np.testing.assert_allclose(position_derivative(times, positions, query, width), expected,
                               atol=1e-12)
    np.testing.assert_allclose(position_derivative(times, positions+7000, query, width), expected,
                               atol=1e-10)


def test_smooth_orbit_refinement_and_support():
    times = np.arange(-50., 51., 5.)
    omega = .01
    positions = 6900*np.column_stack([np.cos(omega*times), np.sin(omega*times), times*0])
    query = 1.7
    expected = 6900*omega*np.array([-np.sin(omega*query), np.cos(omega*query), 0.])
    e5 = np.linalg.norm(position_derivative(times, positions, query, 5)-expected)
    e7 = np.linalg.norm(position_derivative(times, positions, query, 7)-expected)
    assert e7 < e5/100
    with pytest.raises(ValueError):
        position_derivative(times, positions, times[-1], 7)
