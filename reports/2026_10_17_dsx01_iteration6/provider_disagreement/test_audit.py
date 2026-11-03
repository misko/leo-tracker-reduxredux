import numpy as np
import pytest
from audit import projected_disagreement


def test_projection_preserves_seconds_sign_and_perpendicular_distance():
    seconds, perpendicular = projected_disagreement([75., 3., 4.], [0., 0., 0.], [7.5, 0., 0.])
    assert seconds==10. and perpendicular==5.
    seconds, perpendicular = projected_disagreement([-75., 0., 0.], [0., 0., 0.], [7.5, 0., 0.])
    assert seconds==-10. and perpendicular==0.


def test_zero_speed_rejected():
    with pytest.raises(ValueError):
        projected_disagreement(np.zeros(3), np.ones(3), np.zeros(3))
