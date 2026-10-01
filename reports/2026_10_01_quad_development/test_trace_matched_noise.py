import numpy as np
import pytest
from trace_matched_noise import matched_white_variance


def test_trace_matching_and_common_mode_cancellation():
    b = np.column_stack((-np.ones(3), np.eye(3)))
    times = np.array([0., 1., 4., 9.])
    c = 2*np.eye(4)+3*np.exp(-abs(times[:, None]-times[None, :])/10)
    v = matched_white_variance(c, b)
    assert np.isclose(np.trace(b@c@b.T), np.trace(b@(v*np.eye(4))@b.T))
    assert np.isclose(v, matched_white_variance(c+100*np.ones((4, 4)), b))
    rotation, _ = np.linalg.qr(np.array([[1., 2., 4.], [2., -1., 3.], [0., 4., 1.]]))
    assert np.isclose(v, matched_white_variance(c, rotation@b))


def test_invalid_scale_rejected():
    with pytest.raises((ValueError, np.linalg.LinAlgError)):
        matched_white_variance(-np.eye(2), np.array([[-1., 1.]]))
    with pytest.raises(ValueError):
        matched_white_variance(np.eye(2), np.zeros((1, 2)))
