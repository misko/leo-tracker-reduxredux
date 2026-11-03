import numpy as np
import pytest

from leo.analysis.localization_observed import gradient_jacobian


def test_quartic_hessian_and_step_refinement():
    def gradient(x):
        return np.array([4*x[0]**3+3*x[1], 3*x[0]-2*x[1]])
    x = np.array([.7, -.4])
    exact = np.array([[12*x[0]**2, 3.], [3., -2.]])
    coarse = gradient_jacobian(gradient, x, [.01, .01])
    fine = gradient_jacobian(gradient, x, [.005, .005])
    np.testing.assert_allclose(np.linalg.norm(coarse-exact)/np.linalg.norm(fine-exact),
                               4., rtol=1e-7)
    assert np.linalg.eigvalsh(fine)[0] < 0  # No hidden PSD clipping.


def test_coordinate_scaling_and_asymmetry_preserved():
    matrix = np.array([[2., 3.], [4., 7.]])
    scales = np.array([.001, 1000.])
    transformed = scales[:, None]*matrix*scales[None, :]
    result = gradient_jacobian(lambda x: transformed@x, [.2, -.3], [.1, .1])
    np.testing.assert_allclose(result, transformed, rtol=1e-7, atol=1e-12)
    assert result[0, 1] != result[1, 0]
    with pytest.raises(ValueError):
        gradient_jacobian(lambda x: x, [0.], [0.])
    with pytest.raises(ValueError):
        gradient_jacobian(lambda x: np.array([np.nan]), [0.], [.1])
