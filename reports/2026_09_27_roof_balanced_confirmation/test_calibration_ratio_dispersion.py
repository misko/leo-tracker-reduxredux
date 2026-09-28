from types import SimpleNamespace

import numpy as np
import pytest

from calibration_ratio_dispersion import ratio_moments


def test_shared_identity_variance_and_no_ratio_conditioning():
    track = SimpleNamespace(matched=np.array([True, True]),
        detection_design=np.zeros((2, 2, 1)), log_weights=np.log([.5, .5]),
        ratio_design=np.array([[[0.], [0.]], [[2.], [2.]]]),
        log_ratio=np.array([1., 1.]))
    theta = np.array([0., 1., 0.])
    layout = SimpleNamespace(detection_size=1)
    numerator, variance, count = ratio_moments(track, theta, layout)
    assert (numerator, variance, count) == pytest.approx((0., 6., 2))
    track.log_ratio = np.array([10., 10.])
    assert ratio_moments(track, theta, layout) == pytest.approx((324., 6., 2))


def test_no_matched_rows():
    assert ratio_moments(SimpleNamespace(matched=np.array([False])), None, None) is None
