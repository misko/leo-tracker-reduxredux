"""Position diagnostic helper uses no target-dependent thresholds."""

import numpy as np
from report_control import distance_km


def test_distance_same_point_and_one_degree():
    reference = dict(latitude_deg=0.0, longitude_deg=0.0)
    assert distance_km(0.0, 0.0, reference) == 0
    assert np.isclose(distance_km(0.0, 1.0, reference), 6371.0088 * np.pi / 180)
