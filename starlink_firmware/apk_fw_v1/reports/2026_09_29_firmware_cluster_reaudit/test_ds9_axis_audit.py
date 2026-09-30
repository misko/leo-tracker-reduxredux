import numpy as np
import pytest
from ds9_axis_audit import rotations


def test_axis_controls_center_stationary_offsets_and_detect_matching_frames():
    x = np.random.default_rng(3).normal(size=(23, 4))
    scores = rotations(x, x + np.array([100, -50, 9, 17]))
    assert abs(scores[0] - 1) < 1e-12
    assert abs(scores.mean()) < 1e-12
    assert scores[1:].max() < scores[0]
    with pytest.raises(ValueError, match="Constant"):
        rotations(np.ones((5, 4)), x[:5])
